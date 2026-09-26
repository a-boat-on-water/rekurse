"""Exchange rates: live table with an on-disk cache for currencies the live feed doesn't cover."""
import json
from pathlib import Path

_CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "rates.json"

# Rates from the live feed at startup (mocked for this service).
LIVE_RATES: dict[str, float] = {"USD": 1.0, "EUR": 1.10}


def _cached() -> dict[str, float]:
    return json.loads(_CACHE_PATH.read_text()) if _CACHE_PATH.exists() else {}


def get_rate(currency: str) -> float:
    """Rate to convert USD amounts into `currency`."""
    rates = dict(LIVE_RATES)
    rates.update(_cached())
    return rates[currency]
