"""Deployment configuration layer.

Ops ship per-environment overrides in config/defaults.json; this module applies them onto the
settings namespace at import time so every service reads one consistent set of values.
"""
import json
from pathlib import Path

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.json"


def load_overrides() -> dict:
    return json.loads(_DEFAULTS_PATH.read_text()) if _DEFAULTS_PATH.exists() else {}


def apply_overrides(namespace: dict) -> None:
    """Apply deployment overrides onto a settings namespace (keys are upper-cased)."""
    for key, value in load_overrides().items():
        namespace[key.upper()] = value
