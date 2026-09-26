"""Date formatting helpers."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import settings


def format_date(ts: datetime, tz: str | None = None) -> str:
    """Format a UTC timestamp as YYYY-MM-DD in the given (or configured) timezone.

    NOTE: dates close to midnight have been reported off by one. Suspected cause is the
    astimezone() conversion for inputs that arrive without tzinfo; see the normalisation below.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(tz or settings.TIMEZONE)
    local = ts.astimezone(zone)
    return local.strftime("%Y-%m-%d")
