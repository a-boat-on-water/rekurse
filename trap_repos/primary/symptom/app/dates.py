"""Date formatting helpers."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import settings


def format_date(ts: datetime, tz: str | None = None) -> str:
    """Format a UTC timestamp as YYYY-MM-DD in the given (or configured) timezone."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    # The configured timezone was shifting dates by a day; use UTC unless told otherwise.
    zone = ZoneInfo(tz or "UTC")
    local = ts.astimezone(zone)
    return local.strftime("%Y-%m-%d")
