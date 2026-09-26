import importlib
from datetime import datetime, timezone

import pytest

from app import dates, settings

UTC = timezone.utc


def _reload_settings(monkeypatch, tz: str):
    monkeypatch.setenv("DATE_TZ", tz)
    importlib.reload(settings)
    importlib.reload(dates)


def test_format_date(monkeypatch):
    _reload_settings(monkeypatch, "UTC")
    ts = datetime(2026, 1, 1, 2, 30, tzinfo=UTC)
    assert dates.format_date(ts) == "2026-01-01"


def test_explicit_timezone(monkeypatch):
    _reload_settings(monkeypatch, "UTC")
    ts = datetime(2026, 1, 1, 20, 30, tzinfo=UTC)
    assert dates.format_date(ts, tz="Asia/Tokyo") == "2026-01-02"


def test_default_timezone_from_environment(monkeypatch):
    _reload_settings(monkeypatch, "Asia/Tokyo")
    ts = datetime(2026, 1, 1, 20, 30, tzinfo=UTC)
    assert dates.format_date(ts) == "2026-01-02"
