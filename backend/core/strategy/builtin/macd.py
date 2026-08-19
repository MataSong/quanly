"""MACD (Moving Average Convergence Divergence) built-in strategy.

Interface contract for P3-C runner:

    from core.strategy.builtin.macd import on_tick

    on_tick(ctx, params)

ctx protocol (duck-typed, implemented by the runner):
    ctx.candles() -> list[dict]  — [{ts, o, h, l, c, vol, volCcy}, ...]  oldest-first
    ctx.buy(sz, ord_type="market", px=None) -> str   — returns ordId
    ctx.sell(sz, ord_type="market", px=None) -> str  — returns ordId
    ctx.log(level, message)                          — emit a StrategyLog entry

params keys (with defaults):
    fast: int = 12           — fast EMA period (bars)
    slow: int = 26           — slow EMA period (bars)
    signal_period: int = 9   — signal-line EMA period (bars)
    sz: str = "0.001"        — order size per signal

Algorithm (standard MACD):
    - MACD line = EMA(fast) - EMA(slow) over the close series.
    - Signal line = EMA(signal_period) of the MACD line.
    - MACD crosses ABOVE signal → BUY (bullish crossover).
    - MACD crosses BELOW signal → SELL (bearish crossover).
    - Otherwise no signal. Insufficient data → None.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quanly.strategy.macd")


def _ema_series(prices: list[float], period: int) -> list[float]:
    """Return the EMA series for `prices` with the given period.

    Seeds with the first price (standard recursive EMA seeding) and applies
    multiplier k = 2 / (period + 1). Output length == len(prices).
    Empty input → empty list.
    """
    if not prices or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    ema = prices[0]
    out = [ema]
    for price in prices[1:]:
        ema = price * k + ema * (1.0 - k)
        out.append(ema)
    return out


def _macd_lines(
    closes: list[float],
    fast: int,
    slow: int,
    signal_period: int,
) -> tuple[list[float], list[float]] | None:
    """Return (macd_line, signal_line) series, or None if insufficient data.

    Both returned series are aligned to the tail so that the last element of
    each corresponds to the most recent bar. We need at least
    (slow + signal_period) closes for the signal line to be meaningful.
    """
    if fast <= 0 or slow <= 0 or signal_period <= 0:
        return None
    if len(closes) < slow + signal_period:
        return None

    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema_series(macd_line, signal_period)
    return macd_line, signal_line


def compute_signal(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> str | None:
    """Compute a MACD crossover signal from a list of close prices.

    Returns:
        "buy"  — MACD line just crossed above the signal line
        "sell" — MACD line just crossed below the signal line
        None   — no crossover or insufficient data

    Pure function — no side effects, fully unit-testable.
    """
    lines = _macd_lines(closes, fast, slow, signal_period)
    if lines is None:
        return None
    macd_line, signal_line = lines
    if len(macd_line) < 2 or len(signal_line) < 2:
        return None

    macd_prev, macd_now = macd_line[-2], macd_line[-1]
    sig_prev, sig_now = signal_line[-2], signal_line[-1]

    # Bullish crossover: MACD was <= signal, now MACD > signal.
    if macd_prev <= sig_prev and macd_now > sig_now:
        return "buy"

    # Bearish crossover: MACD was >= signal, now MACD < signal.
    if macd_prev >= sig_prev and macd_now < sig_now:
        return "sell"

    return None


def on_tick(ctx: Any, params: dict[str, Any]) -> None:
    """Strategy entry point called by the runner on each tick.

    ctx: runner-provided context object with candles/buy/sell/log methods.
    params: strategy parameters dict (from StrategyRun.params).
    """
    fast: int = int(params.get("fast", 12))
    slow: int = int(params.get("slow", 26))
    signal_period: int = int(params.get("signal_period", 9))
    sz: str = str(params.get("sz", "0.001"))

    candles = ctx.candles()
    if not candles:
        ctx.log("warn", "macd: no candle data received")
        return

    closes = [float(c["c"]) for c in candles]
    signal = compute_signal(closes, fast=fast, slow=slow, signal_period=signal_period)

    if signal == "buy":
        ctx.log("buy", f"macd: bullish crossover (fast{fast}/slow{slow}/sig{signal_period}), buying {sz}")
        try:
            ord_id = ctx.buy(sz)
            ctx.log("info", f"macd: buy order placed ordId={ord_id}")
        except Exception as exc:
            ctx.log("error", f"macd: buy failed: {exc}")

    elif signal == "sell":
        ctx.log("sell", f"macd: bearish crossover (fast{fast}/slow{slow}/sig{signal_period}), selling {sz}")
        try:
            ord_id = ctx.sell(sz)
            ctx.log("info", f"macd: sell order placed ordId={ord_id}")
        except Exception as exc:
            ctx.log("error", f"macd: sell failed: {exc}")

    else:
        ctx.log("info", f"macd: no signal (fast={fast}, slow={slow}, signal={signal_period})")
