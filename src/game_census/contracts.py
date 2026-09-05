"""Public read contracts. They deliberately contain no operator configuration."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SourceFailure(ReadModel):
    code: str
    message: str
    next_action: str


class LastAttempt(ReadModel):
    status: str
    at: datetime | None = None
    error: SourceFailure | None = None


class AppSummary(ReadModel):
    app_id: int = Field(ge=1, le=4294967295)
    name: str
    player_count: int | None = Field(default=None, ge=0)
    availability: Literal["fresh", "stale", "no_observations", "unsupported", "not_tracked"]
    observed_at: datetime | None = None
    tracking_started_at: datetime
    sample_count: int = Field(ge=0)
    observed_24h_peak: int | None = Field(default=None, ge=0)
    highest_recorded: int | None = Field(default=None, ge=0)
    last_attempt: LastAttempt | None = None
    expected_interval_seconds: int = Field(gt=0)
    source: str
    source_version: str


class AppList(ReadModel):
    items: list[AppSummary]
    total: int
    tracking_scope: Literal["enrolled"] = "enrolled"
    generated_at: datetime


class PlayerPoint(ReadModel):
    observed_at: datetime
    player_count: int = Field(ge=0)


class Coverage(ReadModel):
    sample_count: int = Field(ge=0)
    expected_samples: int = Field(ge=0)
    covered_seconds: float = Field(ge=0)
    requested_seconds: float = Field(ge=0)
    maximum_gap_seconds: float = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)


class HistoryMetrics(ReadModel):
    observed_peak: int | None = Field(default=None, ge=0)
    average_observed_ccu: float | None = Field(default=None, ge=0)
    estimator_version: str


class HistoryGap(ReadModel):
    from_time: datetime = Field(alias="from")
    to: datetime
    seconds: float = Field(ge=0)


class PlayerHistory(ReadModel):
    app_id: int
    from_time: datetime = Field(alias="from")
    to: datetime
    points: list[PlayerPoint]
    coverage: Coverage
    metrics: HistoryMetrics
    source: str
    source_version: str
    gaps: list[HistoryGap]
    tracking_scope: Literal["recorded_by_this_instance"] = "recorded_by_this_instance"


class PublicStatus(ReadModel):
    read_service: Literal["ready"] = "ready"
    generated_at: datetime
    tracked_apps: int
    fresh_apps: int
    stale_apps: int
    apps_without_observations: int
    total_observations: int
    source: str
    collection_mode: Literal["manual"] = "manual"
    last_run: dict | None = None
