"""回测绩效指标:基于 equity_curve(净值序列)与 trades(成交)计算。

覆盖市面主流量化指标:收益、风险、风险调整收益、交易统计。
无外部依赖,纯 Python(bar 级收益按 sqrt(周期数) 年化,mock 场景够用)。
"""
import math

# 1 分钟 bar 一年的根数(365*24*60),用于年化
BARS_PER_YEAR = 365 * 24 * 60


def _returns(equity):
    out = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        out.append((equity[i] - prev) / prev if prev else 0.0)
    return out


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def compute_metrics(result, bar="1m"):
    curve = [p["equity"] for p in result["equity_curve"]]
    trades = result["trades"]
    initial = result["initial_capital"]
    n = len(curve)
    if n == 0:
        return {}

    final = curve[-1]
    total_return = (final - initial) / initial if initial else 0.0
    periods_per_year = BARS_PER_YEAR  # 假设 1m;其它周期可按需缩放
    years = n / periods_per_year if periods_per_year else 0
    # 年化仅在样本足够长(≥1 天)时用复利公式,否则退化为总收益,避免 1/years 过大导致溢出
    if years >= (1 / 365) and initial > 0 and final > 0:
        annual_return = (final / initial) ** (1 / years) - 1
    else:
        annual_return = total_return

    # 最大回撤 + 持续期
    peak = curve[0]
    max_dd = 0.0
    dd_start = 0
    max_dd_dur = 0
    cur_dd_start = 0
    for i, v in enumerate(curve):
        if v > peak:
            peak = v
            cur_dd_start = i
        dd = (v - peak) / peak if peak else 0.0
        if dd < max_dd:
            max_dd = dd
            dd_start = cur_dd_start
        max_dd_dur = max(max_dd_dur, i - cur_dd_start)

    rets = _returns(curve)
    vol = _std(rets)
    annual_vol = vol * math.sqrt(periods_per_year)
    downside = _std([r for r in rets if r < 0])
    annual_downside = downside * math.sqrt(periods_per_year)

    mean_ret = sum(rets) / len(rets) if rets else 0.0
    sharpe = (mean_ret / vol * math.sqrt(periods_per_year)) if vol else 0.0
    sortino = (mean_ret / downside * math.sqrt(periods_per_year)) if downside else 0.0
    calmar = (annual_return / abs(max_dd)) if max_dd else 0.0

    # 交易统计(以卖出成交的 pnl 计盈亏)
    closed = [t for t in trades if t.get("side") == "sell" and "pnl" in t]
    wins = [t["pnl"] for t in closed if t["pnl"] > 0]
    losses = [t["pnl"] for t in closed if t["pnl"] <= 0]
    win_rate = len(wins) / len(closed) if closed else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss else (gross_win if gross_win else 0.0)

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "final_equity": round(final, 2),
        "max_drawdown": round(max_dd, 4),
        "max_dd_duration": max_dd_dur,
        "annual_volatility": round(annual_vol, 4),
        "downside_volatility": round(annual_downside, 4),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "calmar": round(calmar, 3),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 3),
        "trade_count": len(trades),
        "closed_trades": len(closed),
        "win_count": len(wins),
        "loss_count": len(losses),
        "avg_win": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 4) if losses else 0.0,
        "max_win": round(max(wins), 4) if wins else 0.0,
        "max_loss": round(min(losses), 4) if losses else 0.0,
    }
