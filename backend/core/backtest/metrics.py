"""Backtest metrics: pure functions, no external dependencies.

All inputs are plain Python lists/dicts.  Safe to unit-test without Django.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

# Approximate number of bars per year for common timeframes.
# Used to annualise returns and Sharpe ratio.
_BARS_PER_YEAR: dict[str, float] = {
    "1m":  525_600.0,
    "3m":  175_200.0,
    "5m":  105_120.0,
    "15m":  35_040.0,
    "30m":  17_520.0,
    "1H":   8_760.0,
    "2H":   4_380.0,
    "4H":   2_190.0,
    "6H":   1_460.0,
    "12H":    730.0,
    "1D":     365.0,
    "1W":      52.0,
    "1M":      12.0,
}
_DEFAULT_BARS_PER_YEAR = 365.0  # fallback: treat unknown bars as daily


def _bars_per_year(bar: str) -> float:
    return _BARS_PER_YEAR.get(bar, _DEFAULT_BARS_PER_YEAR)


def compute_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    bar: str = "1D",
) -> dict[str, Any]:
    """Compute summary performance metrics from an equity curve and trade list.

    Parameters
    ----------
    equity_curve:
        List of ``{ts: int, equity: float}`` dicts, oldest-first.
    trades:
        List of trade dicts produced by the engine (keys: side, ts, price, sz, fee, pnl).
    bar:
        Timeframe string (e.g. "1m", "1H", "1D") used for annualisation.

    Returns
    -------
    dict with keys:
        total_return, annualized_return, max_drawdown, sharpe,
        win_rate, profit_factor, trade_count
    """
    if not equity_curve:
        return _empty_metrics()

    equities = [float(p["equity"]) for p in equity_curve]
    init_eq = equities[0]
    final_eq = equities[-1]
    n_bars = len(equities)

    # --- total return ---
    total_return = (final_eq - init_eq) / init_eq if init_eq else 0.0

    # --- annualised return (CAGR-like, compound) ---
    ann_factor = _bars_per_year(bar)
    if n_bars > 1 and init_eq > 0:
        # (1 + r)^(ann_factor/n_bars) - 1
        ratio = final_eq / init_eq
        if ratio > 0:
            annualized_return = math.pow(ratio, ann_factor / n_bars) - 1.0
        else:
            annualized_return = -1.0
    else:
        annualized_return = 0.0

    # --- max drawdown ---
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # --- bar returns for Sharpe ---
    bar_returns = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev > 0:
            bar_returns.append((equities[i] - prev) / prev)

    if len(bar_returns) >= 2:
        try:
            mean_r = statistics.mean(bar_returns)
            std_r = statistics.stdev(bar_returns)
            sharpe = (mean_r / std_r * math.sqrt(ann_factor)) if std_r > 0 else 0.0
        except statistics.StatisticsError:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # --- trade statistics ---
    closed_trades = [t for t in trades if t.get("side") == "sell"]
    trade_count = len(trades)
    win_rate = 0.0
    profit_factor = 0.0

    if closed_trades:
        wins = [t["pnl"] for t in closed_trades if t.get("pnl", 0) > 0]
        losses = [t["pnl"] for t in closed_trades if t.get("pnl", 0) <= 0]
        win_rate = len(wins) / len(closed_trades)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6),
        "max_drawdown": round(max_dd, 6),
        "sharpe": round(sharpe, 4),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if math.isfinite(profit_factor) else None,
        "trade_count": trade_count,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_return": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
        "win_rate": 0.0,
        "profit_factor": None,
        "trade_count": 0,
    }
