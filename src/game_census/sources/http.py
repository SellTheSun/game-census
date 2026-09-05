"""One bounded HTTPS request. Durable admission belongs to the collector/database."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from .base import SourceError

ALLOWED_HOSTS = frozenset({"api.steampowered.com", "store.steampowered.com"})


def retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = int(value)
        # Bound untrusted delta-seconds to the representable UTC timestamp range.
        maximum = (datetime.max.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, float(seconds)) if seconds <= maximum else None
    except (ValueError, OverflowError):
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                return None
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def request(client: httpx.Client, url: str, params: dict, max_bytes: int, *, headers: dict | None = None) -> tuple[bytes, datetime, datetime, int]:
    parsed = httpx.URL(url)
    if parsed.scheme != "https" or parsed.host not in ALLOWED_HOSTS or parsed.port not in (None, 443) or parsed.userinfo:
        raise SourceError("source_not_allowed", "The source URL is outside the approved Steam hosts.",
                          "Use the shipped Steam source adapters.")
    started = datetime.now(timezone.utc)
    try:
        with client.stream("GET", url, params=params, headers=headers, follow_redirects=False) as response:
            if response.status_code != 200:
                raise SourceError("http_error", f"Steam returned HTTP {response.status_code}.",
                                  "Retry a bounded collection after Steam access recovers.",
                                  http_status=response.status_code,
                                  retryable=response.status_code in (429, 500, 502, 503, 504),
                                  retry_after_seconds=retry_after(response.headers.get("Retry-After")))
            payload = bytearray()
            for chunk in response.iter_bytes():
                if len(payload) + len(chunk) > max_bytes:
                    raise SourceError("response_too_large", "Steam response exceeded http.max_response_bytes.",
                                      "Inspect the source contract and configured response-size bound.")
                payload.extend(chunk)
            return bytes(payload), started, datetime.now(timezone.utc), response.status_code
    except httpx.TimeoutException:
        raise SourceError("timeout", "Steam request timed out.",
                          "Check network connectivity and retry a bounded collection.", retryable=True) from None
    except httpx.RequestError:
        raise SourceError("network_error", "Steam request could not complete.",
                          "Check network connectivity and retry a bounded collection.", retryable=True) from None
