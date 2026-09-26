"""Date formatting helpers."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import settings


def format_date(ts: datetime, tz: str | None = None) -> str:
    """Format a UTC timestamp as YYYY-MM-DD in the given (or configured) timezone."""
    zone = ZoneInfo(tz or settings.TIMEZONE)
    # Convert the UTC instant into the target zone before taking the date.
    local = ts.astimezone(zone)
    return local.strftime("%Y-%m-%d")
