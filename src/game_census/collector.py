"""Bounded manual collection: durable accounting, atomic captures, explicit outcomes."""
import time
import httpx
from . import __version__
from .db import DatabaseError
from .sources import SourceError, players, store
from .sources.base import validate_app_id


def collect_once(settings, db, app_ids=None, transport=None) -> dict:
    targets = list(settings.tracking.app_ids if app_ids is None else app_ids)
    if not 1 <= len(targets) <= 25 or len(set(targets)) != len(targets):
        raise DatabaseError("Manual collection requires 1–25 unique app IDs. Correct tracking.app_ids.")
    for app_id in targets:
        validate_app_id(app_id)
    adapters = [players] + ([store] if settings.sources.store_metadata_enabled else [])
    with db.collection_lock():
        db.initialize(targets, settings.tracking.interval_seconds)
        run_id = db.start_run(targets, [a.SOURCE for a in adapters])
        report = {"run_id": run_id, "status": "failed", "apps": [], "request_count": 0}
        successes, failures = 0, 0
        try:
            with httpx.Client(timeout=settings.http.timeout_seconds, transport=transport,
                              headers={"User-Agent": f"Game-Census/{__version__}", "Accept": "application/json"}) as client:
                for app_id in targets:
                    app_report = {"app_id": app_id, "sources": []}
                    report["apps"].append(app_report)
                    for adapter in adapters:
                        outcome = {"source": adapter.SOURCE, "status": "failed"}
                        app_report["sources"].append(outcome)
                        for attempt_index in range(settings.http.max_attempts):
                            attempt_id = None
                            try:
                                group = adapter.HOST_GROUP
                                quota = getattr(settings.quota, f"{group}_rolling_24h")
                                spacing = max(settings.http.min_interval_seconds, 2 if group == "store" else 1)
                                attempt_id = db.reserve_attempt(run_id, app_id, adapter.SOURCE, group, quota, spacing)
                                report["request_count"] += 1
                                capture = adapter.fetch(client, app_id, settings.http.max_response_bytes)
                                capture_id = db.record_capture(run_id, attempt_id, capture)
                                # Earlier attempt failures remain in request_result; this outcome is successful.
                                outcome.pop("error", None)
                                outcome.update(status="succeeded", capture_id=capture_id,
                                               observed_at=capture.received_at.isoformat(), value=capture.value)
                                successes += 1
                                break
                            except SourceError as error:
                                outcome["error"] = error.as_dict()
                                if attempt_id:
                                    db.record_failure(attempt_id, error)
                                delay = error.retry_after_seconds if error.retry_after_seconds is not None else min(2 ** attempt_index, settings.http.timeout_seconds)
                                if not error.retryable or attempt_index + 1 >= settings.http.max_attempts or delay > settings.http.timeout_seconds:
                                    failures += 1
                                    break
                                time.sleep(delay)
                    app_report["status"] = "succeeded" if all(s["status"] == "succeeded" for s in app_report["sources"]) else ("partial" if any(s["status"] == "succeeded" for s in app_report["sources"]) else "failed")
        except Exception:
            report["error"] = {"code": "collection_interrupted", "message": "Collection could not finish; any unconfirmed requests remain charged.",
                               "next_action": "Check database and collector status, then run a new bounded collection. No historical gap can be backfilled."}
            report["status"] = "partial" if successes else "failed"
            db.finish_run(report)
            raise DatabaseError("Collection stopped before completion. Inspect the last-run report and database status; reserved requests remain charged.") from None
        report["status"] = "partial" if successes and failures else ("failed" if failures else "succeeded")
        db.finish_run(report)
        return report
