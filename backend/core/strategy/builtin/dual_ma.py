"""Dual Moving Average (dual_ma) built-in strategy.

Interface contract for P3-C runner:

    from core.strategy.builtin.dual_ma import on_tick

    on_tick(ctx, params)

ctx protocol (duck-typed, implemented by the runner):
    ctx.candles() -> list[dict]  — [{ts, o, h, l, c, vol, volCcy}, ...]  oldest-first
    ctx.buy(sz, ord_type="market", px=None) -> str   — returns ordId
    ctx.sell(sz, ord_type="market", px=None) -> str  — returns ordId
    ctx.log(level, message)                          — emit a StrategyLog entry

params keys (with defaults):
    fast_period: int = 5    — fast MA window (bars)
    slow_period: int = 20   — slow MA window (bars)
    sz: str = "0.001"       — order size per signal

Algorithm:
    - Compute fast MA and slow MA from close prices.
    - Golden cross (fast crosses above slow) → BUY signal.
    - Death cross (fast crosses below slow) → SELL signal.
    - No signal when not enough data or when MA relationship unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quanly.strategy.dual_ma")


def _moving_average(prices: list[float], period: int) -> float | None:
    """Return simple moving average of the last `period` values, or None if insufficient data."""
    if len(prices) < period:
        return None
    window = prices[-period:]
    return sum(window) / period


def compute_signal(
    closes: list[float],
    fast_period: int = 5,
    slow_period: int = 20,
) -> str | None:
    """Compute MA crossover signal from a list of close prices.

    Returns:
        "buy"  — golden cross: fast MA just crossed above slow MA
        "sell" — death cross: fast MA just crossed below slow MA
        None   — no crossover or insufficient data

    This is a pure function — no side effects, fully unit-testable.
    Requires at least (slow_period + 1) data points to detect a crossover.
    """
    if len(closes) < slow_period + 1:
        return None

    # Current bar
    fast_now = _moving_average(closes, fast_period)
    slow_now = _moving_average(closes, slow_period)

    # Previous bar (drop the last element)
    prev_closes = closes[:-1]
    fast_prev = _moving_average(prev_closes, fast_period)
    slow_prev = _moving_average(prev_closes, slow_period)

    if any(v is None for v in (fast_now, slow_now, fast_prev, slow_prev)):
        return None

    # Golden cross: fast was <= slow, now fast > slow
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "buy"

    # Death cross: fast was >= slow, now fast < slow
    if fast_prev >= slow_prev and fast_now < slow_now:
        return "sell"

    return None


def on_tick(ctx: Any, params: dict[str, Any]) -> None:
    """Strategy entry point called by the runner on each tick.

    ctx: runner-provided context object with candles/buy/sell/log methods.
    params: strategy parameters dict (from StrategyRun.params).
    """
    fast_period: int = int(params.get("fast_period", 5))
    slow_period: int = int(params.get("slow_period", 20))
    sz: str = str(params.get("sz", "0.001"))

    candles = ctx.candles()
    if not candles:
        ctx.log("warn", "dual_ma: no candle data received")
        return

    closes = [float(c["c"]) for c in candles]
    signal = compute_signal(closes, fast_period=fast_period, slow_period=slow_period)

    if signal == "buy":
        ctx.log("buy", f"dual_ma: golden cross — fast{fast_period} > slow{slow_period}, buying {sz}")
        try:
            ord_id = ctx.buy(sz)
            ctx.log("info", f"dual_ma: buy order placed ordId={ord_id}")
        except Exception as exc:
            ctx.log("error", f"dual_ma: buy failed: {exc}")

    elif signal == "sell":
        ctx.log("sell", f"dual_ma: death cross — fast{fast_period} < slow{slow_period}, selling {sz}")
        try:
            ord_id = ctx.sell(sz)
            ctx.log("info", f"dual_ma: sell order placed ordId={ord_id}")
        except Exception as exc:
            ctx.log("error", f"dual_ma: sell failed: {exc}")

    else:
        ctx.log("info", f"dual_ma: no signal (fast={fast_period}, slow={slow_period})")
