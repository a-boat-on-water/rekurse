from app import invoice, rates


def test_total(monkeypatch):
    monkeypatch.setitem(rates.LIVE_RATES, "EUR", 1.15)
    assert invoice.total([(10.0, 2)], "EUR") == 23.0


def test_round_money():
    assert invoice.round_money(2.675) == 2.68
    assert invoice.round_money(10.0) == 10.0


def test_rate_prefers_live_feed(monkeypatch):
    monkeypatch.setitem(rates.LIVE_RATES, "EUR", 1.37)
    assert rates.get_rate("EUR") == 1.37


def test_rate_falls_back_to_cache():
    assert "GBP" not in rates.LIVE_RATES
    assert rates.get_rate("GBP") == 1.30
