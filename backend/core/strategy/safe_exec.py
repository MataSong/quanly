"""Safe exec for user-uploaded Python strategy code.

⚠️  POSITIONING WARNING ⚠️
This module is an INPUT-CLEANING / EARLY-ERROR layer, NOT a security boundary.
The real security boundary is container isolation (cap_drop / read_only filesystem /
network isolation / non-root user / pids_limit) implemented in T7.

Do NOT rely on this module alone to prevent malicious code execution.
Do NOT use exec_strategy() in a web/worker main process as the sole protection
against untrusted code.  exec_strategy() should only be called from inside an
already-isolated container environment.

Security model (defence-in-depth, not sole protection):
  - __builtins__ is replaced with a strict whitelist of pure-compute builtins.
  - __import__ is replaced with a controlled wrapper that only allows
    importing modules from ALLOWED_MODULES whitelist.
  - Even if AST checks are somehow bypassed, exec-time restrictions apply.
  - on_tick is extracted but NOT called here; calling happens in T3 trial-run
    and in the production runner, both inside network-isolated containers.
"""
from __future__ import annotations

import builtins
from typing import Callable


# ---------------------------------------------------------------------------
# Safe builtins whitelist
# ---------------------------------------------------------------------------

#: Safe builtin names: pure-compute / data-manipulation only.
#: Deliberately excludes: open, eval, exec, compile, __import__, globals,
#: locals, vars, input, getattr, setattr, delattr, hasattr, memoryview,
#: breakpoint, classmethod, staticmethod, super, property, object, type,
#: __loader__, __spec__, __build_class__, etc.
_SAFE_BUILTIN_NAMES = {
    # Numeric / math
    "abs", "divmod", "pow", "round",
    # Comparison / logic
    "all", "any", "min", "max",
    # Sequence / iteration
    "len", "range", "sum", "sorted", "reversed", "enumerate", "zip",
    "map", "filter",
    # Type constructors (pure data)
    "float", "int", "str", "list", "dict", "tuple", "set", "frozenset",
    "bool", "bytes", "bytearray",
    # Inspection (safe subset — no dynamic dispatch)
    "isinstance", "issubclass",
    # Output (non-harmful for logging)
    "print",
    # Misc pure utilities
    "repr", "hash", "id", "hex", "oct", "bin", "ord", "chr",
    "format", "iter", "next", "slice",
    # Exceptions (needed for try/except in user code)
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration", "NotImplementedError",
    "ZeroDivisionError", "OverflowError", "ArithmeticError",
    "ImportError", "ModuleNotFoundError", "NameError", "LookupError",
    "AssertionError", "OSError", "IOError",
    # Constants
    "True", "False", "None",
    # NotImplemented sentinel
    "NotImplemented",
}

#: Modules that user code is permitted to import at exec time.
ALLOWED_MODULES: frozenset[str] = frozenset({
    "math",
    "statistics",
    "json",
    "datetime",
    "decimal",
    "numpy",
    "pandas",
})


def build_safe_builtins() -> dict:
    """Return a restricted __builtins__ dict containing only safe entries.

    The returned dict is a *copy* — mutations by user code do not affect the
    real builtins module.
    """
    safe: dict = {}
    real_builtins = vars(builtins)
    for name in _SAFE_BUILTIN_NAMES:
        if name in real_builtins:
            safe[name] = real_builtins[name]
    # Controlled __import__ is injected by exec_strategy, not here, so that
    # the allowed_modules set can be parameterised per call.
    return safe


def _make_controlled_import(allowed_modules: frozenset[str]) -> Callable:
    """Return a __import__ replacement that whitelists module imports.

    Only top-level package names are checked; e.g. ``from numpy.linalg import …``
    resolves to top-level package ``numpy`` which is allowed.
    """

    def _controlled_import(name: str, globals=None, locals=None,
                           fromlist=(), level=0) -> object:
        # Relative imports (level > 0) are forbidden.
        if level != 0:
            raise ImportError(
                f"Relative imports are not allowed in user strategy code "
                f"(attempted: level={level}, name={name!r})"
            )
        # Check top-level package name.
        top_level = name.split(".")[0]
        if top_level not in allowed_modules:
            raise ImportError(
                f"Import of '{top_level}' is not allowed in user strategy code. "
                f"Allowed modules: {sorted(allowed_modules)}"
            )
        # Delegate to the real import machinery for allowed modules.
        return builtins.__import__(name, globals, locals, fromlist, level)

    return _controlled_import


def exec_strategy(code: str, allowed_modules: set[str] | None = None) -> Callable:
    """Execute user strategy code in a controlled namespace and return on_tick.

    Args:
        code: The user-uploaded Python source code.
        allowed_modules: Override the default ALLOWED_MODULES whitelist.
            Defaults to ALLOWED_MODULES defined in this module.

    Returns:
        The ``on_tick(ctx, params)`` callable defined in *code*.

    Raises:
        SyntaxError: If *code* has syntax errors (from compile step inside exec).
        ImportError: If *code* attempts to import a non-whitelisted module.
        ValueError: If *code* does not define a callable ``on_tick``.

    Security notes:
        - __builtins__ is replaced with the safe whitelist from
          build_safe_builtins().  This removes open/eval/exec/__import__ etc.
        - A custom __import__ is installed that only allows whitelisted modules,
          providing a second layer even if the AST check was somehow bypassed.
        - on_tick is extracted but NOT called here.
    """
    _allowed: frozenset[str] = (
        frozenset(allowed_modules) if allowed_modules is not None else ALLOWED_MODULES
    )

    safe_builtins = build_safe_builtins()
    # Install the controlled __import__ so module-level import statements work
    # for whitelisted modules but fail for anything else.
    safe_builtins["__import__"] = _make_controlled_import(_allowed)

    namespace: dict = {"__builtins__": safe_builtins}

    # exec runs module-level code (import statements, function definitions, etc.)
    exec(code, namespace)  # noqa: S102  — intentional controlled exec

    on_tick = namespace.get("on_tick")
    if not callable(on_tick):
        raise ValueError(
            "User strategy code must define a callable 'on_tick(ctx, params)' "
            f"function. Got: {type(on_tick)!r}"
        )
    return on_tick
