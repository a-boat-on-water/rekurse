"""Runtime profile support.

A deployment ships a profile (config/defaults.json) describing the environment it runs in. `finalize`
validates the settings namespace and applies the active profile so all services agree on one set of values.
"""
import json
import os
from pathlib import Path

_PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "defaults.json"

_REQUIRED = ("TIMEZONE", "CURRENCY")
_ENV_KEYS = {"timezone": "DATE_TZ", "currency": "CURRENCY"}


def _load_profile() -> dict:
    return json.loads(_PROFILE_PATH.read_text()) if _PROFILE_PATH.exists() else {}


def finalize(namespace: dict) -> None:
    """Validate required settings and apply the deployment profile where the environment set nothing."""
    for key in _REQUIRED:
        if key not in namespace:
            raise RuntimeError(f"setting {key} is missing")
    for key, value in _load_profile().items():
        if os.environ.get(_ENV_KEYS.get(key, key.upper())) is None:
            namespace[key.upper()] = value
