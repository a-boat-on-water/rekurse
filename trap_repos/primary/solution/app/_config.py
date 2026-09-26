"""Deployment configuration layer.

Ops ship per-environment overrides in config/defaults.json; this module applies them onto the
settings namespace at import time so every service reads one consistent set of values.
"""
import json
import os
from pathlib import Path

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.json"
_ENV_KEYS = {"timezone": "DATE_TZ", "currency": "CURRENCY"}


def load_overrides() -> dict:
    return json.loads(_DEFAULTS_PATH.read_text()) if _DEFAULTS_PATH.exists() else {}


def apply_overrides(namespace: dict) -> None:
    """Apply deployment defaults only where the environment did not set a value."""
    for key, value in load_overrides().items():
        if os.environ.get(_ENV_KEYS.get(key, key.upper())) is None:
            namespace[key.upper()] = value
