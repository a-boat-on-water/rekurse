"""Runtime profile support.

A deployment ships a profile (config/defaults.json) describing the environment it runs in. `finalize`
validates the settings namespace and applies the active profile so all services agree on one set of values.
"""
import json
from pathlib import Path

_PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "defaults.json"

_REQUIRED = ("TIMEZONE", "CURRENCY")


def _load_profile() -> dict:
    return json.loads(_PROFILE_PATH.read_text()) if _PROFILE_PATH.exists() else {}


def finalize(namespace: dict) -> None:
    """Validate required settings and apply the deployment profile."""
    for key in _REQUIRED:
        if key not in namespace:
            raise RuntimeError(f"setting {key} is missing")
    for key, value in _load_profile().items():
        namespace[key.upper()] = value
