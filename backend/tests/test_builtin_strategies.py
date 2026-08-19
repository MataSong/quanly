"""Tests for UC-T8: built-in RSI + MACD strategies.

Coverage:
  1. rsi.compute_signal  — pure-function: oversold/overbought/neutral/insufficient.
  2. macd.compute_signal — pure-function: bullish/bearish crossover/none/insufficient.
  3. on_tick             — buy/sell/no-signal via a MagicMock ctx.
  4. engine.run          — rsi/macd run through _BUILTIN_MAP and produce trades.
  5. seed_builtin_strategies — creates rsi + macd Strategy rows (DB test).

compute_signal is a pure function — no Django, no DB, no network.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


def _candle(ts: int, c: float) -> dict:
    return {
        "ts": str(ts),
        "o": str(c),
        "h": str(c),
        "l": str(c),
        "c": str(c),
        "vol": "1.0",
        "volCcy": "1.0",
    }


def _candles_from(values: list[float]) -> list[dict]:
    return [_candle(1_000_000 + i * 60_000, v) for i, v in enumerate(values)]


# ---------------------------------------------------------------------------
# 1. RSI compute_signal — pure function
# ---------------------------------------------------------------------------

def test_rsi_insufficient_data_returns_none():
    """Fewer than period+1 closes → None."""
    from core.strategy.builtin.rsi import compute_signal

    assert compute_signal([100.0] * 10, period=14) is None


def test_rsi_oversold_buy():
    """Monotonic decline → RSI 0 (< oversold) → 'buy'."""
    from core.strategy.builtin.rsi import compute_signal

    closes = [100.0 - i for i in range(20)]  # strictly declining
    assert compute_signal(closes, period=14, oversold=30, overbought=70) == "buy"


def test_rsi_overbought_sell():
    """Monotonic rise → RSI 100 (> overbought) → 'sell'."""
    from core.strategy.builtin.rsi import compute_signal

    closes = [100.0 + i for i in range(20)]  # strictly rising
    assert compute_signal(closes, period=14, oversold=30, overbought=70) == "sell"


def test_rsi_neutral_no_signal():
    """Balanced up/down swings → RSI ~50 (within band) → None."""
    from core.strategy.builtin.rsi import compute_signal

    closes = [100.0 + (5 if i % 2 else -5) for i in range(20)]
    assert compute_signal(closes, period=14, oversold=30, overbought=70) is None


def test_rsi_value_bounds():
    """_rsi stays within [0, 100] for arbitrary input."""
    from core.strategy.builtin.rsi import _rsi

    closes = [100.0, 102.0, 101.0, 105.0, 103.0, 108.0, 107.0,
              110.0, 109.0, 112.0, 111.0, 115.0, 114.0, 117.0, 116.0]
    val = _rsi(closes, 14)
    assert val is not None
    assert 0.0 <= val <= 100.0


# ---------------------------------------------------------------------------
# 2. MACD compute_signal — pure function
# ---------------------------------------------------------------------------

def test_macd_insufficient_data_returns_none():
    """Fewer than slow+signal_period closes → None."""
    from core.strategy.builtin.macd import compute_signal

    assert compute_signal([100.0] * 10, fast=12, slow=26, signal_period=9) is None


def test_macd_flat_no_signal():
    """Flat prices → MACD and signal both 0, no crossover → None."""
    from core.strategy.builtin.macd import compute_signal

    assert compute_signal([100.0] * 60, fast=12, slow=26, signal_period=9) is None


def test_macd_bullish_crossover_buy():
    """Long decline then a reversal bar flips MACD above signal → 'buy'."""
    from core.strategy.builtin.macd import compute_signal

    # 40 declining bars push MACD below signal; the +bar reverses on the last bar.
    closes = [100.0 - i for i in range(40)] + [65.0]
    assert compute_signal(closes, fast=12, slow=26, signal_period=9) == "buy"


def test_macd_bearish_crossover_sell():
    """Long rise then a drop bar flips MACD below signal → 'sell'."""
    from core.strategy.builtin.macd import compute_signal

    closes = [60.0 + i for i in range(40)] + [95.0]
    assert compute_signal(closes, fast=12, slow=26, signal_period=9) == "sell"


def test_macd_ema_series_basic():
    """_ema_series length matches input and first element seeds with first price."""
    from core.strategy.builtin.macd import _ema_series

    series = _ema_series([10.0, 20.0, 30.0], 2)
    assert len(series) == 3
    assert series[0] == 10.0
    assert series[-1] > series[0]  # trending up


# ---------------------------------------------------------------------------
# 3. on_tick — MagicMock ctx
# ---------------------------------------------------------------------------

def test_rsi_on_tick_buy():
    from core.strategy.builtin.rsi import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = _candles_from([100.0 - i for i in range(20)])
    ctx.buy.return_value = "ORD_BUY"

    on_tick(ctx, {"period": 14, "oversold": 30, "overbought": 70, "sz": "0.001"})

    ctx.buy.assert_called_once_with("0.001")
    ctx.sell.assert_not_called()


def test_rsi_on_tick_sell():
    from core.strategy.builtin.rsi import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = _candles_from([100.0 + i for i in range(20)])
    ctx.sell.return_value = "ORD_SELL"

    on_tick(ctx, {"period": 14, "oversold": 30, "overbought": 70, "sz": "0.002"})

    ctx.sell.assert_called_once_with("0.002")
    ctx.buy.assert_not_called()


def test_rsi_on_tick_no_signal():
    from core.strategy.builtin.rsi import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = _candles_from([100.0 + (5 if i % 2 else -5) for i in range(20)])

    on_tick(ctx, {"period": 14, "oversold": 30, "overbought": 70, "sz": "0.001"})

    ctx.buy.assert_not_called()
    ctx.sell.assert_not_called()


def test_macd_on_tick_buy():
    from core.strategy.builtin.macd import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = _candles_from([100.0 - i for i in range(40)] + [65.0])
    ctx.buy.return_value = "ORD_BUY"

    on_tick(ctx, {"fast": 12, "slow": 26, "signal_period": 9, "sz": "0.001"})

    ctx.buy.assert_called_once_with("0.001")
    ctx.sell.assert_not_called()


def test_macd_on_tick_sell():
    from core.strategy.builtin.macd import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = _candles_from([60.0 + i for i in range(40)] + [95.0])
    ctx.sell.return_value = "ORD_SELL"

    on_tick(ctx, {"fast": 12, "slow": 26, "signal_period": 9, "sz": "0.003"})

    ctx.sell.assert_called_once_with("0.003")
    ctx.buy.assert_not_called()


def test_macd_on_tick_no_signal():
    from core.strategy.builtin.macd import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = _candles_from([100.0] * 60)

    on_tick(ctx, {"fast": 12, "slow": 26, "signal_period": 9, "sz": "0.001"})

    ctx.buy.assert_not_called()
    ctx.sell.assert_not_called()


# ---------------------------------------------------------------------------
# 4. engine.run — rsi/macd registered in _BUILTIN_MAP
# ---------------------------------------------------------------------------

def test_engine_runs_rsi_and_produces_trades():
    """Engine runs 'rsi' via _BUILTIN_MAP; decline→rise sequence yields buy+sell."""
    from core.backtest.engine import run

    # 20 declining (oversold→buy) then 20 rising (overbought→sell); trailing bars
    # give the last signal a next-bar open to fill against.
    values = [100.0 - i for i in range(20)] + [50.0 + i for i in range(20)]
    result = run("rsi", {"period": 14, "oversold": 30, "overbought": 70, "sz": "0.01"},
                 _candles_from(values))

    sides = {t["side"] for t in result["trades"]}
    assert "buy" in sides
    assert "sell" in sides


def test_engine_runs_macd_and_produces_buy():
    """Engine runs 'macd' via _BUILTIN_MAP; decline→reversal yields a buy."""
    from core.backtest.engine import run

    values = [100.0 - i for i in range(40)] + [65.0] * 6
    result = run("macd", {"fast": 12, "slow": 26, "signal_period": 9, "sz": "0.01"},
                 _candles_from(values))

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    assert buys, "Expected at least one buy trade from macd"


def test_engine_rsi_macd_in_builtin_map():
    """Registry contains the two new code_refs."""
    from core.backtest.engine import _BUILTIN_MAP

    assert _BUILTIN_MAP["rsi"] == "core.strategy.builtin.rsi"
    assert _BUILTIN_MAP["macd"] == "core.strategy.builtin.macd"


# ---------------------------------------------------------------------------
# 5. seed_builtin_strategies — creates rsi + macd rows
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seed_creates_rsi_and_macd():
    """seed_builtin_strategies creates rsi + macd built-in Strategy rows."""
    from django.core.management import call_command
    from core.strategy.models import Strategy

    call_command("seed_builtin_strategies")

    for code_ref in ("rsi", "macd"):
        s = Strategy.objects.get(code_ref=code_ref, source_type=Strategy.SOURCE_BUILTIN)
        assert s.is_builtin is True
        assert s.owner is None
        assert s.status == Strategy.STATUS_APPROVED
        assert s.visibility == Strategy.VISIBILITY_PUBLIC
        assert s.default_params  # non-empty


@pytest.mark.django_db
def test_seed_is_idempotent():
    """Running seed twice does not create duplicate rows."""
    from django.core.management import call_command
    from core.strategy.models import Strategy

    call_command("seed_builtin_strategies")
    call_command("seed_builtin_strategies")

    for code_ref in ("dual_ma", "rsi", "macd"):
        assert Strategy.objects.filter(
            code_ref=code_ref, source_type=Strategy.SOURCE_BUILTIN
        ).count() == 1
