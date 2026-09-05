"""Stored-data-only HTTP interface and server-rendered exploration workspace."""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contracts import AppList, AppSummary, PlayerHistory, PublicStatus
from .db import QueryLimitError
from .sources.players import DOCUMENTATION_URL as SOURCE_URL, SOURCE as SOURCE_ID

logger = logging.getLogger(__name__)
PACKAGE = Path(__file__).parent
APP_ID = Annotated[int, ApiPath(ge=1, le=4294967295)]


def _utc(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _number(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _timestamp(value: datetime | str | None) -> str:
    return _utc(value).strftime("%d %b %Y, %H:%M:%S UTC") if value else "Not yet observed"


def _chart(history: dict, interval: int, gap_multiplier: float) -> dict:
    """Only draw observed samples; never bridge a cadence-capped collection gap."""
    points = history["points"]
    start, end = _utc(history["from"]), _utc(history["to"])
    seconds = max((end - start).total_seconds(), 1)
    width, height, left, top = 880, 260, 64, 24
    plot_width, plot_height = width - left - 24, height - top - 40
    maximum = max((point["player_count"] for point in points), default=0)
    ceiling = max(4, math.ceil(maximum * 1.12))
    plotted, paths, segment = [], [], []
    previous_time = None
    for point in points:
        at = _utc(point["observed_at"])
        x = left + max(0, min(1, (at - start).total_seconds() / seconds)) * plot_width
        y = top + (1 - point["player_count"] / ceiling) * plot_height
        crosses_recorded_gap = previous_time is not None and any(
            _utc(gap["from"]) < at and _utc(gap["to"]) > previous_time for gap in history.get("gaps", [])
        )
        if previous_time is not None and (crosses_recorded_gap or (at - previous_time).total_seconds() > interval * gap_multiplier):
            paths.append(" ".join(segment))
            segment = []
        segment.append(f"{x:.2f},{y:.2f}")
        plotted.append({"x": round(x, 2), "y": round(y, 2), "count": point["player_count"], "at": _timestamp(at)})
        previous_time = at
    if segment:
        paths.append(" ".join(segment))
    ticks = [{"y": top + plot_height * index / 4, "label": _number(ceiling * (1 - index / 4))} for index in range(5)]
    return {"paths": paths, "points": plotted, "ticks": ticks, "start_label": start.strftime("%d %b · %H:%M"),
            "end_label": end.strftime("%d %b · %H:%M UTC"), "width": width, "height": height}


def create_app(settings: Any, db: Any = None) -> FastAPI:
    """Create a read process. Storage setup and Steam collection belong to the CLI."""
    if db is None:
        from .db import Database

        db = Database(settings.storage.database_url.get_secret_value())
    app = FastAPI(title="Game Census read API", version="1.0.0", docs_url=None, redoc_url=None)
    app.state.db = db
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory=str(PACKAGE / "static")), name="static")
    templates = Jinja2Templates(directory=str(PACKAGE / "templates"))
    templates.env.filters["number"] = _number
    templates.env.filters["timestamp"] = _timestamp
    maximum_hours = settings.web.max_history_days * 24

    def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
        return templates.TemplateResponse(request=request, name=name, status_code=status_code, context={
            "nav": "activity", "source_url": SOURCE_URL, "generated_at": datetime.now(timezone.utc),
            "refresh_seconds": settings.web.refresh_seconds, **(context or {}),
        })

    def read(operation: str, *args, **kwargs):
        try:
            return getattr(db, operation)(*args, **kwargs)
        except QueryLimitError as exc:
            raise HTTPException(422, {"code": "history_point_limit", "message": str(exc)}) from None
        except Exception as exc:
            incident = uuid.uuid4().hex[:12]
            # Exception text may contain a database URL or other credentials.
            logger.error("read_service_failed operation=%s error_type=%s incident=%s", operation, type(exc).__name__, incident)
            raise HTTPException(503, {"code": "storage_unavailable", "message": "Stored data could not be read. Check database availability and run the status command.", "incident": incident}) from None

    def detail(app_id: int) -> dict:
        result = read("app_detail", app_id, settings)
        if result is None:
            raise HTTPException(404, {"code": "app_not_tracked", "message": f"App {app_id} is not tracked by this instance. Return to the tracked games list."})
        return AppSummary.model_validate(result).model_dump()

    def listing(q: str = "") -> list[dict]:
        apps = [AppSummary.model_validate(item).model_dump() for item in read("list_apps", settings)]
        query = q.strip().casefold()
        return sorted([item for item in apps if not query or query in item["name"].casefold() or query in str(item["app_id"])],
                      key=lambda item: (item["availability"] != "fresh", -(item["player_count"] or 0), item["app_id"]))

    def history_for(app_id: int, hours: int) -> dict:
        result = read("history", app_id, settings, hours=hours)
        if result is None:
            raise HTTPException(404, {"code": "app_not_tracked", "message": f"App {app_id} is not tracked by this instance."})
        if len(result["points"]) > settings.web.max_points:
            raise HTTPException(422, {"code": "history_point_limit", "message": f"This window exceeds web.max_points ({settings.web.max_points}). Choose a shorter history window."})
        return PlayerHistory.model_validate(result).model_dump(by_alias=True)

    def status_data() -> dict:
        read("status")
        apps = listing()
        run = read("last_run")
        # Restrict operational output to safe counts and outcomes, never arbitrary config.
        safe_run = None if run is None else {key: run[key] for key in ("run_id", "status", "started_at", "finished_at", "completed_at", "app_ids", "attempted", "succeeded", "failed") if key in run}
        return PublicStatus(generated_at=datetime.now(timezone.utc), tracked_apps=len(apps),
                            fresh_apps=sum(item["availability"] == "fresh" for item in apps),
                            stale_apps=sum(item["availability"] == "stale" for item in apps),
                            apps_without_observations=sum(item["player_count"] is None for item in apps),
                            total_observations=sum(item["sample_count"] for item in apps), source=SOURCE_ID,
                            last_run=safe_run).model_dump()

    def page_data(item: dict, hours: int) -> dict:
        history = history_for(item["app_id"], hours)
        return {"game": item, "history": history, "hours": hours,
                "windows": [(value, label) for value, label in [(1, "1H"), (24, "24H"), (168, "7D"), (720, "30D")] if value <= maximum_hours],
                "chart": _chart(history, item["expected_interval_seconds"], settings.metrics.gap_cap_multiplier)}

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            incident = uuid.uuid4().hex[:12]
            logger.error("read_contract_failure error_type=%s incident=%s", type(exc).__name__, incident)
            problem = {"code": "read_contract_failure", "message": "Stored data could not be presented. Run the status command and inspect the read service using this report reference.", "incident": incident}
            response = (JSONResponse(status_code=503, content={"error": problem})
                        if request.url.path.startswith(("/api/", "/health/", "/openapi.json"))
                        else render(request, "error.html", {"status_code": 503, "problem": problem}, 503))
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if not request.url.path.startswith("/static/") else "public, max-age=3600"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        problem = exc.detail if isinstance(exc.detail, dict) else {"code": "request_failed", "message": str(exc.detail)}
        if request.url.path.startswith(("/api/", "/health/")):
            return JSONResponse(status_code=exc.status_code, content={"error": problem})
        return render(request, "error.html", {"status_code": exc.status_code, "problem": problem}, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        problem = {"code": "invalid_request", "message": "A request value is outside the allowed bounds.",
                   "fields": [".".join(str(part) for part in item["loc"]) for item in exc.errors()]}
        if request.url.path.startswith(("/api/", "/health/")):
            return JSONResponse(status_code=422, content={"error": problem})
        return render(request, "error.html", {"status_code": 422, "problem": problem}, 422)

    @app.get("/health/live", tags=["Health"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Health"])
    def ready():
        read("status")
        return {"status": "ready"}

    @app.get("/api/v1/apps", response_model=AppList, tags=["Players"])
    def api_apps(q: Annotated[str, Query(max_length=100)] = ""):
        items = listing(q)
        return {"items": items, "total": len(items), "tracking_scope": "enrolled", "generated_at": datetime.now(timezone.utc)}

    @app.get("/api/v1/apps/{app_id}", response_model=AppSummary, tags=["Players"])
    @app.get("/api/v1/apps/{app_id}/players", response_model=AppSummary, tags=["Players"])
    def api_app(app_id: APP_ID):
        return detail(app_id)

    @app.get("/api/v1/apps/{app_id}/history", response_model=PlayerHistory, tags=["Players"])
    def api_history(app_id: APP_ID, hours: int = Query(default=24, ge=1, le=maximum_hours)):
        return history_for(app_id, hours)

    @app.get("/api/v1/status", response_model=PublicStatus, tags=["Health"])
    def api_status():
        return status_data()

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request, q: Annotated[str, Query(max_length=100)] = "", hours: int = Query(default=24, ge=1, le=maximum_hours)):
        apps = listing()
        filtered = listing(q) if q.strip() else apps
        page = page_data(apps[0], hours) if apps else {}
        return render(request, "index.html", {"apps": filtered, "cohort_count": len(apps), "q": q,
                      "fresh_count": sum(item["availability"] == "fresh" for item in apps), **page})

    @app.get("/apps/{app_id}", response_class=HTMLResponse, include_in_schema=False)
    def game_page(request: Request, app_id: APP_ID, hours: int = Query(default=24, ge=1, le=maximum_hours)):
        return render(request, "game.html", page_data(detail(app_id), hours))

    @app.get("/methodology", response_class=HTMLResponse, include_in_schema=False)
    def methodology(request: Request):
        return render(request, "methodology.html", {"nav": "methodology", "freshness_multiplier": settings.metrics.freshness_interval_multiplier,
                                                   "gap_multiplier": settings.metrics.gap_cap_multiplier, "max_points": settings.web.max_points,
                                                   "max_history_days": settings.web.max_history_days})

    @app.get("/status", response_class=HTMLResponse, include_in_schema=False)
    def status_page(request: Request):
        return render(request, "status.html", {"nav": "status", "status": status_data(), "apps": listing()})

    return app
