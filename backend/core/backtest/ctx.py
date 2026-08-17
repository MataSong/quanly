"""BacktestContext: duck-typed ctx injected into strategy on_tick during backtest.

Mirrors the runtime runner ctx interface so the same on_tick code works in both
live and backtest modes.  All state is in-memory; no DB, no OKX calls.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quanly.backtest")


class BacktestContext:
    """Provides the same ctx interface as the live runner but operates on stored candles.

    Usage:
        ctx = BacktestContext(candles)
        for i in range(start_index, len(candles)):
            ctx.advance(i)
            ctx._clear_signals()
            on_tick(ctx, params)
            signals = ctx._pop_signals()
    """

    def __init__(self, history: list[dict[str, Any]]) -> None:
        # history: oldest-first list of candle dicts with ts/o/h/l/c/vol/volCcy (all str from OKX)
        self._history = history
        self._cursor: int = 0
        self._signals: list[dict[str, Any]] = []
        self._logs: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Cursor management
    # ------------------------------------------------------------------

    def advance(self, i: int) -> None:
        """Set cursor to index i (inclusive — candles() returns history[:i+1])."""
        self._cursor = i

    # ------------------------------------------------------------------
    # ctx protocol — called by on_tick
    # ------------------------------------------------------------------

    def candles(self) -> list[dict[str, Any]]:
        """Return all candles up to and including the current bar (oldest-first)."""
        return self._history[: self._cursor + 1]

    def price(self) -> float:
        """Return the close price of the current bar."""
        return float(self._history[self._cursor]["c"])

    def buy(self, sz: Any, ord_type: str = "market", px: Any = None) -> str:
        """Record a buy signal for the current bar; returns a fake ordId."""
        sz_f = float(sz)
        signal = {
            "side": "buy",
            "ts": int(self._history[self._cursor]["ts"]),
            "sz": sz_f,
            "ord_type": ord_type,
            "px": float(px) if px is not None else None,
        }
        self._signals.append(signal)
        return f"bt-buy-{self._cursor}"

    def sell(self, sz: Any, ord_type: str = "market", px: Any = None) -> str:
        """Record a sell signal for the current bar; returns a fake ordId."""
        sz_f = float(sz)
        signal = {
            "side": "sell",
            "ts": int(self._history[self._cursor]["ts"]),
            "sz": sz_f,
            "ord_type": ord_type,
            "px": float(px) if px is not None else None,
        }
        self._signals.append(signal)
        return f"bt-sell-{self._cursor}"

    def log(self, level: str, message: str) -> None:
        """Record a log entry in memory (no DB write during backtest)."""
        self._logs.append({"level": level, "message": message, "bar": self._cursor})
        logger.debug("backtest log [%s] bar=%d: %s", level, self._cursor, message)

    # ------------------------------------------------------------------
    # Internal helpers used by the engine
    # ------------------------------------------------------------------

    def _clear_signals(self) -> None:
        """Clear pending signals before calling on_tick for the next bar."""
        self._signals = []

    def _pop_signals(self) -> list[dict[str, Any]]:
        """Return and clear the signals accumulated during the last on_tick call."""
        signals = list(self._signals)
        self._signals = []
        return signals
