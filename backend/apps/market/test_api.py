import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_symbols_public():
    c = APIClient()
    r = c.get("/api/market/symbols")
    assert r.status_code == 200
    assert "BTC-USDT" in r.data["symbols"]


@pytest.mark.django_db
def test_candles_public(monkeypatch):
    from apps.exchanges.okx import adapter as okx_adapter
    from apps.exchanges.types import Candle

    def fake_get_candles(self, symbol, bar, limit):
        return [Candle(ts=1700000000000, open=1, high=2, low=0.5, close=1.5, vol=10)]

    monkeypatch.setattr(okx_adapter.OKXAdapter, "get_candles", fake_get_candles)

    c = APIClient()  # 未登录也能访问
    r = c.get("/api/market/BTC-USDT/candles?bar=1m&limit=1")
    assert r.status_code == 200
    assert r.data["symbol"] == "BTC-USDT"
    assert len(r.data["candles"]) == 1
    assert r.data["candles"][0]["close"] == 1.5
