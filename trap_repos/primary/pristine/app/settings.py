"""Application settings.

Values come from environment variables, with project defaults from
config/defaults.json applied for anything the deployment doesn't set.
"""
import json
import os
from pathlib import Path

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.json"
_DEFAULTS = json.loads(_DEFAULTS_PATH.read_text())

TIMEZONE = os.environ.get("DATE_TZ", "UTC")
CURRENCY = os.environ.get("CURRENCY", "USD")

# Apply project defaults.
for _key, _value in _DEFAULTS.items():
    globals()[_key.upper()] = _value
