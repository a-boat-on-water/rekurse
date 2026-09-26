"""Date formatting helpers."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import settings


def format_date(ts: datetime, tz: str | None = None) -> str:
    """Format a UTC timestamp as YYYY-MM-DD in the given (or configured) timezone."""
    # The configured timezone was shifting dates by a day; use UTC unless told otherwise.
    zone = ZoneInfo(tz or "UTC")
    local = ts.astimezone(zone)
    return local.strftime("%Y-%m-%d")
