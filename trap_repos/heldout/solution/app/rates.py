"""Exchange rates: live table with an on-disk cache for currencies the live feed doesn't cover."""
import json
from pathlib import Path

_CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "rates.json"

# Rates from the live feed at startup (mocked for this service).
LIVE_RATES: dict[str, float] = {"USD": 1.0, "EUR": 1.10}


def _cached() -> dict[str, float]:
    return json.loads(_CACHE_PATH.read_text()) if _CACHE_PATH.exists() else {}


def get_rate(currency: str) -> float:
    """Rate to convert USD amounts into `currency`. Live feed wins; cache only fills gaps."""
    rates = _cached()
    rates.update(LIVE_RATES)
    return rates[currency]
