"""Inspectable source contracts and safe diagnostics; no source performs retries."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json


class SourceError(Exception):
    def __init__(self, code: str, message: str, next_action: str, *, retryable: bool = False,
                 http_status: int | None = None, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.code, self.message, self.next_action = code, message, next_action
        self.retryable, self.http_status = retryable, http_status
        self.retry_after_seconds = retry_after_seconds

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "next_action": self.next_action}


@dataclass(frozen=True)
class Capture:
    source: str
    source_version: str
    app_id: int
    request_started_at: datetime
    received_at: datetime
    http_status: int
    parameters: dict
    payload: bytes
    capture_form: str
    value: int | str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


def parse_json(payload: bytes) -> dict:
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeError):
        raise SourceError("invalid_json", "Steam returned invalid JSON.",
                          "Inspect the source contract and retry a bounded collection.") from None
    if not isinstance(value, dict):
        raise SourceError("invalid_schema", "Steam returned a non-object response.",
                          "Inspect the source contract before collecting again.")
    return value


def validate_app_id(app_id: int) -> None:
    if type(app_id) is not int or not 1 <= app_id <= 4294967295:
        raise SourceError("invalid_app_id", "app_id must be an integer from 1 to 4294967295.",
                          "Correct tracking.app_ids or the requested app ID.")
