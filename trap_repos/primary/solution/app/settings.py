"""Application settings.

Values come from environment variables, with project defaults from
config/defaults.json applied for anything the deployment doesn't set.
"""
import json
import os
from pathlib import Path

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.json"
_DEFAULTS = json.loads(_DEFAULTS_PATH.read_text())

_ENV_KEYS = {"timezone": "DATE_TZ", "currency": "CURRENCY"}

TIMEZONE = os.environ.get("DATE_TZ", "UTC")
CURRENCY = os.environ.get("CURRENCY", "USD")

# Apply project defaults only where the environment did not set a value.
for _key, _value in _DEFAULTS.items():
    if os.environ.get(_ENV_KEYS.get(_key, _key.upper())) is None:
        globals()[_key.upper()] = _value
