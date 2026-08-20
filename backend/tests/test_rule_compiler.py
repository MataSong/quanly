"""Tests for the visual-strategy rule compiler (VB-T2).

Covers:
  - validate_rule_config: legal config passes; empty conditions / non-whitelist
    ind / non-whitelist op / non-numeric period-const (injection payloads) raise
    ValueError.
  - compile_rule: every indicator (MA/EMA/RSI/MACD/price/volume) + operators
    (cross / scalar compare) + and/or + take-profit/stop-loss → generated code
    compile()s and passes validation.check_ast.
  - anti-injection: malicious strings in period/const/sz are blocked at validate,
    or (if reached) at float()/int() in compile — and never appear as literals in
    the generated source.
  - executability: exec_strategy extracts on_tick; feeding synthetic candles and
    calling on_tick several times doesn't raise; module-level _pos state persists
    across calls (buy sets _pos > 0).
  - take-profit: a profit-crossing series makes the generated code sell.
"""
from __future__ import annotations

import pytest

from core.strategy.rule_compiler import compile_rule, validate_rule_config
from core.strategy.safe_exec import exec_strategy
from core.strategy.validation import check_ast, check_syntax


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCtx:
    """Minimal ctx exposing candles()/buy()/sell()/log()/price()."""

    def __init__(self, history):
        self._history = history
        self.buys = []
        self.sells = []
        self.logs = []

    def candles(self):
        return self._history

    def price(self):
        return float(self._history[-1]["c"])

    def buy(self, sz, ord_type="market", px=None):
        self.buys.append(float(sz))
        return "ord-buy"

    def sell(self, sz, ord_type="market", px=None):
        self.sells.append(float(sz))
        return "ord-sell"

    def log(self, level, message):
        self.logs.append((level, message))


def _candle(ts, c, vol=1.0):
    return {"ts": ts, "o": str(c), "h": str(c), "l": str(c), "c": str(c),
            "vol": str(vol), "volCcy": str(vol)}


def _series(prices):
    return [_candle(1000 + i * 60, p) for i, p in enumerate(prices)]


_LEGAL_CFG = {
    "buy": {"logic": "and", "conditions": [
        {"left": {"ind": "MA", "period": 5}, "op": "cross_above", "right": {"ind": "MA", "period": 20}},
        {"left": {"ind": "RSI", "period": 14}, "op": "<", "right": {"const": 30}}]},
    "sell": {"logic": "or", "conditions": [
        {"left": {"ind": "MA", "period": 5}, "op": "cross_below", "right": {"ind": "MA", "period": 20}}]},
    "risk": {"take_profit_pct": 5.0, "stop_loss_pct": 3.0},
    "sz": "0.001",
}


# ---------------------------------------------------------------------------
# validate_rule_config
# ---------------------------------------------------------------------------


def test_validate_legal_config_passes():
    validate_rule_config(_LEGAL_CFG)  # must not raise


def test_validate_buy_only_passes():
    cfg = {"buy": {"conditions": [
        {"left": {"ind": "price"}, "op": ">", "right": {"const": 100}}]}}
    validate_rule_config(cfg)


def test_validate_both_groups_empty_raises():
    with pytest.raises(ValueError):
        validate_rule_config({"buy": {"conditions": []}, "sell": {"conditions": []}})


def test_validate_missing_both_groups_raises():
    with pytest.raises(ValueError):
        validate_rule_config({"risk": {"take_profit_pct": 5}})


def test_validate_non_whitelist_indicator_raises():
    cfg = {"buy": {"conditions": [
        {"left": {"ind": "EVIL", "period": 5}, "op": ">", "right": {"const": 1}}]}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


def test_validate_non_whitelist_op_raises():
    cfg = {"buy": {"conditions": [
        {"left": {"ind": "MA", "period": 5}, "op": "__eq__", "right": {"const": 1}}]}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


def test_validate_non_whitelist_logic_raises():
    cfg = {"buy": {"logic": "xor", "conditions": [
        {"left": {"ind": "price"}, "op": ">", "right": {"const": 1}}]}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


def test_validate_cross_with_const_raises():
    cfg = {"buy": {"conditions": [
        {"left": {"ind": "MA", "period": 5}, "op": "cross_above", "right": {"const": 20}}]}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


@pytest.mark.parametrize("payload", [
    "__import__('os')",
    "__import__('os').system('rm -rf /')",
    "eval('1+1')",
    "1); import os; os.system('x'); (",
    "abc",
    None,
    [1, 2],
    float("inf"),
    float("-inf"),
    float("nan"),
    "inf",
    "nan",
    "1e400",  # overflows to inf
])
def test_validate_injection_period_raises(payload):
    cfg = {"buy": {"conditions": [
        {"left": {"ind": "MA", "period": payload}, "op": ">", "right": {"const": 1}}]}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


@pytest.mark.parametrize("payload", [
    "__import__('os')",
    "open('/etc/passwd')",
    "abc",
    float("inf"),
    float("-inf"),
    float("nan"),
    "inf",
    "nan",
    "1e400",
])
def test_validate_injection_const_raises(payload):
    cfg = {"buy": {"conditions": [
        {"left": {"ind": "price"}, "op": ">", "right": {"const": payload}}]}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


@pytest.mark.parametrize("payload", ["__import__('os')", float("inf"), float("nan"), "inf", "1e400"])
def test_validate_injection_sz_raises(payload):
    cfg = {**_LEGAL_CFG, "sz": payload}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


@pytest.mark.parametrize("payload", ["eval('9')", float("inf"), float("nan"), "inf", "1e400"])
def test_validate_injection_risk_pct_raises(payload):
    cfg = {**_LEGAL_CFG, "risk": {"take_profit_pct": payload}}
    with pytest.raises(ValueError):
        validate_rule_config(cfg)


def test_compile_rejects_non_finite_const():
    # I-1 regression: float('inf') must not reach the generator (would emit bare
    # `inf` — compiles + passes AST but NameError at runtime → silent failure).
    for bad in (float("inf"), float("nan"), float("-inf")):
        cfg = {"buy": {"conditions": [
            {"left": {"ind": "price"}, "op": ">", "right": {"const": bad}}]}}
        with pytest.raises(ValueError):
            compile_rule(cfg)


# ---------------------------------------------------------------------------
# compile_rule — syntax + AST for every indicator/op combination
# ---------------------------------------------------------------------------


def _assert_compiles_and_passes_ast(cfg):
    code = compile_rule(cfg)
    assert check_syntax(code)["ok"], code
    result = check_ast(code)
    assert result["ok"], result["violations"]
    # sanity: compile() directly too
    compile(code, "<gen>", "exec")
    # M-2: every generated variant must be free of dangerous tokens / bare
    # non-finite literals — enforced across all parametrized variants, not just
    # one example.
    for token in ["__import__", "eval(", "exec(", "os.system", "open(",
                  " inf", "=inf", " nan", "=nan"]:
        assert token not in code, f"dangerous token {token!r} in:\n{code}"
    return code


def test_compile_full_legal_config():
    _assert_compiles_and_passes_ast(_LEGAL_CFG)


@pytest.mark.parametrize("cfg", [
    # MA scalar compare
    {"buy": {"conditions": [{"left": {"ind": "MA", "period": 10}, "op": ">", "right": {"const": 50}}]}},
    # EMA cross
    {"buy": {"conditions": [{"left": {"ind": "EMA", "period": 5}, "op": "cross_above", "right": {"ind": "EMA", "period": 20}}]}},
    # RSI
    {"buy": {"conditions": [{"left": {"ind": "RSI", "period": 14}, "op": "<", "right": {"const": 30}}]}},
    # MACD macd-line cross signal-line
    {"buy": {"conditions": [{"left": {"ind": "MACD", "fast": 12, "slow": 26, "signal": 9, "line": "macd"},
                             "op": "cross_above",
                             "right": {"ind": "MACD", "fast": 12, "slow": 26, "signal": 9, "line": "signal"}}]}},
    # price / volume
    {"buy": {"conditions": [{"left": {"ind": "price"}, "op": ">=", "right": {"const": 100}}]}},
    {"buy": {"conditions": [{"left": {"ind": "volume"}, "op": "<=", "right": {"const": 5}}]}},
    # or logic, sell-only
    {"sell": {"logic": "or", "conditions": [
        {"left": {"ind": "MA", "period": 5}, "op": "cross_below", "right": {"ind": "MA", "period": 20}},
        {"left": {"ind": "RSI", "period": 14}, "op": ">", "right": {"const": 70}}]}},
    # risk only take-profit
    {"buy": {"conditions": [{"left": {"ind": "price"}, "op": ">", "right": {"const": 1}}]},
     "risk": {"take_profit_pct": 10.0}},
    # risk only stop-loss
    {"buy": {"conditions": [{"left": {"ind": "price"}, "op": ">", "right": {"const": 1}}]},
     "risk": {"stop_loss_pct": 2.0}},
])
def test_compile_variants_pass_ast(cfg):
    _assert_compiles_and_passes_ast(cfg)


# ---------------------------------------------------------------------------
# anti-injection: no user string ends up as a literal in generated code
# ---------------------------------------------------------------------------


def test_compile_blocks_injection_and_no_string_in_output():
    # These would be blocked at validate. Verify compile also refuses.
    bad = {"buy": {"conditions": [
        {"left": {"ind": "MA", "period": "__import__('os')"}, "op": ">", "right": {"const": 1}}]}}
    with pytest.raises(ValueError):
        compile_rule(bad)


def test_compile_numeric_const_appears_only_as_number():
    cfg = {"buy": {"conditions": [{"left": {"ind": "price"}, "op": ">", "right": {"const": 42}}]}}
    code = compile_rule(cfg)
    # the coerced float 42.0 is present; no quoted user payload
    assert "42.0" in code
    # ensure the generated code never references dangerous names
    for token in ["__import__", "eval(", "exec(", "os.system", "open("]:
        assert token not in code


def test_compile_string_numeric_is_coerced_not_spliced():
    # Legit string-encoded numbers must be coerced to numeric literals.
    cfg = {"buy": {"conditions": [{"left": {"ind": "MA", "period": "7"}, "op": ">", "right": {"const": "3.5"}}]}}
    code = compile_rule(cfg)
    assert "_ma_at(closes, 7," in code   # int 7, not "7"
    assert "3.5" in code
    assert '"7"' not in code and "'7'" not in code


# ---------------------------------------------------------------------------
# executability + module-level position state persistence
# ---------------------------------------------------------------------------


def test_compiled_code_execs_and_defines_on_tick():
    code = compile_rule(_LEGAL_CFG)
    on_tick = exec_strategy(code)
    assert callable(on_tick)


def test_on_tick_runs_without_raising_over_many_ticks():
    code = compile_rule(_LEGAL_CFG)
    on_tick = exec_strategy(code)
    # Build a rising-then-anything series and call on_tick repeatedly.
    prices = [100.0] * 25 + [100.0 + i for i in range(30)]
    for i in range(21, len(prices)):
        ctx = _FakeCtx(_series(prices[: i + 1]))
        on_tick(ctx, {})  # must not raise


def test_module_level_position_state_persists_after_buy():
    # A buy-only strategy: price > 0 always true → first tick buys and sets _pos.
    cfg = {"buy": {"conditions": [{"left": {"ind": "price"}, "op": ">", "right": {"const": 0}}]}}
    code = compile_rule(cfg)
    on_tick = exec_strategy(code)
    # exec_strategy builds its own namespace internally; to inspect module state
    # we re-exec in a namespace we control, mirroring the runner.
    from core.strategy.safe_exec import build_safe_builtins, _make_controlled_import, ALLOWED_MODULES
    safe_builtins = build_safe_builtins()
    safe_builtins["__import__"] = _make_controlled_import(ALLOWED_MODULES)
    ns = {"__builtins__": safe_builtins}
    exec(code, ns)
    fn = ns["on_tick"]
    ctx = _FakeCtx(_series([100.0] * 40))
    assert ns["_pos"] == 0.0
    fn(ctx, {})
    assert ctx.buys == [pytest.approx(0.001)]
    assert ns["_pos"] > 0  # module-level state persisted across the call
    # second tick: now holding, buy branch is skipped (no double buy)
    fn(ctx, {})
    assert ctx.buys == [pytest.approx(0.001)]  # still only one buy


# ---------------------------------------------------------------------------
# take-profit: profit crossing the threshold triggers a sell
# ---------------------------------------------------------------------------


def test_take_profit_triggers_sell():
    cfg = {
        "buy": {"conditions": [{"left": {"ind": "price"}, "op": ">", "right": {"const": 0}}]},
        "risk": {"take_profit_pct": 5.0},
    }
    code = compile_rule(cfg)
    from core.strategy.safe_exec import build_safe_builtins, _make_controlled_import, ALLOWED_MODULES
    safe_builtins = build_safe_builtins()
    safe_builtins["__import__"] = _make_controlled_import(ALLOWED_MODULES)
    ns = {"__builtins__": safe_builtins}
    exec(code, ns)
    fn = ns["on_tick"]

    # Tick 1 @ price 100 → buys, _entry = 100.
    ctx1 = _FakeCtx(_series([100.0] * 40))
    fn(ctx1, {})
    assert ns["_entry"] == pytest.approx(100.0)
    assert ns["_pos"] > 0

    # Tick 2 @ price 110 (+10% > 5% take-profit) → sells & resets.
    ctx2 = _FakeCtx(_series([100.0] * 40 + [110.0]))
    fn(ctx2, {})
    assert ctx2.sells and ctx2.sells[0] > 0
    assert ns["_pos"] == 0.0
    assert ns["_entry"] == 0.0


def test_stop_loss_triggers_sell():
    cfg = {
        "buy": {"conditions": [{"left": {"ind": "price"}, "op": ">", "right": {"const": 0}}]},
        "risk": {"stop_loss_pct": 3.0},
    }
    code = compile_rule(cfg)
    from core.strategy.safe_exec import build_safe_builtins, _make_controlled_import, ALLOWED_MODULES
    safe_builtins = build_safe_builtins()
    safe_builtins["__import__"] = _make_controlled_import(ALLOWED_MODULES)
    ns = {"__builtins__": safe_builtins}
    exec(code, ns)
    fn = ns["on_tick"]

    ctx1 = _FakeCtx(_series([100.0] * 40))
    fn(ctx1, {})
    assert ns["_pos"] > 0

    # price drops to 95 (-5% <= -3% stop-loss) → sells.
    ctx2 = _FakeCtx(_series([100.0] * 40 + [95.0]))
    fn(ctx2, {})
    assert ctx2.sells and ns["_pos"] == 0.0
