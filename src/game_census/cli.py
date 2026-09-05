"""Inspectable commands for every component in the first usable release."""
import argparse
import json
import sys
from pydantic import ValidationError
from .config import ConfigurationError, describe_settings, generate_profile, load_settings
from .db import Database, DatabaseError
from .sources import SourceError


def parser():
    p = argparse.ArgumentParser(prog="game-census", description="Collect and display recorded Steam player counts.")
    p.add_argument("--config", help="JSON configuration path (or GAME_CENSUS_CONFIG)")
    commands = p.add_subparsers(dest="command", required=True)
    config = commands.add_parser("config", help="Generate or inspect validated configuration").add_subparsers(dest="action", required=True)
    init = config.add_parser("init", help="Create a profile only when absent; never overwrite it")
    init.add_argument("--app-id", type=int, action="append")
    init.add_argument("--port", type=int, default=8000)
    desc = config.add_parser("describe", help="Print redacted settings or schema with supported bounds")
    desc.add_argument("--schema", action="store_true")
    commands.add_parser("initialize", help="Apply schema and enroll configured app IDs idempotently")
    collect = commands.add_parser("collect", help="Run one bounded collection; scheduling is unavailable")
    collect.add_argument("--once", action="store_true", required=True)
    collect.add_argument("--app-id", type=int, action="append")
    report = commands.add_parser("report", help="Print recorded operations status")
    report.add_argument("--last-run", action="store_true")
    commands.add_parser("apps", help="Print the enrolled cohort with source timestamps")
    history = commands.add_parser("history", help="Print bounded history and coverage")
    history.add_argument("--app-id", type=int, required=True)
    history.add_argument("--hours", type=int, default=24)
    aggregate = commands.add_parser("aggregate", help="Validate projections against canonical captures").add_subparsers(dest="action", required=True)
    aggregate.add_parser("rebuild", help="Replay captures without deleting or overwriting canonical data")
    commands.add_parser("serve", help="Serve the local read-only web application")
    doctor = commands.add_parser("doctor", help="Check configuration and database readiness")
    doctor.add_argument("--http", action="store_true", help="Also require an actual healthy HTTP server on the configured local port")
    return p


def emit(value, stream=None):
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout, flush=True)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "config":
            if args.action == "init":
                emit(generate_profile(args.config, app_ids=args.app_id, port=args.port))
            else:
                emit(describe_settings(None if args.schema else load_settings(args.config)))
            return 0
        settings = load_settings(args.config)
        db = Database(settings.storage.database_url.get_secret_value())
        if args.command == "initialize":
            result = db.initialize(settings.tracking.app_ids, settings.tracking.interval_seconds)
        elif args.command == "collect":
            from .collector import collect_once
            targets = args.app_id or settings.tracking.app_ids
            if any(app_id not in settings.tracking.app_ids for app_id in targets):
                raise ConfigurationError("Collection app IDs must be enrolled through tracking.app_ids. Update configuration before expanding the cohort.")
            emit({"operation": "collect_once", "app_ids": targets,
                  "maximum_requests": len(targets) * (2 if settings.sources.store_metadata_enabled else 1) * settings.http.max_attempts,
                  "scheduler": "disabled"})
            result = collect_once(settings, db, targets)
            emit(result)
            return 0 if result["status"] == "succeeded" else 1
        elif args.command == "report":
            result = db.last_run() if args.last_run else db.status()
            if result is None:
                result = {"status": "no_runs", "next_action": "Run collect --once to record observations."}
        elif args.command == "apps":
            rows = db.list_apps(settings)
            result = {"items": rows, "total": len(rows), "tracking_scope": "enrolled"}
        elif args.command == "history":
            result = db.history(args.app_id, settings, args.hours)
            if result is None:
                raise ConfigurationError("app_id has not been enrolled. Add it to tracking.app_ids and run initialize.")
        elif args.command == "aggregate":
            result = db.rebuild()
        elif args.command == "doctor":
            result = {"configuration": "ok", **db.status()}
            if args.http:
                import httpx
                try:
                    response = httpx.get(f"http://127.0.0.1:{settings.web.port}/health/ready", timeout=settings.http.timeout_seconds)
                    response.raise_for_status()
                    if response.json() != {"status": "ready"}:
                        raise ValueError("Unexpected readiness response")
                except (httpx.HTTPError, ValueError):
                    raise DatabaseError("HTTP readiness failed. Check the web process and web.bind/web.port settings, then run start again.") from None
                result["http"] = "ready"
        elif args.command == "serve":
            import uvicorn
            from .web import create_app
            db.status()  # Fail clearly before accepting requests against an empty/unavailable schema.
            uvicorn.run(create_app(settings, db), host=settings.web.bind, port=settings.web.port, access_log=False)
            return 0
        emit(result)
        return 0
    except (ConfigurationError, DatabaseError, SourceError) as error:
        emit({"status": "failed", "error": str(error)}, sys.stderr)
        return 1
    except ValidationError as error:
        keys = sorted({".".join(map(str, item["loc"])) for item in error.errors()})
        emit({"status": "failed", "error": "Invalid configuration setting(s): " + ", ".join(keys) + ". Run config describe --schema for bounds."}, sys.stderr)
        return 1
    except OSError:
        emit({"status": "failed", "error": "File or network operation failed. Check configuration paths, permissions, database status and available disk space."}, sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
