"""RSI (Relative Strength Index) built-in strategy.

Interface contract for P3-C runner:

    from core.strategy.builtin.rsi import on_tick

    on_tick(ctx, params)

ctx protocol (duck-typed, implemented by the runner):
    ctx.candles() -> list[dict]  — [{ts, o, h, l, c, vol, volCcy}, ...]  oldest-first
    ctx.buy(sz, ord_type="market", px=None) -> str   — returns ordId
    ctx.sell(sz, ord_type="market", px=None) -> str  — returns ordId
    ctx.log(level, message)                          — emit a StrategyLog entry

params keys (with defaults):
    period: int = 14        — RSI lookback window (bars)
    oversold: float = 30    — RSI below this → BUY
    overbought: float = 70  — RSI above this → SELL
    sz: str = "0.001"       — order size per signal

Algorithm (standard Wilder-style simple-average RSI):
    - Over the last `period` close-to-close changes, average the gains and the
      losses separately.
    - RS = avg_gain / avg_loss; RSI = 100 - 100 / (1 + RS).
    - RSI < oversold → BUY (oversold rebound).
    - RSI > overbought → SELL (overbought pullback).
    - Otherwise no signal. Insufficient data (< period + 1 closes) → None.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quanly.strategy.rsi")


def _rsi(closes: list[float], period: int) -> float | None:
    """Return the RSI value over the last `period` price changes, or None.

    Uses simple (arithmetic) averages of gains/losses over the window.
    Requires at least (period + 1) close prices to form `period` changes.
    """
    if period <= 0 or len(closes) < period + 1:
        return None

    # The last `period` close-to-close changes.
    window = closes[-(period + 1):]
    gains = 0.0
    losses = 0.0
    for prev, cur in zip(window[:-1], window[1:]):
        change = cur - prev
        if change > 0:
            gains += change
        else:
            losses += -change

    avg_gain = gains / period
    avg_loss = losses / period

    if avg_loss == 0:
        # No losses in the window: fully overbought (unless flat).
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def compute_signal(
    closes: list[float],
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> str | None:
    """Compute an RSI-based signal from a list of close prices.

    Returns:
        "buy"  — RSI < oversold (oversold condition)
        "sell" — RSI > overbought (overbought condition)
        None   — RSI within band, or insufficient data

    Pure function — no side effects, fully unit-testable.
    Requires at least (period + 1) data points.
    """
    rsi = _rsi(closes, period)
    if rsi is None:
        return None

    if rsi < oversold:
        return "buy"
    if rsi > overbought:
        return "sell"
    return None


def on_tick(ctx: Any, params: dict[str, Any]) -> None:
    """Strategy entry point called by the runner on each tick.

    ctx: runner-provided context object with candles/buy/sell/log methods.
    params: strategy parameters dict (from StrategyRun.params).
    """
    period: int = int(params.get("period", 14))
    oversold: float = float(params.get("oversold", 30))
    overbought: float = float(params.get("overbought", 70))
    sz: str = str(params.get("sz", "0.001"))

    candles = ctx.candles()
    if not candles:
        ctx.log("warn", "rsi: no candle data received")
        return

    closes = [float(c["c"]) for c in candles]
    signal = compute_signal(closes, period=period, oversold=oversold, overbought=overbought)

    if signal == "buy":
        ctx.log("buy", f"rsi: oversold (RSI<{oversold}) period={period}, buying {sz}")
        try:
            ord_id = ctx.buy(sz)
            ctx.log("info", f"rsi: buy order placed ordId={ord_id}")
        except Exception as exc:
            ctx.log("error", f"rsi: buy failed: {exc}")

    elif signal == "sell":
        ctx.log("sell", f"rsi: overbought (RSI>{overbought}) period={period}, selling {sz}")
        try:
            ord_id = ctx.sell(sz)
            ctx.log("info", f"rsi: sell order placed ordId={ord_id}")
        except Exception as exc:
            ctx.log("error", f"rsi: sell failed: {exc}")

    else:
        ctx.log("info", f"rsi: no signal (period={period}, band={oversold}-{overbought})")
