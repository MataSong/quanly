"""Static validation for user-uploaded Python strategy code.

⚠️  POSITIONING WARNING ⚠️
This module is an INPUT-CLEANING / EARLY-ERROR layer, NOT a security boundary.
The real security boundary is container isolation (cap_drop / read_only filesystem /
network isolation / non-root user / pids_limit) implemented in T7.

Do NOT rely on this module alone to prevent malicious code execution.
Do NOT use exec_strategy() in a web/worker main process as the sole protection
against untrusted code.  This layer exists to:
  1. Catch obvious mistakes and give friendly error messages to honest users.
  2. Reduce noise by blocking clearly malicious submissions early.
  3. Serve as defence-in-depth alongside (not instead of) container isolation.

Two layers of static checking, performed before controlled exec (safe_exec):

1. check_syntax: fast compile() pass — catches SyntaxErrors early.
2. check_ast:   AST walk — enforces security policy:
     - Import whitelist (only ALLOWED_MODULES).
     - Dangerous built-in call blacklist.
     - ALL dunder attribute access (node.attr.startswith("__")) is blocked —
       this is broader than a per-name blacklist and catches frame/traceback
       escape chains like e.__traceback__.tb_frame.f_back.f_builtins["__import__"].
     - frame/traceback/generator internal attribute names (tb_frame, f_back, etc.).
     - Dangerous name references (eval / exec / __import__ / open referenced
       directly, even without calling).
     - Mandatory on_tick(ctx, params) top-level function definition.

No Django dependencies — these are pure Python functions safe to run outside
any request context and in unit tests without a database.
"""
from __future__ import annotations

import ast
import json
from typing import TypedDict


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

#: Only these top-level module names may appear in import statements.
ALLOWED_MODULES: frozenset[str] = frozenset({
    "math",
    "statistics",
    "json",
    "datetime",
    "decimal",
    "numpy",
    "pandas",
})

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class SyntaxResult(TypedDict):
    ok: bool
    line: int | None
    msg: str | None


class Violation(TypedDict):
    line: int
    rule: str
    detail: str


class ASTResult(TypedDict):
    ok: bool
    violations: list[Violation]


# ---------------------------------------------------------------------------
# Layer 1: Syntax check
# ---------------------------------------------------------------------------


def check_syntax(code: str) -> SyntaxResult:
    """Attempt to compile *code* and report any SyntaxError.

    Returns:
        ``{"ok": True}`` on success,
        ``{"ok": False, "line": <lineno>, "msg": <message>}`` on failure.
    """
    try:
        compile(code, "<strategy>", "exec")
    except SyntaxError as exc:
        return SyntaxResult(ok=False, line=exc.lineno, msg=str(exc))
    return SyntaxResult(ok=True, line=None, msg=None)


# ---------------------------------------------------------------------------
# Layer 2: AST security check
# ---------------------------------------------------------------------------

#: Function/variable names that are dangerous even when merely referenced
#: (not just when called).
_DANGEROUS_NAMES: frozenset[str] = frozenset({
    "eval",
    "exec",
    "__import__",
    "open",
    "compile",
    "input",
    "breakpoint",
})

#: Function call names that are explicitly forbidden.
_FORBIDDEN_CALLS: frozenset[str] = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "globals",
    "locals",
    "vars",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "memoryview",
    "breakpoint",
})

#: Attribute names (accessed via dot notation) that are forbidden.
#:
#: STRATEGY: we block ALL dunder attributes (names starting with "__") rather
#: than maintaining an exhaustive per-name blacklist.  CPython has too many
#: dunder-based escape vectors to enumerate reliably.  Legitimate trading
#: strategy code (ctx.candles / ctx.buy / ctx.sell / ctx.log) never needs to
#: access any __xxx__ attribute on any object.
#:
#: Additionally we block frame/traceback/generator internal attribute names
#: that are NOT dunders but enable the classic traceback-frame RCE chain:
#:   try: raise ValueError()
#:   except ValueError as e:
#:       e.__traceback__.tb_frame.f_back.f_builtins["__import__"]("os").system(…)
#: The __traceback__ access is caught by the all-dunder rule; tb_frame / f_back /
#: f_builtins are caught by this explicit set.
_FORBIDDEN_FRAME_ATTRS: frozenset[str] = frozenset({
    # traceback object internals
    "tb_frame",
    "tb_next",
    "tb_lineno",
    "tb_lasti",
    # frame object internals
    "f_back",
    "f_globals",
    "f_builtins",
    "f_locals",
    "f_code",
    "f_lineno",
    "f_lasti",
    "f_trace",
    # generator/coroutine/async-generator internals
    "gi_frame",
    "gi_code",
    "cr_frame",
    "cr_code",
    "ag_frame",
    "ag_code",
})


def _top_level_module(name: str) -> str:
    """Return the top-level package name from a potentially dotted import."""
    return name.split(".")[0]


class _SecurityVisitor(ast.NodeVisitor):
    """AST visitor that accumulates security violations."""

    def __init__(self) -> None:
        self.violations: list[Violation] = []
        self._has_on_tick = False
        self._on_tick_valid = False

    def _add(self, node: ast.AST, rule: str, detail: str) -> None:
        line = getattr(node, "lineno", 0)
        self.violations.append(Violation(line=line, rule=rule, detail=detail))

    # -- Import checks -------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            top = _top_level_module(alias.name)
            if top not in ALLOWED_MODULES:
                self._add(
                    node,
                    rule="forbidden_import",
                    detail=f"import '{alias.name}' is not allowed; "
                           f"allowed: {sorted(ALLOWED_MODULES)}",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        top = _top_level_module(module) if module else ""
        # Relative imports (level > 0) with no module name are also forbidden.
        if node.level and node.level > 0:
            self._add(
                node,
                rule="forbidden_import",
                detail="Relative imports are not allowed in user strategy code.",
            )
        elif top not in ALLOWED_MODULES:
            self._add(
                node,
                rule="forbidden_import",
                detail=f"from '{module}' import … is not allowed; "
                       f"allowed: {sorted(ALLOWED_MODULES)}",
            )
        self.generic_visit(node)

    # -- Call checks ---------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        name: str | None = None

        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr  # e.g. obj.eval(…)

        if name and name in _FORBIDDEN_CALLS:
            self._add(
                node,
                rule="forbidden_call",
                detail=f"Call to '{name}' is forbidden in user strategy code.",
            )
        self.generic_visit(node)

    # -- Attribute / dunder access checks ------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        attr = node.attr
        # Block ALL dunder attributes — any name starting with "__".
        # Legitimate strategy code never needs __xxx__ on any object.
        if attr.startswith("__"):
            self._add(
                node,
                rule="forbidden_attr",
                detail=f"Access to dunder attribute '{attr}' is forbidden "
                       "(all dunder attributes are blocked to prevent sandbox escapes).",
            )
        # Also block frame/traceback/generator internals that are not dunders
        # but enable the traceback-frame RCE escape chain.
        elif attr in _FORBIDDEN_FRAME_ATTRS:
            self._add(
                node,
                rule="forbidden_attr",
                detail=f"Access to frame/traceback attribute '{attr}' is forbidden "
                       "(potential sandbox escape via traceback frame chain).",
            )
        self.generic_visit(node)

    # -- Dangerous name references -------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id in _DANGEROUS_NAMES:
            self._add(
                node,
                rule="forbidden_name",
                detail=f"Reference to dangerous name '{node.id}' is forbidden.",
            )
        self.generic_visit(node)

    # -- on_tick presence / signature check ----------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        # Only check top-level definitions (parent is Module).
        # We detect top-level by checking that we haven't descended: the
        # visitor's generic_visit call structure means we need a depth counter.
        # Use a simpler approach: collect all top-level defs in check_ast.
        if node.name == "on_tick":
            self._has_on_tick = True
            args = node.args
            # Count positional parameters (args.args).  Must be exactly 2.
            n_pos = len(args.args)
            if n_pos == 2:
                self._on_tick_valid = True
        self.generic_visit(node)

    # AsyncFunctionDef is not expected but check it too.
    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]


def check_ast(code: str) -> ASTResult:
    """Parse *code* and perform a full security AST walk.

    Checks:
    - Import/ImportFrom: top-level module must be in ALLOWED_MODULES.
    - Call: function name must not be in _FORBIDDEN_CALLS.
    - Attribute: ALL dunder names (attr.startswith("__")) are blocked;
      additionally frame/traceback/generator internals in _FORBIDDEN_FRAME_ATTRS.
    - Name: identifier must not be in _DANGEROUS_NAMES.
    - Top-level ``on_tick(ctx, params)`` function must be present with exactly
      2 positional parameters.

    Returns:
        ``{"ok": True, "violations": []}`` if clean,
        ``{"ok": False, "violations": [{"line":…, "rule":…, "detail":…}]}``
        otherwise.
    """
    try:
        tree = ast.parse(code, filename="<strategy>")
    except SyntaxError as exc:
        return ASTResult(
            ok=False,
            violations=[
                Violation(
                    line=exc.lineno or 0,
                    rule="syntax_error",
                    detail=str(exc),
                )
            ],
        )

    # Detect top-level on_tick (only Module-level FunctionDef nodes).
    top_level_on_tick = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "on_tick":
                top_level_on_tick = node

    visitor = _SecurityVisitor()
    visitor.visit(tree)

    violations = list(visitor.violations)

    # Validate on_tick at module level (visitor catches nested too, but the
    # required-presence check uses our explicit top-level scan).
    if top_level_on_tick is None:
        violations.append(
            Violation(
                line=0,
                rule="missing_on_tick",
                detail="User strategy code must define a top-level "
                       "'on_tick(ctx, params)' function.",
            )
        )
    else:
        args = top_level_on_tick.args
        n_pos = len(args.args)
        if n_pos != 2:
            violations.append(
                Violation(
                    line=top_level_on_tick.lineno,
                    rule="invalid_on_tick_signature",
                    detail=f"on_tick must have exactly 2 positional parameters "
                           f"(ctx, params); found {n_pos}.",
                )
            )

    return ASTResult(ok=len(violations) == 0, violations=violations)


# ---------------------------------------------------------------------------
# Layer 3: Trial run (isolated container)
#
# SECURITY: user code is NEVER exec'd in this (web/worker) main process. We spin
# up a one-shot, fully-isolated container running the strategy-runner in
# TRIAL_MODE and only read a single line of result JSON from its stdout. The
# container is the security boundary:
#   - network_disabled=True (trial is 100% offline — stricter than the isolated
#     network the live runner uses)
#   - cap_drop=ALL / read_only rootfs / no-new-privileges
#   - mem_limit / pids_limit (fork-bomb guard) / tmpfs writable /tmp only
# ---------------------------------------------------------------------------

#: Runner image (built with numpy/pandas). Same image the live runner uses.
_TRIAL_IMAGE = "quanly-strategy-runner"
#: Max seconds to wait for the trial container to exit before killing it.
_TRIAL_TIMEOUT = 30
#: Cap on ticks fed to the trial (one on_tick per synthetic bar).
_TRIAL_MAX_TICKS = "200"


class TrialResult(TypedDict, total=False):
    ok: bool
    signal_count: int
    error: str
    tick: int


def _build_trial_candles() -> list[dict]:
    """Build ~150 synthetic candles with an up-trend then a down-trend.

    The sequence rises, spikes, holds high, then crashes and stays low — this
    guarantees a moving-average style strategy produces both buy and sell
    signals so the trial exercises real signal paths. Format matches the runner
    contract: [{ts, o, h, l, c, vol, volCcy}, ...] oldest-first.
    """
    candles: list[dict] = []
    t = 1_000_000
    step = 60_000  # 1-minute bars

    def _bar(o: float, h: float, l: float, c: float) -> dict:  # noqa: E741
        return {
            "ts": t,
            "o": f"{o}",
            "h": f"{h}",
            "l": f"{l}",
            "c": f"{c}",
            "vol": "1",
            "volCcy": "1",
        }

    # 40 flat bars (baseline → MAs converge)
    for _ in range(40):
        candles.append(_bar(100.0, 100.0, 100.0, 100.0))
        t += step
    # 30 bars ramping up (golden cross territory)
    price = 100.0
    for _ in range(30):
        nxt = price + 5.0
        candles.append(_bar(price, nxt, price, nxt))
        price = nxt
        t += step
    # 20 bars holding high
    for _ in range(20):
        candles.append(_bar(price, price, price, price))
        t += step
    # 30 bars ramping down (death cross territory)
    for _ in range(30):
        nxt = max(10.0, price - 5.0)
        candles.append(_bar(price, price, nxt, nxt))
        price = nxt
        t += step
    # 30 bars holding low
    for _ in range(30):
        candles.append(_bar(price, price, price, price))
        t += step

    return candles


def check_trial_run(code: str) -> TrialResult:
    """Dry-run *code* inside a one-shot, fully-isolated container.

    NEVER execs user code in this process — it only launches a container running
    the strategy-runner in TRIAL_MODE against synthetic candles and reads the
    single-line JSON result from stdout.

    Returns:
        ``{"ok": True, "signal_count": N}`` on a clean trial,
        ``{"ok": False, "error": "...", "tick": i?}`` on any failure.

    Degrades gracefully:
        - docker unavailable            → ``{"ok": False, "error": "trial unavailable"}``
        - container won't start/timeout → ``{"ok": False, "error": "..."}``
        - non-JSON / empty stdout       → ``{"ok": False, "error": "..."}``
    """
    try:
        import docker  # type: ignore[import]
    except Exception:  # noqa: BLE001 — SDK missing → degrade, don't crash
        return TrialResult(ok=False, error="trial unavailable")

    try:
        client = docker.from_env()
    except Exception:  # noqa: BLE001 — daemon unreachable → degrade
        return TrialResult(ok=False, error="trial unavailable")

    candles = _build_trial_candles()
    trial_env = {
        "TRIAL_MODE": "1",
        "TRIAL_CANDLES": json.dumps(candles),
        "USER_CODE": code,
        "TRIAL_MAX_TICKS": _TRIAL_MAX_TICKS,
    }

    container = None
    try:
        container = client.containers.run(
            _TRIAL_IMAGE,
            detach=True,
            environment=trial_env,
            mem_limit="256m",
            cpu_quota=50000,       # 50% of one CPU
            cap_drop=["ALL"],
            read_only=True,
            security_opt=["no-new-privileges:true"],
            pids_limit=128,        # fork-bomb guard
            network_disabled=True,  # trial is fully offline — no network at all
            tmpfs={"/tmp": "size=64m,mode=1777"},
        )
    except Exception as exc:  # noqa: BLE001 — start failure
        # Best-effort cleanup if a partial container object came back.
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass
        return TrialResult(ok=False, error=f"trial container failed to start: {exc}")

    try:
        try:
            container.wait(timeout=_TRIAL_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 — timeout or wait error → kill
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                pass
            return TrialResult(ok=False, error=f"trial timed out: {exc}")

        # stdout only — user print() goes to stderr and won't pollute the result.
        try:
            raw = container.logs(stdout=True, stderr=False)
        except Exception as exc:  # noqa: BLE001
            return TrialResult(ok=False, error=f"trial log read failed: {exc}")

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        text = (raw or "").strip()
        if not text:
            return TrialResult(ok=False, error="trial produced no result")

        # Result is a single-line JSON object; take the last non-empty line to be
        # robust against any stray output ahead of it.
        last_line = text.splitlines()[-1].strip()
        try:
            parsed = json.loads(last_line)
        except (json.JSONDecodeError, ValueError) as exc:
            return TrialResult(ok=False, error=f"trial result not JSON: {exc}")

        if not isinstance(parsed, dict):
            return TrialResult(ok=False, error="trial result not an object")

        result = TrialResult(ok=bool(parsed.get("ok")))
        if result["ok"]:
            result["signal_count"] = int(parsed.get("signal_count", 0))
        else:
            result["error"] = str(parsed.get("error", "trial failed"))
            if "tick" in parsed:
                try:
                    result["tick"] = int(parsed["tick"])
                except (TypeError, ValueError):
                    pass
        return result
    finally:
        try:
            container.remove(force=True)
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass


# ---------------------------------------------------------------------------
# Three-layer combinator
# ---------------------------------------------------------------------------


def validate_strategy_code(code: str) -> dict:
    """Run the full three-layer check pipeline over user *code*.

    Order (fast → slow, short-circuit on first failure):
      1. check_syntax  — compile() pass.
      2. check_ast     — AST security policy.
      3. check_trial_run — isolated-container dry run (only reached if 1 & 2 pass;
         the container is the sole place user code executes).

    Returns a dict shaped for the Strategy.check_status / check_report fields::

        {"check_status": "passed"|"failed", "check_report": {"stage": ..., ...}}

    The container (slow) is only started once syntax + AST (fast) both pass, so a
    submission with a forbidden import never launches a container.
    """
    # Lazy import so this module stays importable without Django loaded.
    from core.strategy.models import Strategy

    # Layer 1: syntax.
    syntax = check_syntax(code)
    if not syntax["ok"]:
        return {
            "check_status": Strategy.CHECK_FAILED,
            "check_report": {
                "stage": "syntax",
                "line": syntax["line"],
                "msg": syntax["msg"],
            },
        }

    # Layer 2: AST security.
    ast_result = check_ast(code)
    if not ast_result["ok"]:
        return {
            "check_status": Strategy.CHECK_FAILED,
            "check_report": {
                "stage": "ast",
                "violations": ast_result["violations"],
            },
        }

    # Layer 3: isolated-container trial run.
    trial = check_trial_run(code)
    if not trial.get("ok"):
        report: dict = {"stage": "trial", "ok": False, "error": trial.get("error", "trial failed")}
        if "tick" in trial:
            report["tick"] = trial["tick"]
        return {
            "check_status": Strategy.CHECK_FAILED,
            "check_report": report,
        }

    return {
        "check_status": Strategy.CHECK_PASSED,
        "check_report": {
            "stage": "trial",
            "ok": True,
            "signal_count": trial.get("signal_count", 0),
        },
    }
