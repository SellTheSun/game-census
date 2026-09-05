"""PostgreSQL persistence and bounded read models; raw database errors stay private."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import time
import uuid
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from . import metrics, projections
from .sources import SourceError, players


class DatabaseError(Exception):
    """A safe, actionable storage diagnostic, without a DSN or server error text."""


class QueryLimitError(DatabaseError):
    """A history request exceeds the configured public read bounds."""


def iso(value):
    return value.isoformat() if value is not None else None


class Database:
    def __init__(self, dsn: str):
        self._dsn = dsn

    @contextmanager
    def connection(self):
        try:
            with psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row,
                                 application_name="game_census", options="-c statement_timeout=15000") as conn:
                yield conn
        except psycopg.Error:
            raise DatabaseError("PostgreSQL operation failed. Check storage.database_url and database status; run initialize before collecting or serving.") from None

    def initialize(self, app_ids: list[int], interval_seconds: int) -> dict:
        from .sources.base import validate_app_id
        for app_id in app_ids:
            validate_app_id(app_id)
        if type(interval_seconds) is not int or not 300 <= interval_seconds <= 604800:
            raise DatabaseError("tracking.interval_seconds must be an integer from 300 to 604800.")
        migration_dir = Path(__file__).parent / "migrations"
        with self.connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(734801001)")
            for migration in sorted(migration_dir.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))
            for app_id in app_ids:
                conn.execute("INSERT INTO app(app_id) VALUES (%s) ON CONFLICT DO NOTHING", (app_id,))
                latest = conn.execute("SELECT interval_seconds FROM tracking_interval WHERE app_id=%s ORDER BY started_at DESC,id DESC LIMIT 1", (app_id,)).fetchone()
                if latest is None or latest["interval_seconds"] != interval_seconds:
                    conn.execute("INSERT INTO tracking_interval(app_id,interval_seconds) VALUES (%s,%s)", (app_id, interval_seconds))
            counts = conn.execute("SELECT (SELECT count(*) FROM app) AS tracked_apps, (SELECT count(*) FROM capture) AS captures").fetchone()
            version = conn.execute("SELECT max(version) AS version FROM schema_migration").fetchone()["version"]
        return {"schema_version": version, **counts, "enrolled_app_ids": app_ids, "scheduler": "disabled"}

    @contextmanager
    def collection_lock(self):
        with self.connection() as conn:
            acquired = conn.execute("SELECT pg_try_advisory_lock(734801002) AS acquired").fetchone()["acquired"]
            if not acquired:
                raise DatabaseError("Another manual collector is active. Wait for it to finish before collecting again.")
            try:
                yield
            finally:
                conn.execute("SELECT pg_advisory_unlock(734801002)")

    def start_run(self, app_ids: list[int], sources: list[str]) -> str:
        run_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute("INSERT INTO collection_run(run_id,app_ids,sources) VALUES (%s,%s,%s)",
                         (run_id, Jsonb(app_ids), Jsonb(sources)))
        return run_id

    def reserve_attempt(self, run_id: str, app_id: int, source: str, host_group: str,
                        quota: int, interval_seconds: float) -> str:
        """Charge before dispatch, with a shared rolling ledger and per-host pacing."""
        with self.connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(734801003)")
            cooldown = conn.execute("SELECT max(expires_at) AS expires_at FROM source_cooldown WHERE host_group=%s AND expires_at>clock_timestamp()", (host_group,)).fetchone()["expires_at"]
            if cooldown is not None:
                raise SourceError("source_cooldown", f"Steam requested a {host_group} request cooldown.",
                                  f"Wait until {cooldown.isoformat()} before collecting from this source again.")
            count = conn.execute("SELECT count(*) AS n FROM request_attempt WHERE host_group=%s AND dispatched_at > clock_timestamp()-interval '24 hours'", (host_group,)).fetchone()["n"]
            if count >= quota:
                raise SourceError("quota_exhausted", f"The {host_group} rolling 24-hour request budget is exhausted.",
                                  "Wait for reserved attempts to leave the rolling window before collecting again.")
            previous = conn.execute("SELECT EXTRACT(EPOCH FROM (clock_timestamp()-max(dispatched_at))) AS elapsed FROM request_attempt WHERE host_group=%s", (host_group,)).fetchone()["elapsed"]
            if previous is not None:
                remaining = interval_seconds - float(previous)
                if remaining > 0:
                    time.sleep(remaining)
            attempt_id = str(uuid.uuid4())
            conn.execute("INSERT INTO request_attempt(attempt_id,run_id,app_id,source,host_group) VALUES (%s,%s,%s,%s,%s)",
                         (attempt_id, run_id, app_id, source, host_group))
        return attempt_id

    def record_capture(self, run_id: str, attempt_id: str, capture) -> str:
        capture_id = str(uuid.uuid4())
        row = {"capture_id": capture_id, "app_id": capture.app_id, "source": capture.source,
               "source_version": capture.source_version, "received_at": capture.received_at,
               "payload": capture.payload, "checksum": capture.checksum}
        with self.connection() as conn:
            conn.execute("""INSERT INTO capture(capture_id,attempt_id,run_id,app_id,source,source_version,
                request_started_at,received_at,http_status,parameters,payload,checksum,capture_form)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (capture_id, attempt_id, run_id, capture.app_id, capture.source, capture.source_version,
                 capture.request_started_at, capture.received_at, capture.http_status, Jsonb(capture.parameters),
                 capture.payload, capture.checksum, capture.capture_form))
            projections.project(conn, row)
            conn.execute("INSERT INTO request_result(attempt_id,status,http_status) VALUES (%s,'succeeded',%s)",
                         (attempt_id, capture.http_status))
        return capture_id

    def record_failure(self, attempt_id: str, error: SourceError) -> None:
        with self.connection() as conn:
            conn.execute("INSERT INTO request_result(attempt_id,status,http_status,error) VALUES (%s,'failed',%s,%s)",
                         (attempt_id, error.http_status, Jsonb(error.as_dict())))
            if error.retry_after_seconds is not None and error.retry_after_seconds > 0:
                conn.execute("""INSERT INTO source_cooldown(cooldown_id,attempt_id,host_group,expires_at)
                    SELECT %s,attempt_id,host_group,clock_timestamp()+(%s * interval '1 second')
                    FROM request_attempt WHERE attempt_id=%s""",
                    (str(uuid.uuid4()),error.retry_after_seconds,attempt_id))

    def finish_run(self, report: dict) -> None:
        with self.connection() as conn:
            conn.execute("INSERT INTO run_completion(run_id,status,report) VALUES (%s,%s,%s)",
                         (report["run_id"], report["status"], Jsonb(report)))

    def last_run(self) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("""SELECT r.*, c.finished_at,c.status,c.report FROM collection_run r
                LEFT JOIN run_completion c USING(run_id) ORDER BY r.started_at DESC LIMIT 1""").fetchone()
        if row is None:
            return None
        if row["report"] is not None:
            return {**row["report"], "started_at": iso(row["started_at"]), "finished_at": iso(row["finished_at"])}
        return {"run_id": str(row["run_id"]), "status": "unfinished", "app_ids": row["app_ids"],
                "started_at": iso(row["started_at"]), "finished_at": None,
                "next_action": "Inspect the collector process. An interrupted request remains charged; a new bounded run cannot fill its historical gap."}

    def status(self) -> dict:
        with self.connection() as conn:
            counts = conn.execute("""SELECT (SELECT count(*) FROM app) AS tracked_apps,
                (SELECT count(*) FROM capture) AS captures,(SELECT count(*) FROM player_sample) AS player_samples,
                (SELECT count(*) FROM request_attempt a LEFT JOIN request_result r USING(attempt_id)
                  WHERE r.attempt_id IS NULL) AS uncertain_attempts""").fetchone()
            groups = conn.execute("SELECT host_group,count(*) AS n FROM request_attempt WHERE dispatched_at>clock_timestamp()-interval '24 hours' GROUP BY host_group").fetchall()
            cooldowns = conn.execute("SELECT host_group,max(expires_at) AS expires_at FROM source_cooldown WHERE expires_at>clock_timestamp() GROUP BY host_group").fetchall()
        return {"database": "ok", **counts, "request_attempts_24h": {"webapi": 0, "store": 0, **{g["host_group"]: g["n"] for g in groups}},
                "source_cooldowns": [{"host_group": row["host_group"], "expires_at": iso(row["expires_at"])} for row in cooldowns],
                "last_run": self.last_run(), "scheduler": "disabled"}

    def list_apps(self, settings) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("""SELECT a.app_id,a.created_at AS tracking_started_at,
                n.name,p.player_count,p.observed_at,
                t.interval_seconds AS expected_interval_seconds,
                (SELECT count(*) FROM player_sample ps WHERE ps.app_id=a.app_id) AS sample_count,
                (SELECT max(player_count) FROM player_sample ps WHERE ps.app_id=a.app_id) AS highest_recorded,
                (SELECT max(player_count) FROM player_sample ps WHERE ps.app_id=a.app_id AND observed_at>=clock_timestamp()-interval '24 hours') AS observed_24h_peak,
                ra.dispatched_at,rr.status AS attempt_status,rr.error AS attempt_error
                FROM app a
                LEFT JOIN LATERAL (SELECT * FROM app_name WHERE app_id=a.app_id ORDER BY observed_at DESC,capture_id DESC LIMIT 1) n ON true
                LEFT JOIN LATERAL (SELECT * FROM player_sample WHERE app_id=a.app_id ORDER BY observed_at DESC,capture_id DESC LIMIT 1) p ON true
                LEFT JOIN LATERAL (SELECT * FROM tracking_interval WHERE app_id=a.app_id ORDER BY started_at DESC,id DESC LIMIT 1) t ON true
                LEFT JOIN LATERAL (SELECT * FROM request_attempt WHERE app_id=a.app_id AND source=%s ORDER BY dispatched_at DESC LIMIT 1) ra ON true
                LEFT JOIN request_result rr ON rr.attempt_id=ra.attempt_id ORDER BY a.app_id""", (players.SOURCE,)).fetchall()
        now = datetime.now(timezone.utc)
        result = []
        for row in rows:
            at = row["observed_at"]
            state = "no_observations" if at is None else ("fresh" if (now-at).total_seconds() <= row["expected_interval_seconds"]*settings.metrics.freshness_interval_multiplier else "stale")
            last_attempt = None if row["dispatched_at"] is None else {"status": row["attempt_status"] or "uncertain", "at": iso(row["dispatched_at"]), "error": row["attempt_error"]}
            result.append({"app_id": row["app_id"], "name": row["name"] or f"Steam app {row['app_id']}",
                           "player_count": row["player_count"], "availability": state, "observed_at": iso(at),
                           "tracking_started_at": iso(row["tracking_started_at"]), "sample_count": row["sample_count"],
                           "observed_24h_peak": row["observed_24h_peak"], "highest_recorded": row["highest_recorded"],
                           "expected_interval_seconds": row["expected_interval_seconds"], "last_attempt": last_attempt,
                           "source": players.SOURCE, "source_version": players.VERSION, "source_url": players.DOCUMENTATION_URL})
        return result

    def app_detail(self, app_id: int, settings) -> dict | None:
        return next((row for row in self.list_apps(settings) if row["app_id"] == app_id), None)

    def history(self, app_id: int, settings, hours: int = 24) -> dict | None:
        if type(hours) is not int or not 1 <= hours <= settings.web.max_history_days * 24:
            raise QueryLimitError("hours must be an integer from 1 through web.max_history_days × 24. Request a smaller history window.")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        with self.connection() as conn:
            if conn.execute("SELECT app_id FROM app WHERE app_id=%s", (app_id,)).fetchone() is None:
                return None
            n = conn.execute("SELECT count(*) AS n FROM player_sample WHERE app_id=%s AND observed_at >= %s AND observed_at < %s", (app_id,start,end)).fetchone()["n"]
            if n > settings.web.max_points:
                raise QueryLimitError("History exceeds web.max_points. Request a smaller hours window; no observations were truncated.")
            rows = conn.execute("SELECT observed_at,player_count FROM player_sample WHERE app_id=%s AND observed_at >= %s AND observed_at < %s ORDER BY observed_at,capture_id", (app_id,start,end)).fetchall()
            previous = conn.execute("SELECT observed_at,player_count FROM player_sample WHERE app_id=%s AND observed_at<%s ORDER BY observed_at DESC,capture_id DESC LIMIT 1", (app_id,start)).fetchone()
            tracking = conn.execute("SELECT started_at,interval_seconds FROM tracking_interval WHERE app_id=%s ORDER BY started_at,id", (app_id,)).fetchall()
        calculated = metrics.calculate(([previous] if previous else [])+rows, start,end,tracking,settings.metrics.gap_cap_multiplier)
        return {"app_id": app_id, "from": iso(start), "to": iso(end),
                "points": [{"observed_at": iso(r["observed_at"]), "player_count": r["player_count"]} for r in rows],
                "source": players.SOURCE,"source_version": players.VERSION, **calculated}

    def rebuild(self) -> dict:
        """Replay retained captures, add missing rows, and prove all projections match."""
        digest = hashlib.sha256()
        with self.connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(734801002)")
            captures = conn.execute("SELECT * FROM capture ORDER BY received_at,capture_id").fetchall()
            for row in captures:
                projections.project(conn,row)
                digest.update(f"{row['capture_id']}:{row['checksum']}\n".encode())
            rows = conn.execute("""SELECT capture_id,app_id,observed_at,player_count AS value,parser_version FROM player_sample
                UNION ALL SELECT capture_id,app_id,observed_at,NULL::bigint AS value,parser_version FROM app_name""").fetchall()
            if len(rows) != len(captures):
                raise DatabaseError("Projection row counts do not match retained captures. Inspect a scratch restore before repairing projections.")
            by_id = {r["capture_id"]: r for r in rows}
            from .sources import REGISTRY
            for capture in captures:
                projection = by_id[capture["capture_id"]]
                adapter = REGISTRY[capture["source"]]
                expected = adapter.parse(bytes(capture["payload"]),capture["app_id"])
                if adapter is players:
                    actual = projection["value"]
                else:
                    actual = conn.execute("SELECT name FROM app_name WHERE capture_id=%s", (capture["capture_id"],)).fetchone()["name"]
                if (actual != expected or projection["app_id"] != capture["app_id"] or projection["observed_at"] != capture["received_at"] or projection["parser_version"] != adapter.VERSION):
                    raise DatabaseError("A derived projection differs from its retained capture. Inspect a scratch restore before repairing projections.")
        return {"status": "succeeded", "captures_replayed": len(captures), "projections_verified": len(rows),
                "capture_manifest_sha256": digest.hexdigest(), "canonical_history_changed": False}
