"""Rule compiler: visual strategy rule_config (JSON) → Python on_tick source.

SECURITY CORE of the visual strategy builder.

Users assemble a strategy visually (pick indicators / conditions / params /
take-profit / stop-loss). The UI stores that as a ``rule_config`` JSON blob.
This module compiles that JSON into Python ``on_tick`` source code (stored in the
Strategy.code field) which then re-uses the existing ``source_type=code``
container-exec + AST-check execution chain (safe_exec / validation).

⚠️  ANTI-INJECTION IS THE POINT ⚠️
The compiler NEVER splices raw rule_config strings into the generated source:

  1. Every numeric value (period / const / pct / sz) is coerced with float()/int()
     during validation AND again at interpolation time, then emitted via repr() of
     the *coerced number* — so ``"__import__('os')"`` can never survive as a string
     literal in code; it raises ValueError at float()/int() first.
  2. Indicator names / operators / logic keywords are mapped through fixed Python
     dispatch (if/elif on validated enums) — the raw string is never emitted.
  3. No eval / no str.format of user content into an executable position.

The generated code:
  - only uses the safe-builtins whitelist (see safe_exec.build_safe_builtins) plus
    inlined pure indicator helpers (no imports — the runner container can't import
    backend),
  - passes validation.check_ast (self-checked by tests),
  - keeps module-level position state (_pos / _entry) across on_tick calls (the
    exec namespace == on_tick.__globals__ is reused per container run), which is
    the basis for take-profit / stop-loss / position management.

Pure module — NO Django imports; unit-testable without a DB.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Whitelisted enums — the ONLY indicator/op/logic tokens the compiler accepts.
# Raw rule_config strings are validated against these sets and then dispatched
# through fixed code paths; they are never emitted into the generated source.
# ---------------------------------------------------------------------------

#: Indicators that produce a series/scalar from closes (or price/volume/const).
_ALLOWED_INDICATORS: frozenset[str] = frozenset({
    "MA", "EMA", "RSI", "MACD", "price", "volume", "const",
})

#: Indicators that require a numeric ``period`` field.
_PERIOD_INDICATORS: frozenset[str] = frozenset({"MA", "EMA", "RSI"})

#: Comparison operators (scalar now-value compare).
_SCALAR_OPS: frozenset[str] = frozenset({">", "<", ">=", "<="})

#: Crossover operators (need prev + now of both sides).
_CROSS_OPS: frozenset[str] = frozenset({"cross_above", "cross_below"})

_ALLOWED_OPS: frozenset[str] = _SCALAR_OPS | _CROSS_OPS

_ALLOWED_LOGIC: frozenset[str] = frozenset({"and", "or"})

_ALLOWED_MACD_LINES: frozenset[str] = frozenset({"macd", "signal"})


# ---------------------------------------------------------------------------
# 1. validate_rule_config
# ---------------------------------------------------------------------------


def _as_number(value: Any, field: str, *, kind: str = "float") -> float | int:
    """Coerce *value* to a number or raise ValueError.

    This is the anti-injection gate: any non-numeric payload (e.g. a string like
    ``"__import__('os')"``) fails here with a Chinese error message, and never
    reaches the compiler's interpolation step.
    """
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        raise ValueError(f"字段 {field} 不能是布尔值: {value!r}")
    if isinstance(value, str) and value.strip() == "":
        raise ValueError(f"字段 {field} 不能为空字符串")
    try:
        if kind == "int":
            return int(value)
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"字段 {field} 必须是数字, 收到非法值: {value!r}")


def _validate_operand(operand: Any, side: str) -> None:
    """Validate a single left/right operand dict."""
    if not isinstance(operand, dict):
        raise ValueError(f"{side} 操作数必须是对象, 收到: {operand!r}")

    if "const" in operand:
        _as_number(operand["const"], f"{side}.const")
        return

    ind = operand.get("ind")
    if ind not in _ALLOWED_INDICATORS:
        raise ValueError(
            f"{side} 指标 {ind!r} 不在白名单内, 允许: {sorted(_ALLOWED_INDICATORS)}"
        )
    if ind == "const":
        # ind:"const" must carry a numeric value via the 'const' key handled above;
        # reaching here means no const value was provided.
        raise ValueError(f"{side} 指标为 const 时必须提供数字 const 值")

    if ind in _PERIOD_INDICATORS:
        if "period" not in operand:
            raise ValueError(f"{side} 指标 {ind} 缺少 period")
        period = _as_number(operand["period"], f"{side}.period", kind="int")
        if period <= 0:
            raise ValueError(f"{side} 指标 {ind} 的 period 必须为正整数, 收到: {period}")

    if ind == "MACD":
        for key in ("fast", "slow", "signal"):
            val = _as_number(operand.get(key, {"fast": 12, "slow": 26, "signal": 9}[key]),
                             f"{side}.{key}", kind="int")
            if val <= 0:
                raise ValueError(f"{side} MACD 的 {key} 必须为正整数, 收到: {val}")
        line = operand.get("line", "macd")
        if line not in _ALLOWED_MACD_LINES:
            raise ValueError(
                f"{side} MACD line 必须是 {sorted(_ALLOWED_MACD_LINES)}, 收到: {line!r}"
            )


def _validate_condition(cond: Any, group: str) -> None:
    if not isinstance(cond, dict):
        raise ValueError(f"{group} 组的条件必须是对象, 收到: {cond!r}")

    op = cond.get("op")
    if op not in _ALLOWED_OPS:
        raise ValueError(
            f"{group} 组运算符 {op!r} 不在白名单内, 允许: {sorted(_ALLOWED_OPS)}"
        )

    if "left" not in cond or "right" not in cond:
        raise ValueError(f"{group} 组条件缺少 left 或 right")

    left = cond["left"]
    right = cond["right"]
    _validate_operand(left, f"{group}.left")
    _validate_operand(right, f"{group}.right")

    # Crossover operators need two indicator lines (prev/now); a const has no
    # 'previous' value. Reject const operands on cross_* for correctness + clarity.
    if op in _CROSS_OPS:
        if isinstance(left, dict) and "const" in left:
            raise ValueError(f"{group} 组 {op} 的 left 不能是常量 const(金叉死叉需两条指标线)")
        if isinstance(right, dict) and "const" in right:
            raise ValueError(f"{group} 组 {op} 的 right 不能是常量 const(金叉死叉需两条指标线)")


def _validate_group(group_cfg: Any, name: str) -> bool:
    """Validate a buy/sell group. Returns True if it has usable conditions."""
    if group_cfg is None:
        return False
    if not isinstance(group_cfg, dict):
        raise ValueError(f"{name} 必须是对象, 收到: {group_cfg!r}")

    conditions = group_cfg.get("conditions")
    if not conditions:
        return False
    if not isinstance(conditions, list):
        raise ValueError(f"{name}.conditions 必须是数组, 收到: {conditions!r}")

    logic = group_cfg.get("logic", "and")
    if logic not in _ALLOWED_LOGIC:
        raise ValueError(f"{name}.logic 必须是 {sorted(_ALLOWED_LOGIC)}, 收到: {logic!r}")

    for cond in conditions:
        _validate_condition(cond, name)
    return True


def validate_rule_config(cfg: Any) -> None:
    """Validate a rule_config dict; raise ValueError (Chinese reason) if illegal.

    Checks:
      - cfg is a dict.
      - At least one of buy/sell has non-empty conditions (both empty → error).
      - Every condition: left/right ind ∈ whitelist; op ∈ whitelist;
        period/const/MACD-params numeric & positive (anti-injection gate).
      - logic ∈ {and, or}.
      - cross_* operands must be indicators, not const.
      - risk.take_profit_pct / stop_loss_pct numeric if present.
      - sz numeric & positive if present.
    """
    if not isinstance(cfg, dict):
        raise ValueError(f"rule_config 必须是对象, 收到: {cfg!r}")

    has_buy = _validate_group(cfg.get("buy"), "buy")
    has_sell = _validate_group(cfg.get("sell"), "sell")
    if not has_buy and not has_sell:
        raise ValueError("buy 与 sell 至少要有一组包含 conditions(两组都为空非法)")

    risk = cfg.get("risk")
    if risk is not None:
        if not isinstance(risk, dict):
            raise ValueError(f"risk 必须是对象, 收到: {risk!r}")
        for key in ("take_profit_pct", "stop_loss_pct"):
            if key in risk and risk[key] is not None:
                pct = _as_number(risk[key], f"risk.{key}")
                if pct <= 0:
                    raise ValueError(f"risk.{key} 必须为正数, 收到: {pct}")

    if "sz" in cfg and cfg["sz"] is not None:
        sz = _as_number(cfg["sz"], "sz")
        if sz <= 0:
            raise ValueError(f"sz 必须为正数, 收到: {sz}")


# ---------------------------------------------------------------------------
# 2. Inlined indicator helper source (mirrors builtin/*.py pure functions).
#    Emitted verbatim at the top of the generated module. NO user data here.
#    Only safe-whitelist builtins are used (len/sum/zip/float/max/min/range).
# ---------------------------------------------------------------------------

_INDICATOR_HELPERS = '''\
def _ma(closes, n):
    if n <= 0 or len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _ma_at(closes, n, offset):
    # SMA using data up to index len-1-offset (offset=0 -> now, 1 -> prev).
    end = len(closes) - offset
    if end <= 0:
        return None
    return _ma(closes[:end], n)


def _ema_series(prices, n):
    if not prices or n <= 0:
        return []
    k = 2.0 / (n + 1.0)
    ema = prices[0]
    out = [ema]
    for p in prices[1:]:
        ema = p * k + ema * (1.0 - k)
        out.append(ema)
    return out


def _ema_at(closes, n, offset):
    series = _ema_series(closes, n)
    idx = len(series) - 1 - offset
    if idx < 0:
        return None
    return series[idx]


def _rsi(closes, n):
    if n <= 0 or len(closes) < n + 1:
        return None
    window = closes[-(n + 1):]
    gains = 0.0
    losses = 0.0
    for prev, cur in zip(window[:-1], window[1:]):
        change = cur - prev
        if change > 0:
            gains += change
        else:
            losses += -change
    avg_gain = gains / n
    avg_loss = losses / n
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _rsi_at(closes, n, offset):
    end = len(closes) - offset
    if end <= 0:
        return None
    return _rsi(closes[:end], n)


def _macd_lines(closes, fast, slow, sig):
    if fast <= 0 or slow <= 0 or sig <= 0:
        return None
    if len(closes) < slow + sig:
        return None
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema_series(macd_line, sig)
    return macd_line, signal_line


def _macd_at(closes, fast, slow, sig, which, offset):
    lines = _macd_lines(closes, fast, slow, sig)
    if lines is None:
        return None
    macd_line, signal_line = lines
    series = macd_line if which == "macd" else signal_line
    idx = len(series) - 1 - offset
    if idx < 0:
        return None
    return series[idx]
'''


# ---------------------------------------------------------------------------
# 3. compile_rule — JSON → on_tick source string.
# ---------------------------------------------------------------------------


def _operand_expr(operand: dict, offset_var: str) -> tuple[str, int]:
    """Return (python_expr, min_bars_needed) for an operand at a given offset.

    *offset_var* is a Python expression string that evaluates to the bar offset
    (0 = current bar, 1 = previous bar). All numeric params are re-coerced here
    and emitted via repr() of the coerced number — never as raw strings.
    """
    if "const" in operand:
        val = float(operand["const"])
        return (repr(val), 0)

    ind = operand["ind"]

    if ind == "price":
        # close price at the given offset
        return (f"(closes[-1 - ({offset_var})] if len(closes) > ({offset_var}) else None)", 1)

    if ind == "volume":
        return (f"(volumes[-1 - ({offset_var})] if len(volumes) > ({offset_var}) else None)", 1)

    if ind in ("MA", "EMA", "RSI"):
        n = int(operand["period"])
        fn = {"MA": "_ma_at", "EMA": "_ema_at", "RSI": "_rsi_at"}[ind]
        need = n + 1 if ind == "RSI" else n
        return (f"{fn}(closes, {n!r}, {offset_var})", need + 1)

    if ind == "MACD":
        fast = int(operand.get("fast", 12))
        slow = int(operand.get("slow", 26))
        sig = int(operand.get("signal", 9))
        which = operand.get("line", "macd")
        # which is validated ∈ {macd, signal}; emit as a fixed string literal.
        which_lit = "macd" if which == "macd" else "signal"
        need = slow + sig + 1
        return (
            f"_macd_at(closes, {fast!r}, {slow!r}, {sig!r}, {which_lit!r}, {offset_var})",
            need,
        )

    # Unreachable if validate_rule_config ran first.
    raise ValueError(f"未知指标: {ind!r}")


def _condition_expr(cond: dict, indent: str, idx: int) -> tuple[list[str], str, int]:
    """Build code lines computing a single condition into a bool var.

    Returns (lines, result_var_name, min_bars_needed).
    Each condition assigns to a uniquely-named local bool (defaults False when
    any operand is None / insufficient data).
    """
    op = cond["op"]
    left = cond["left"]
    right = cond["right"]
    var = f"_c{idx}"
    lines: list[str] = []
    need = 0

    if op in _CROSS_OPS:
        # Need prev (offset 1) and now (offset 0) of both lines.
        l_now, n1 = _operand_expr(left, "0")
        l_prev, n2 = _operand_expr(left, "1")
        r_now, n3 = _operand_expr(right, "0")
        r_prev, n4 = _operand_expr(right, "1")
        need = max(n1, n2, n3, n4)
        lines.append(f"{indent}_ln = {l_now}")
        lines.append(f"{indent}_lp = {l_prev}")
        lines.append(f"{indent}_rn = {r_now}")
        lines.append(f"{indent}_rp = {r_prev}")
        lines.append(f"{indent}if _ln is None or _lp is None or _rn is None or _rp is None:")
        lines.append(f"{indent}    {var} = False")
        if op == "cross_above":
            lines.append(f"{indent}else:")
            lines.append(f"{indent}    {var} = (_lp <= _rp) and (_ln > _rn)")
        else:  # cross_below
            lines.append(f"{indent}else:")
            lines.append(f"{indent}    {var} = (_lp >= _rp) and (_ln < _rn)")
        return lines, var, need

    # Scalar comparison — compare now-values of both sides.
    l_now, n1 = _operand_expr(left, "0")
    r_now, n2 = _operand_expr(right, "0")
    need = max(n1, n2)
    # op ∈ {>,<,>=,<=} validated; dispatch via fixed literals (no raw splice).
    cmp = {">": ">", "<": "<", ">=": ">=", "<=": "<="}[op]
    lines.append(f"{indent}_lv = {l_now}")
    lines.append(f"{indent}_rv = {r_now}")
    lines.append(f"{indent}if _lv is None or _rv is None:")
    lines.append(f"{indent}    {var} = False")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    {var} = (_lv {cmp} _rv)")
    return lines, var, need


def _group_block(group_cfg: dict, indent: str) -> tuple[list[str], str, int]:
    """Build lines computing a whole buy/sell group into a single bool var.

    Returns (lines, result_var_name, min_bars_needed).
    """
    conditions = group_cfg["conditions"]
    logic = group_cfg.get("logic", "and")
    lines: list[str] = []
    cond_vars: list[str] = []
    need = 0
    for i, cond in enumerate(conditions):
        c_lines, c_var, c_need = _condition_expr(cond, indent, i)
        lines.extend(c_lines)
        cond_vars.append(c_var)
        need = max(need, c_need)

    joiner = " and " if logic == "and" else " or "
    result_var = "_group_ok"
    lines.append(f"{indent}{result_var} = {joiner.join(cond_vars)}")
    return lines, result_var, need


def compile_rule(cfg: dict) -> str:
    """Compile a rule_config dict into on_tick(ctx, params) Python source.

    Validates first (raises ValueError on illegal input), then emits source that:
      - inlines pure indicator helpers (no imports),
      - keeps module-level _pos/_entry across calls,
      - checks take-profit/stop-loss when holding (_pos > 0),
      - checks the buy group when flat, the sell group when holding,
      - only uses safe-whitelist builtins → passes validation.check_ast.
    """
    validate_rule_config(cfg)

    buy_cfg = cfg.get("buy") if cfg.get("buy") and cfg["buy"].get("conditions") else None
    sell_cfg = cfg.get("sell") if cfg.get("sell") and cfg["sell"].get("conditions") else None

    # sz — coerced to float, emitted as a number literal.
    sz_val = float(cfg["sz"]) if cfg.get("sz") is not None else 0.001

    risk = cfg.get("risk") or {}
    tp = risk.get("take_profit_pct")
    sl = risk.get("stop_loss_pct")
    tp_val = float(tp) if tp is not None else None
    sl_val = float(sl) if sl is not None else None

    max_need = 30  # minimum lookback floor
    body: list[str] = []

    # --- take-profit / stop-loss block (only when holding) ------------------
    risk_lines: list[str] = []
    if tp_val is not None or sl_val is not None:
        risk_lines.append("        if _entry > 0:")
        risk_lines.append("            _chg = (cur_price - _entry) / _entry * 100.0")
        conds: list[str] = []
        if tp_val is not None:
            conds.append(f"_chg >= {tp_val!r}")
        if sl_val is not None:
            conds.append(f"_chg <= -{sl_val!r}")
        risk_lines.append(f"            if {' or '.join(conds)}:")
        risk_lines.append("                try:")
        risk_lines.append("                    ctx.sell(_pos)")
        risk_lines.append('                    ctx.log("sell", "visual: risk exit chg=" + str(round(_chg, 4)) + "%")')
        risk_lines.append("                except Exception as _e:")
        risk_lines.append('                    ctx.log("error", "visual: risk sell failed: " + str(_e))')
        risk_lines.append("                _pos = 0.0")
        risk_lines.append("                _entry = 0.0")
        risk_lines.append("                return")

    # --- buy group (only when flat) -----------------------------------------
    buy_lines: list[str] = []
    if buy_cfg is not None:
        g_lines, g_var, g_need = _group_block(buy_cfg, "            ")
        max_need = max(max_need, g_need)
        buy_lines.append("        if _pos <= 0:")
        buy_lines.extend(g_lines)
        buy_lines.append(f"            if {g_var}:")
        buy_lines.append(f"                _sz = {sz_val!r}")
        buy_lines.append("                try:")
        buy_lines.append("                    ctx.buy(_sz)")
        buy_lines.append('                    ctx.log("buy", "visual: buy signal sz=" + str(_sz))')
        buy_lines.append("                    _pos = _pos + _sz")
        buy_lines.append("                    _entry = cur_price")
        buy_lines.append("                except Exception as _e:")
        buy_lines.append('                    ctx.log("error", "visual: buy failed: " + str(_e))')
        buy_lines.append("                return")

    # --- sell group (only when holding) -------------------------------------
    sell_lines: list[str] = []
    if sell_cfg is not None:
        g_lines, g_var, g_need = _group_block(sell_cfg, "            ")
        max_need = max(max_need, g_need)
        sell_lines.append("        if _pos > 0:")
        sell_lines.extend(g_lines)
        sell_lines.append(f"            if {g_var}:")
        sell_lines.append("                try:")
        sell_lines.append("                    ctx.sell(_pos)")
        sell_lines.append('                    ctx.log("sell", "visual: sell signal")')
        sell_lines.append("                except Exception as _e:")
        sell_lines.append('                    ctx.log("error", "visual: sell failed: " + str(_e))')
        sell_lines.append("                _pos = 0.0")
        sell_lines.append("                _entry = 0.0")
        sell_lines.append("                return")

    # limit: enough bars for the deepest indicator + slack.
    limit = int(max_need) + 5

    # --- assemble on_tick ---------------------------------------------------
    parts: list[str] = []
    parts.append('"""Auto-generated by rule_compiler from a visual rule_config.')
    parts.append("Do not edit by hand — regenerate from the rule_config JSON.")
    parts.append('"""')
    parts.append("")
    parts.append(_INDICATOR_HELPERS)
    parts.append("")
    parts.append("_pos = 0.0")
    parts.append("_entry = 0.0")
    parts.append("")
    parts.append("")
    parts.append("def on_tick(ctx, params):")
    parts.append("    global _pos, _entry")
    parts.append("    candles = ctx.candles()")
    parts.append("    if not candles:")
    parts.append("        return")
    parts.append(f"    _lim = {limit!r}")
    parts.append("    if len(candles) > _lim:")
    parts.append("        candles = candles[-_lim:]")
    parts.append('    closes = [float(c["c"]) for c in candles]')
    parts.append('    volumes = [float(c["vol"]) for c in candles]')
    parts.append("    if not closes:")
    parts.append("        return")
    parts.append("    cur_price = closes[-1]")
    # Wrap logic in a try to keep a single tick failure from crashing the runner.
    parts.append("    try:")
    if risk_lines:
        parts.extend(risk_lines)
    if buy_lines:
        parts.extend(buy_lines)
    if sell_lines:
        parts.extend(sell_lines)
    parts.append("        return")
    parts.append("    except Exception as _e:")
    parts.append('        ctx.log("error", "visual: on_tick error: " + str(_e))')
    parts.append("        return")
    parts.append("")

    return "\n".join(parts)
