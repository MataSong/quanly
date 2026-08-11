from apps.backtest.metrics import compute_metrics


def _curve(values):
    return {
        "equity_curve": [{"ts": i, "equity": v} for i, v in enumerate(values)],
        "trades": [],
        "initial_capital": values[0],
    }


def test_flat_curve_zero_return_zero_dd():
    m = compute_metrics(_curve([10000] * 10))
    assert m["total_return"] == 0.0
    assert m["max_drawdown"] == 0.0
    assert m["sharpe"] == 0.0


def test_rising_curve_positive_return():
    m = compute_metrics(_curve([10000, 10100, 10200, 10300, 10400]))
    assert m["total_return"] > 0
    assert m["final_equity"] == 10400


def test_drawdown_detected():
    # 涨到 11000 再跌到 9900 -> 最大回撤约 -10%
    m = compute_metrics(_curve([10000, 11000, 10500, 9900, 10200]))
    assert m["max_drawdown"] < 0
    assert abs(m["max_drawdown"] - (-0.1)) < 0.01


def test_trade_stats():
    r = {
        "equity_curve": [{"ts": 0, "equity": 10000}, {"ts": 1, "equity": 10100}],
        "initial_capital": 10000,
        "trades": [
            {"side": "buy", "price": 100, "sz": 1, "fee": 0},
            {"side": "sell", "price": 110, "sz": 1, "fee": 0, "pnl": 10},
            {"side": "sell", "price": 90, "sz": 1, "fee": 0, "pnl": -5},
        ],
    }
    m = compute_metrics(r)
    assert m["closed_trades"] == 2
    assert m["win_rate"] == 0.5
    assert m["win_count"] == 1 and m["loss_count"] == 1
    assert m["profit_factor"] == 2.0  # 10 / 5
