"""Static validation for user-uploaded Python strategy code.

Two layers of static checking, performed before controlled exec (safe_exec):

1. check_syntax: fast compile() pass — catches SyntaxErrors early.
2. check_ast:   AST walk — enforces security policy:
     - Import whitelist (only ALLOWED_MODULES).
     - Dangerous built-in call blacklist.
     - Dangerous dunder attribute access blacklist (sandbox-escape via
       __class__/__bases__/__subclasses__/etc.).
     - Dangerous name references (eval / exec / __import__ / open referenced
       directly, even without calling).
     - Mandatory on_tick(ctx, params) top-level function definition.

No Django dependencies — these are pure Python functions safe to run outside
any request context and in unit tests without a database.
"""
from __future__ import annotations

import ast
import sys
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

#: Attribute names (accessed via dot notation) that are forbidden — these are
#: the classic vectors for CPython sandbox escapes.
_FORBIDDEN_ATTRS: frozenset[str] = frozenset({
    "__subclasses__",
    "__globals__",
    "__class__",
    "__bases__",
    "__mro__",
    "__dict__",
    "__builtins__",
    "__import__",
    "__code__",
    "__closure__",
    "__func__",
    "__self__",
    "__wrapped__",
    "__loader__",
    "__spec__",
    "__init_subclass__",
    "__reduce__",
    "__reduce_ex__",
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
        if attr in _FORBIDDEN_ATTRS:
            self._add(
                node,
                rule="forbidden_attr",
                detail=f"Access to attribute '{attr}' is forbidden "
                       "(potential sandbox escape).",
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
    - Attribute: attribute name must not be in _FORBIDDEN_ATTRS.
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
