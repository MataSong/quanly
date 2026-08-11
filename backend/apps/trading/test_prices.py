import pytest
from apps.trading import prices


def test_get_last_price_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(prices, "_redis_get", lambda symbol: None)
    assert prices.get_last_price("BTC-USDT") is None


def test_get_last_price_reads_redis(monkeypatch):
    monkeypatch.setattr(prices, "_redis_get", lambda symbol: 65000.0)
    assert prices.get_last_price("BTC-USDT") == 65000.0
