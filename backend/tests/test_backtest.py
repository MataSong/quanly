"""Tests for P4-A: Backtest backend.

Coverage:
  1. metrics.py — pure function unit tests (no Django, no DB).
  2. engine.py  — dual_ma strategy, golden/death cross, no look-ahead.
  3. API permissions — backtest:create required; multi-tenant isolation.
  4. run_backtest Celery task — fetch_range mocked, task stores results.

All OKX calls are unittest.mock stubs — zero real external calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User

from core.accounts.models import Role, UserRole
from core.strategy.models import Strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username: str, perms: list[str] | None = None) -> User:
    user = User.objects.create_user(username, password="pw")
    if perms:
        role = Role.objects.create(name=f"role_{username}", permissions=perms)
        UserRole.objects.create(user=user, role=role)
    return user


def _make_strategy(code_ref: str = "dual_ma") -> Strategy:
    return Strategy.objects.get_or_create(
        code_ref=code_ref,
        defaults={
            "name": "Dual MA",
            "source_type": Strategy.SOURCE_BUILTIN,
            "is_builtin": True,
            "default_params": {"fast_period": 5, "slow_period": 20, "sz": "0.001"},
        },
    )[0]


def _candle(ts: int, o: float, h: float, l: float, c: float) -> dict:
    return {
        "ts": str(ts),
        "o": str(o),
        "h": str(h),
        "l": str(l),
        "c": str(c),
        "vol": "1.0",
        "volCcy": "1.0",
    }


# ---------------------------------------------------------------------------
# 1. metrics.py pure-function tests
# ---------------------------------------------------------------------------

def test_metrics_total_return():
    """total_return = (final - init) / init."""
    from core.backtest.metrics import compute_metrics

    curve = [{"ts": i * 1000, "equity": float(v)} for i, v in enumerate([10000, 10500, 11000])]
    m = compute_metrics(curve, [], bar="1D")
    assert abs(m["total_return"] - 0.1) < 1e-6


def test_metrics_zero_equity_curve():
    """Empty equity curve returns zeros."""
    from core.backtest.metrics import compute_metrics

    m = compute_metrics([], [], bar="1D")
    assert m["total_return"] == 0.0
    assert m["trade_count"] == 0


def test_metrics_max_drawdown():
    """max_drawdown computed correctly from peak-to-trough."""
    from core.backtest.metrics import compute_metrics

    # 10000 → 12000 → 6000: drawdown = (12000-6000)/12000 = 0.5
    curve = [
        {"ts": 0, "equity": 10000.0},
        {"ts": 1, "equity": 12000.0},
        {"ts": 2, "equity": 6000.0},
    ]
    m = compute_metrics(curve, [], bar="1D")
    assert abs(m["max_drawdown"] - 0.5) < 1e-6


def test_metrics_max_drawdown_no_drawdown():
    """Monotonically increasing equity → max_drawdown = 0."""
    from core.backtest.metrics import compute_metrics

    curve = [{"ts": i, "equity": float(10000 + i * 100)} for i in range(10)]
    m = compute_metrics(curve, [], bar="1D")
    assert m["max_drawdown"] == 0.0


def test_metrics_win_rate():
    """win_rate = winning sells / total sells."""
    from core.backtest.metrics import compute_metrics

    curve = [{"ts": i, "equity": 10000.0} for i in range(5)]
    trades = [
        {"side": "buy",  "ts": 1, "price": 100.0, "sz": 1.0, "fee": 0.1, "pnl": 0.0},
        {"side": "sell", "ts": 2, "price": 110.0, "sz": 1.0, "fee": 0.1, "pnl": 9.8},   # win
        {"side": "buy",  "ts": 3, "price": 100.0, "sz": 1.0, "fee": 0.1, "pnl": 0.0},
        {"side": "sell", "ts": 4, "price":  90.0, "sz": 1.0, "fee": 0.1, "pnl": -10.1},  # loss
    ]
    m = compute_metrics(curve, trades, bar="1D")
    assert m["win_rate"] == 0.5
    assert m["trade_count"] == 4


def test_metrics_profit_factor():
    """profit_factor = gross_profit / gross_loss."""
    from core.backtest.metrics import compute_metrics

    curve = [{"ts": i, "equity": 10000.0} for i in range(3)]
    trades = [
        {"side": "sell", "ts": 1, "price": 110.0, "sz": 1.0, "fee": 0.0, "pnl": 20.0},
        {"side": "sell", "ts": 2, "price":  90.0, "sz": 1.0, "fee": 0.0, "pnl": -10.0},
    ]
    m = compute_metrics(curve, trades, bar="1D")
    assert abs(m["profit_factor"] - 2.0) < 1e-4


def test_metrics_sharpe_flat():
    """Flat equity (zero std) → sharpe = 0."""
    from core.backtest.metrics import compute_metrics

    curve = [{"ts": i, "equity": 10000.0} for i in range(20)]
    m = compute_metrics(curve, [], bar="1D")
    assert m["sharpe"] == 0.0


def test_metrics_annualized_return_single_bar():
    """Single-bar curve → annualized_return = 0."""
    from core.backtest.metrics import compute_metrics

    curve = [{"ts": 0, "equity": 10000.0}]
    m = compute_metrics(curve, [], bar="1D")
    assert m["annualized_return"] == 0.0


# ---------------------------------------------------------------------------
# 2. engine.py — dual_ma integration
# ---------------------------------------------------------------------------

def _build_crossover_candles(n_base: int = 25) -> list[dict]:
    """Build a candle sequence that triggers a golden cross then a death cross.

    Layout (1-indexed bar numbers):
      bars 1..n_base      : price = 100 (flat → both MAs equal)
      bar  n_base+1       : price = 200 (spike → fast MA jumps → golden cross BUY signal)
      bars n_base+2..+6   : price = 200 (hold to stabilise MAs above)
      bar  n_base+7       : price = 50  (crash → fast MA drops → death cross SELL signal)
      bar  n_base+8       : price = 50  (provides next-bar open for the sell fill)
    """
    candles = []
    t = 1_000_000
    step = 60_000  # 1-minute steps

    # flat baseline
    for _ in range(n_base):
        candles.append(_candle(t, 100.0, 100.0, 100.0, 100.0))
        t += step

    # spike → golden cross signal on this bar
    candles.append(_candle(t, 100.0, 200.0, 100.0, 200.0))
    t += step

    # hold high
    for _ in range(5):
        candles.append(_candle(t, 200.0, 200.0, 200.0, 200.0))
        t += step

    # crash → death cross signal on this bar
    candles.append(_candle(t, 200.0, 200.0, 50.0, 50.0))
    t += step

    # one more bar so the death cross sell has a next-bar open to fill at
    candles.append(_candle(t, 50.0, 50.0, 50.0, 50.0))
    t += step

    return candles


def test_engine_has_buy_and_sell_trades():
    """Engine produces at least one buy and one sell trade on crossover candles."""
    from core.backtest.engine import run

    candles = _build_crossover_candles()
    result = run("dual_ma", {"fast_period": 3, "slow_period": 5, "sz": "0.01"}, candles)

    buys  = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert buys,  "Expected at least one buy trade"
    assert sells, "Expected at least one sell trade"


def test_engine_equity_curve_length():
    """equity_curve 含 bar0 初始净值点 + 每根后续 bar 一个点 = n 个点。"""
    from core.backtest.engine import run

    candles = _build_crossover_candles()
    result = run("dual_ma", {"fast_period": 3, "slow_period": 5, "sz": "0.01"}, candles)

    # bar0 起始净值点 + range(1,n) 每根一个点 = n 个点。
    assert len(result["equity_curve"]) == len(candles)


def test_engine_fill_uses_next_bar_open():
    """Buy fill price must equal next bar's open (no look-ahead bias)."""
    from core.backtest.engine import run

    candles = _build_crossover_candles()
    result = run("dual_ma", {"fast_period": 3, "slow_period": 5, "sz": "0.01"}, candles)

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    assert buys, "Need at least one buy to test fill price"

    # Find the buy fill: its ts should match a candle's ts, and its price should
    # match that candle's open (the next bar after the signal).
    ts_to_candle = {int(c["ts"]): c for c in candles}
    for buy in buys:
        fill_candle = ts_to_candle.get(buy["ts"])
        assert fill_candle is not None, f"Fill ts {buy['ts']} not found in candles"
        assert abs(buy["price"] - float(fill_candle["o"])) < 1e-9, (
            f"Buy fill price {buy['price']} != candle open {fill_candle['o']} "
            f"(look-ahead bias!)"
        )


def test_engine_metrics_present():
    """Engine result contains required metrics keys."""
    from core.backtest.engine import run

    candles = _build_crossover_candles()
    result = run("dual_ma", {"fast_period": 3, "slow_period": 5, "sz": "0.01"}, candles)

    required_keys = {
        "total_return", "annualized_return", "max_drawdown",
        "sharpe", "win_rate", "profit_factor", "trade_count",
    }
    assert required_keys.issubset(result["metrics"].keys())


def test_engine_insufficient_candles():
    """Fewer than 2 candles returns empty results without error."""
    from core.backtest.engine import run

    result = run("dual_ma", {}, [_candle(1000, 100, 100, 100, 100)])
    assert result["equity_curve"] == []
    assert result["trades"] == []


def test_engine_unknown_code_ref_raises():
    """Unknown code_ref raises ValueError immediately."""
    from core.backtest.engine import run

    with pytest.raises(ValueError, match="Unknown strategy code_ref"):
        run("nonexistent_strategy", {}, _build_crossover_candles())


def test_engine_fee_reduces_cash():
    """Buying deducts fee from cash; selling deducts fee from proceeds."""
    from core.backtest.engine import run

    candles = _build_crossover_candles()
    result = run("dual_ma", {"fast_period": 3, "slow_period": 5, "sz": "0.01"}, candles, fee_rate=0.001)

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    assert all(t["fee"] > 0 for t in buys), "Each buy should have a positive fee"


# ---------------------------------------------------------------------------
# 3. API permissions and multi-tenant isolation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_backtest_without_permission_returns_403(api_client):
    """POST /api/backtest/backtests without backtest:create → 403."""
    user = _make_user("bt_no_perm", [])
    strategy = _make_strategy()
    api_client.force_authenticate(user)
    resp = api_client.post("/api/backtest/backtests", {
        "strategy_id": strategy.pk,
        "symbol": "BTC-USDT",
        "bar": "1m",
        "start_ts": 1_000_000,
        "end_ts": 2_000_000,
    }, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_backtest_with_permission_enqueues_task(api_client):
    """POST /api/backtest/backtests with backtest:create → 201 + task enqueued."""
    user = _make_user("bt_has_perm", ["backtest:create"])
    strategy = _make_strategy()
    api_client.force_authenticate(user)

    with patch("core.backtest.tasks.run_backtest.apply_async") as mock_async:
        resp = api_client.post("/api/backtest/backtests", {
            "strategy_id": strategy.pk,
            "symbol": "BTC-USDT",
            "bar": "1m",
            "start_ts": 1_000_000,
            "end_ts": 2_000_000,
        }, format="json")

    assert resp.status_code == 201
    assert resp.data["status"] == "pending"
    assert mock_async.called


@pytest.mark.django_db
def test_list_backtests_without_permission_returns_403(api_client):
    """GET /api/backtest/backtests without backtest:view → 403."""
    user = _make_user("bt_list_no_perm", [])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/backtest/backtests")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_backtests_only_returns_own(api_client):
    """GET /api/backtest/backtests returns only the authenticated user's backtests."""
    from core.backtest.models import Backtest

    alice = _make_user("bt_alice", ["backtest:view", "backtest:create"])
    bob   = _make_user("bt_bob",   ["backtest:view"])
    strategy = _make_strategy()

    bt_alice = Backtest.objects.create(
        user=alice, strategy=strategy, symbol="BTC-USDT", bar="1m",
        start_ts=1_000_000, end_ts=2_000_000,
    )
    Backtest.objects.create(
        user=bob, strategy=strategy, symbol="ETH-USDT", bar="1m",
        start_ts=1_000_000, end_ts=2_000_000,
    )

    api_client.force_authenticate(alice)
    resp = api_client.get("/api/backtest/backtests")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.data]
    assert bt_alice.pk in ids
    assert all(
        Backtest.objects.get(pk=i).user == alice
        for i in ids
    )


@pytest.mark.django_db
def test_detail_view_returns_404_for_other_user(api_client):
    """GET /api/backtest/backtests/<id> for another user's backtest → 404."""
    from core.backtest.models import Backtest

    alice = _make_user("bt_detail_alice", ["backtest:view"])
    bob   = _make_user("bt_detail_bob")
    strategy = _make_strategy()

    bt_bob = Backtest.objects.create(
        user=bob, strategy=strategy, symbol="BTC-USDT", bar="1m",
        start_ts=1_000_000, end_ts=2_000_000,
    )

    api_client.force_authenticate(alice)
    resp = api_client.get(f"/api/backtest/backtests/{bt_bob.pk}")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_create_backtest_missing_fields_returns_400(api_client):
    """POST with missing required fields returns 400."""
    user = _make_user("bt_400_user", ["backtest:create"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/backtest/backtests", {
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_backtest_end_before_start_returns_400(api_client):
    """POST with end_ts <= start_ts returns 400."""
    user = _make_user("bt_ts_user", ["backtest:create"])
    strategy = _make_strategy()
    api_client.force_authenticate(user)
    resp = api_client.post("/api/backtest/backtests", {
        "strategy_id": strategy.pk,
        "symbol": "BTC-USDT",
        "bar": "1m",
        "start_ts": 2_000_000,
        "end_ts": 1_000_000,
    }, format="json")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. run_backtest Celery task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_run_backtest_task_success():
    """run_backtest task: mocked fetch_range → engine runs → status=done, metrics saved."""
    from core.backtest.models import Backtest, BacktestTrade
    from core.backtest.tasks import run_backtest

    user = _make_user("task_user")
    strategy = _make_strategy()

    bt = Backtest.objects.create(
        user=user, strategy=strategy, symbol="BTC-USDT", bar="1m",
        start_ts=1_000_000, end_ts=5_000_000,
        params={"fast_period": 3, "slow_period": 5, "sz": "0.01"},
    )

    stub_candles = _build_crossover_candles()

    with patch("core.backtest.tasks.fetch_range", return_value=stub_candles):
        run_backtest(bt.pk)

    bt.refresh_from_db()
    assert bt.status == Backtest.STATUS_DONE
    assert len(bt.equity_curve) > 0
    assert "total_return" in bt.metrics
    assert bt.error_msg == ""
    assert BacktestTrade.objects.filter(backtest=bt).count() > 0


@pytest.mark.django_db
def test_run_backtest_task_sets_error_on_exception():
    """run_backtest task: fetch_range raises → status=error, error_msg set."""
    from core.backtest.models import Backtest
    from core.backtest.tasks import run_backtest

    user = _make_user("task_err_user")
    strategy = _make_strategy()

    bt = Backtest.objects.create(
        user=user, strategy=strategy, symbol="BTC-USDT", bar="1m",
        start_ts=1_000_000, end_ts=2_000_000,
    )

    with patch(
        "core.backtest.tasks.fetch_range",
        side_effect=RuntimeError("OKX connection refused"),
    ):
        with pytest.raises(RuntimeError):
            run_backtest(bt.pk)

    bt.refresh_from_db()
    assert bt.status == Backtest.STATUS_ERROR
    assert "OKX connection refused" in bt.error_msg


@pytest.mark.django_db
def test_run_backtest_task_not_found_returns_silently():
    """run_backtest with nonexistent backtest_id returns without error."""
    from core.backtest.tasks import run_backtest

    # Should not raise — just log and return.
    run_backtest(999999)


@pytest.mark.django_db
def test_run_backtest_task_trades_persisted():
    """BacktestTrade rows are created with correct side values."""
    from core.backtest.models import Backtest, BacktestTrade
    from core.backtest.tasks import run_backtest

    user = _make_user("task_trades_user")
    strategy = _make_strategy()

    bt = Backtest.objects.create(
        user=user, strategy=strategy, symbol="BTC-USDT", bar="1m",
        start_ts=1_000_000, end_ts=5_000_000,
        params={"fast_period": 3, "slow_period": 5, "sz": "0.01"},
    )

    stub_candles = _build_crossover_candles()
    with patch("core.backtest.tasks.fetch_range", return_value=stub_candles):
        run_backtest(bt.pk)

    bt.refresh_from_db()
    trades = BacktestTrade.objects.filter(backtest=bt)
    assert trades.exists()
    sides = set(trades.values_list("side", flat=True))
    assert "buy" in sides
    assert "sell" in sides


# ---------------------------------------------------------------------------
# 5. VB-T3: controlled-exec code/visual backtest
# ---------------------------------------------------------------------------

def _ramp_candles(prices: list[float], start_ts: int = 1_000_000, step: int = 60_000) -> list[dict]:
    """Build simple candles where open == close == given price for each bar."""
    out = []
    t = start_ts
    for p in prices:
        out.append(_candle(t, p, p, p, p))
        t += step
    return out


# A minimal user on_tick: buy 0.01 the first time price crosses above 100; then hold.
_CODE_BREAKOUT = '''
_bought = False


def on_tick(ctx, params):
    global _bought
    closes = [float(c["c"]) for c in ctx.candles()]
    if not closes:
        return
    if not _bought and closes[-1] > 100.0:
        ctx.buy(0.01)
        _bought = True
'''


def test_engine_code_strategy_runs():
    """A source_type=code on_tick runs through controlled exec and produces results."""
    from core.backtest.engine import run

    # flat at 100, then break above 100 → one buy, plus a next bar to fill against.
    candles = _ramp_candles([100.0] * 5 + [150.0, 150.0, 150.0])
    result = run("user_code", {}, candles, code=_CODE_BREAKOUT)

    assert result["equity_curve"], "equity_curve must be non-empty"
    buys = [t for t in result["trades"] if t["side"] == "buy"]
    assert buys, "expected at least one buy trade from code strategy"
    assert "total_return" in result["metrics"]


# A code strategy with module-level position + take-profit → must trigger a sell,
# proving module-level state persists across bars (same on_tick object per loop).
_CODE_TP = '''
_pos = 0.0
_entry = 0.0


def on_tick(ctx, params):
    global _pos, _entry
    closes = [float(c["c"]) for c in ctx.candles()]
    if not closes:
        return
    price = closes[-1]
    if _pos <= 0:
        ctx.buy(0.01)
        _pos = 0.01
        _entry = price
        return
    # take-profit: +20% → sell all
    if _entry > 0 and (price - _entry) / _entry >= 0.20:
        ctx.sell(_pos)
        _pos = 0.0
        _entry = 0.0
'''


def test_engine_code_module_state_persists_across_bars():
    """Module-level _pos/_entry persist across bars → take-profit sell fires."""
    from core.backtest.engine import run

    # buy at 100, then price rallies well above +20% → sell.
    candles = _ramp_candles([100.0, 100.0, 130.0, 130.0, 130.0])
    result = run("user_code", {}, candles, code=_CODE_TP)

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert buys, "expected a buy trade"
    assert sells, "expected a take-profit sell (module-level state must persist)"


def test_engine_visual_compiled_product_runs():
    """A rule_compiler product (visual) runs through controlled exec end-to-end."""
    from core.backtest.engine import run
    from core.strategy.rule_compiler import compile_rule

    cfg = {
        "buy": {
            "logic": "and",
            "conditions": [
                {"op": "cross_above",
                 "left": {"ind": "MA", "period": 5},
                 "right": {"ind": "MA", "period": 20}},
            ],
        },
        "risk": {"take_profit_pct": 5},
        "sz": 0.01,
    }
    code = compile_rule(cfg)

    # long flat baseline (enough bars for MA20) then a strong uptrend to force a
    # golden cross (MA5 crossing above MA20), then a further rally for take-profit.
    prices = [100.0] * 30
    prices += [float(100 + i * 10) for i in range(1, 15)]  # rally
    candles = _ramp_candles(prices)

    result = run("visual", {}, candles, code=code)
    assert result["equity_curve"], "visual backtest equity_curve must be non-empty"
    buys = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert buys, "expected a buy from the compiled MA cross rule"
    # take-profit at +5% on a strong rally should also produce a sell.
    assert sells, "expected a take-profit sell from the compiled risk block"


def test_engine_builtin_not_regressed_when_code_none():
    """code=None still routes through the builtin importlib path (no regression)."""
    from core.backtest.engine import run

    candles = _build_crossover_candles()
    result = run(
        "dual_ma", {"fast_period": 3, "slow_period": 5, "sz": "0.01"}, candles,
        code=None,
    )
    buys = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert buys and sells, "builtin dual_ma backtest must still work with code=None"


def test_engine_controlled_exec_blocks_disallowed_import():
    """Defence-in-depth: importing a non-whitelisted module fails at exec time."""
    from core.backtest.engine import run

    bad_code = "import os\n\n\ndef on_tick(ctx, params):\n    pass\n"
    candles = _ramp_candles([100.0, 100.0, 100.0])
    with pytest.raises(ImportError):
        run("user_code", {}, candles, code=bad_code)


# ---------------------------------------------------------------------------
# 6. VB-T3: backtest create — open to all source_types + multi-tenant lockdown
# ---------------------------------------------------------------------------

def _owned_code_strategy(owner, visibility=Strategy.VISIBILITY_PRIVATE, status=Strategy.STATUS_DRAFT) -> Strategy:
    return Strategy.objects.create(
        name="my code",
        source_type=Strategy.SOURCE_CODE,
        code_ref="user_code",
        code=_CODE_BREAKOUT,
        is_builtin=False,
        owner=owner,
        visibility=visibility,
        status=status,
    )


@pytest.mark.django_db
def test_create_backtest_own_code_strategy_201(api_client):
    """User can backtest their own private code strategy → 201."""
    user = _make_user("bt_own_code", ["backtest:create"])
    strategy = _owned_code_strategy(user)
    api_client.force_authenticate(user)
    with patch("core.backtest.tasks.run_backtest.apply_async"):
        resp = api_client.post("/api/backtest/backtests", {
            "strategy_id": strategy.pk,
            "symbol": "BTC-USDT", "bar": "1m",
            "start_ts": 1_000_000, "end_ts": 2_000_000,
        }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_create_backtest_other_users_private_strategy_404(api_client):
    """Backtesting another user's private strategy → 404 (越权收口)."""
    owner = _make_user("bt_owner")
    attacker = _make_user("bt_attacker", ["backtest:create"])
    strategy = _owned_code_strategy(owner)  # private, owned by someone else

    api_client.force_authenticate(attacker)
    with patch("core.backtest.tasks.run_backtest.apply_async") as mock_async:
        resp = api_client.post("/api/backtest/backtests", {
            "strategy_id": strategy.pk,
            "symbol": "BTC-USDT", "bar": "1m",
            "start_ts": 1_000_000, "end_ts": 2_000_000,
        }, format="json")
    assert resp.status_code == 404
    assert not mock_async.called


@pytest.mark.django_db
def test_create_backtest_approved_public_strategy_201(api_client):
    """Any user can backtest an approved public strategy → 201."""
    owner = _make_user("bt_pub_owner")
    user = _make_user("bt_pub_user", ["backtest:create"])
    strategy = _owned_code_strategy(
        owner, visibility=Strategy.VISIBILITY_PUBLIC, status=Strategy.STATUS_APPROVED
    )
    api_client.force_authenticate(user)
    with patch("core.backtest.tasks.run_backtest.apply_async"):
        resp = api_client.post("/api/backtest/backtests", {
            "strategy_id": strategy.pk,
            "symbol": "BTC-USDT", "bar": "1m",
            "start_ts": 1_000_000, "end_ts": 2_000_000,
        }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_create_backtest_builtin_strategy_201(api_client):
    """Builtin strategy (owner is null) is runnable by anyone → 201."""
    user = _make_user("bt_builtin_user", ["backtest:create"])
    strategy = _make_strategy()  # builtin, owner=None
    api_client.force_authenticate(user)
    with patch("core.backtest.tasks.run_backtest.apply_async"):
        resp = api_client.post("/api/backtest/backtests", {
            "strategy_id": strategy.pk,
            "symbol": "BTC-USDT", "bar": "1m",
            "start_ts": 1_000_000, "end_ts": 2_000_000,
        }, format="json")
    assert resp.status_code == 201
