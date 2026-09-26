"""Application settings. Environment variables first, then the deployment layer."""
import os

from app._config import apply_overrides

TIMEZONE = os.environ.get("DATE_TZ", "UTC")
CURRENCY = os.environ.get("CURRENCY", "USD")

apply_overrides(globals())
