"""Backtest engine: run a strategy on historical candles and produce results.

Zero external calls during backtest — all market data is pre-loaded candles.
Matching rule (avoids look-ahead bias):
  - Signal computed on bar i uses data up to bar i (close).
  - Simulated fill uses bar i+1's OPEN price.
  - The last bar's signal is discarded (no next bar to fill against).
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from core.backtest.ctx import BacktestContext
from core.backtest.metrics import compute_metrics

logger = logging.getLogger("quanly.backtest")

# Registry of supported builtin strategy code_refs.
_BUILTIN_MAP: dict[str, str] = {
    "dual_ma": "core.strategy.builtin.dual_ma",
    "rsi": "core.strategy.builtin.rsi",
    "macd": "core.strategy.builtin.macd",
}


def _load_on_tick(code_ref: str):
    """Import and return the on_tick function for the given code_ref.

    Raises ValueError for unknown code_refs.
    """
    module_path = _BUILTIN_MAP.get(code_ref)
    if module_path is None:
        raise ValueError(
            f"Unknown strategy code_ref {code_ref!r}. "
            f"Known builtins: {list(_BUILTIN_MAP)}"
        )
    module = importlib.import_module(module_path)
    return module.on_tick


def run(
    code_ref: str,
    params: dict[str, Any],
    candles: list[dict[str, Any]],
    init_cash: float = 10_000.0,
    fee_rate: float = 0.001,
    bar: str = "1D",
) -> dict[str, Any]:
    """Execute a backtest and return equity_curve, trades, and metrics.

    Parameters
    ----------
    code_ref:
        Strategy identifier (e.g. "dual_ma").
    params:
        Strategy parameters dict passed verbatim to on_tick.
    candles:
        Oldest-first list of candle dicts: {ts, o, h, l, c, vol, volCcy}.
        All numeric fields may be str (as returned by OKX).
    init_cash:
        Starting cash in quote currency.
    fee_rate:
        Taker fee as a fraction (e.g. 0.001 = 0.1 %).
    bar:
        Timeframe string used only for annualisation in metrics.

    Returns
    -------
    dict with keys: equity_curve, trades, metrics
    """
    on_tick = _load_on_tick(code_ref)

    ctx = BacktestContext(candles)
    cash = float(init_cash)
    position: float = 0.0   # base currency held (e.g. BTC)
    avg_cost: float = 0.0   # average cost basis of current position

    equity_curve: list[dict[str, Any]] = []
    raw_trades: list[dict[str, Any]] = []

    n = len(candles)
    if n < 2:
        logger.warning("backtest: not enough candles (%d) to run", n)
        return {
            "equity_curve": [],
            "trades": [],
            "metrics": compute_metrics([], [], bar=bar),
        }

    # Determine the minimum start index required by the strategy.
    # dual_ma needs slow_period + 1 bars; we default to 1 to be safe and let
    # on_tick decide internally via compute_signal (it returns None if not ready).
    start_index = 1  # need at least index 1 so bar i+1 exists for fill

    # 净值曲线从第 0 根 bar 的起始净值(纯现金)起,让曲线覆盖完整区间起点。
    equity_curve.append({"ts": int(candles[0]["ts"]), "equity": round(cash, 8)})

    for i in range(start_index, n):
        ctx.advance(i)
        ctx._clear_signals()
        on_tick(ctx, params)
        signals = ctx._pop_signals()

        # Record equity at this bar's close BEFORE processing fills.
        close_price = float(candles[i]["c"])
        equity = cash + position * close_price
        equity_curve.append({"ts": int(candles[i]["ts"]), "equity": round(equity, 8)})

        # Fills use NEXT bar's open — check next bar exists.
        if i + 1 >= n:
            # Last bar: no next bar, discard signals.
            continue

        fill_price = float(candles[i + 1]["o"])
        fill_ts = int(candles[i + 1]["ts"])

        for sig in signals:
            side = sig["side"]
            sz = float(sig["sz"])

            if side == "buy":
                cost = fill_price * sz
                fee = cost * fee_rate
                total_cost = cost + fee
                if total_cost > cash:
                    # Not enough cash — skip this signal.
                    logger.debug(
                        "backtest: buy skipped — insufficient cash %.4f < %.4f",
                        cash, total_cost,
                    )
                    continue
                # Update average cost basis
                total_held = position * avg_cost + cost
                position += sz
                avg_cost = total_held / position if position > 0 else 0.0
                cash -= total_cost
                raw_trades.append({
                    "side": "buy",
                    "ts": fill_ts,
                    "price": fill_price,
                    "sz": sz,
                    "fee": round(fee, 8),
                    "pnl": 0.0,
                })
                logger.debug(
                    "backtest: BUY sz=%.4f px=%.4f cash=%.4f pos=%.4f",
                    sz, fill_price, cash, position,
                )

            elif side == "sell":
                if position <= 0:
                    # No position to sell — skip.
                    logger.debug("backtest: sell skipped — no position")
                    continue
                sell_sz = min(sz, position)
                proceeds = fill_price * sell_sz
                fee = proceeds * fee_rate
                net_proceeds = proceeds - fee
                # Realised PnL for this partial close.
                cost_basis = avg_cost * sell_sz
                pnl = net_proceeds - cost_basis
                position -= sell_sz
                cash += net_proceeds
                if position <= 1e-12:
                    position = 0.0
                    avg_cost = 0.0
                raw_trades.append({
                    "side": "sell",
                    "ts": fill_ts,
                    "price": fill_price,
                    "sz": sell_sz,
                    "fee": round(fee, 8),
                    "pnl": round(pnl, 8),
                })
                logger.debug(
                    "backtest: SELL sz=%.4f px=%.4f cash=%.4f pnl=%.4f",
                    sell_sz, fill_price, cash, pnl,
                )

    metrics = compute_metrics(equity_curve, raw_trades, bar=bar)

    return {
        "equity_curve": equity_curve,
        "trades": raw_trades,
        "metrics": metrics,
    }
