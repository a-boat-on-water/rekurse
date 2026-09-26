"""Application settings: environment variables first, then the deployment profile."""
import json
import os
from pathlib import Path

_PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.json"
_ENV_KEYS = {"timezone": "DATE_TZ", "currency": "CURRENCY"}

TIMEZONE = os.environ.get("DATE_TZ", "UTC")
CURRENCY = os.environ.get("CURRENCY", "USD")

# Apply the deployment profile only where the environment did not set a value.
_profile = json.loads(_PROFILE_PATH.read_text()) if _PROFILE_PATH.exists() else {}
for _key, _value in _profile.items():
    if os.environ.get(_ENV_KEYS.get(_key, _key.upper())) is None:
        globals()[_key.upper()] = _value
