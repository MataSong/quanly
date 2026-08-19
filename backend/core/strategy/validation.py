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
