import pytest

from apps.backtest import engine
from apps.backtest.engine import run_backtest

BUY_HOLD = """
def on_tick(ctx):
    if ctx.position == 0:
        ctx.buy(ctx.symbol, 0.01)
"""

NOOP = """
def on_tick(ctx):
    ctx.log("tick %.2f" % ctx.price())
"""


def _fake_candles(symbol, bar, limit):
    return [
        {"ts": i, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "vol": 1.0}
        for i in range(int(limit))
    ]


@pytest.fixture(autouse=True)
def _patch_feed(monkeypatch):
    monkeypatch.setattr(engine, "_fetch_candles", _fake_candles)


def test_run_backtest_produces_curve_and_trades():
    r = run_backtest(BUY_HOLD, symbol="BTC-USDT", bar="1m", bars=100, initial_capital=10000)
    assert len(r["equity_curve"]) == 100
    assert r["trades"], "should have at least one buy"
    assert r["trades"][0]["side"] == "buy"
    assert r["final_equity"] > 0


def test_noop_strategy_keeps_capital_flat():
    r = run_backtest(NOOP, bars=50, initial_capital=10000)
    # 不交易,净值恒等于初始资金
    assert all(abs(p["equity"] - 10000) < 0.01 for p in r["equity_curve"])
    assert r["trades"] == []


def test_fee_reduces_cash():
    r = run_backtest(BUY_HOLD, bars=10, initial_capital=10000, fee_rate=0.001)
    # 买入付了手续费,首笔 trade 有 fee>0
    assert r["trades"][0]["fee"] > 0
