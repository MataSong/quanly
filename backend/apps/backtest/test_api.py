import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.backtest import engine
from apps.strategy.models import Strategy

BUY_HOLD = """
def on_tick(ctx):
    if ctx.position == 0:
        ctx.buy(ctx.symbol, 0.01)
"""


def _fake_candles(symbol, bar, limit):
    return [
        {"ts": i, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "vol": 1.0}
        for i in range(int(limit))
    ]


@pytest.fixture(autouse=True)
def _patch_feed(monkeypatch):
    monkeypatch.setattr(engine, "_fetch_candles", _fake_candles)


@pytest.fixture
def auth(db):
    u = get_user_model().objects.create_user("bt", password="pass12345")
    c = APIClient()
    c.force_authenticate(u)
    return c, u


def test_run_backtest_with_strategy(auth):
    c, u = auth
    s = Strategy.objects.create(user=u, name="buyhold", source=BUY_HOLD)
    r = c.post(
        "/api/backtests/run",
        {"strategy_id": s.id, "symbol": "BTC-USDT", "bars": 100, "initial_capital": 10000},
        format="json",
    )
    assert r.status_code == 201
    assert len(r.data["result"]["equity_curve"]) == 100
    assert "sharpe" in r.data["metrics"]
    assert "max_drawdown" in r.data["metrics"]


def test_run_backtest_with_source(auth):
    c, u = auth
    r = c.post(
        "/api/backtests/run",
        {"source": BUY_HOLD, "bars": 50},
        format="json",
    )
    assert r.status_code == 201
    # 可回看
    bid = r.data["id"]
    r2 = c.get(f"/api/backtests/{bid}")
    assert r2.status_code == 200 and "metrics" in r2.data


def test_run_requires_auth():
    c = APIClient()
    assert c.post("/api/backtests/run", {}, format="json").status_code == 401
