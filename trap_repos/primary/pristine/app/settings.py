"""Application settings, read from the environment."""
import os

from app.runtime.profile import finalize

TIMEZONE = os.environ.get("DATE_TZ", "UTC")
CURRENCY = os.environ.get("CURRENCY", "USD")

finalize(globals())
