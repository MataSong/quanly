"""Security-focused tests for UC-T2: AST validation + safe exec.

These tests are pure-Python and do NOT require a database — validation.py and
safe_exec.py have no Django model dependencies.  pytest-django is still loaded
because the project's conftest sets DJANGO_SETTINGS_MODULE, but no DB fixtures
are used here.

Test categories:
  1. check_syntax — valid code, syntax errors.
  2. check_ast — allowed imports, blocked imports, forbidden calls,
     forbidden attribute access, missing/invalid on_tick.
  3. exec_strategy — happy path, blocked import at exec time, no on_tick.
  4. Escape-attempt payloads — classic CPython sandbox escapes must be caught
     by AST *and/or* by the restricted builtins namespace at exec time.
"""
from __future__ import annotations

import pytest

from core.strategy.validation import check_syntax, check_ast, ALLOWED_MODULES
from core.strategy.safe_exec import exec_strategy, build_safe_builtins


# ===========================================================================
# Fixtures / helpers
# ===========================================================================

#: A minimal valid strategy that should pass all checks.
VALID_STRATEGY = """
import math

def on_tick(ctx, params):
    candles = ctx.candles
    if len(candles) < 2:
        return
    price = float(candles[-1]['close'])
    threshold = float(params.get('threshold', 0))
    if price > threshold:
        ctx.buy(price)
    else:
        ctx.sell(price)
    ctx.log(f"price={price}")
"""

#: Strategy using several allowed imports.
VALID_MULTI_IMPORT = """
import math
import statistics
import json
import datetime
import decimal
from math import sqrt, floor
from statistics import mean

def on_tick(ctx, params):
    data = [float(c['close']) for c in ctx.candles]
    avg = mean(data) if data else 0.0
    ctx.log(str(avg))
"""


def _violations_rules(result: dict) -> list[str]:
    return [v["rule"] for v in result["violations"]]


def _has_rule(result: dict, rule: str) -> bool:
    return rule in _violations_rules(result)


# ===========================================================================
# 1. check_syntax
# ===========================================================================

class TestCheckSyntax:
    def test_valid_code_returns_ok(self):
        r = check_syntax(VALID_STRATEGY)
        assert r["ok"] is True

    def test_syntax_error_returns_not_ok_with_line(self):
        bad = "def on_tick(ctx, params)\n    pass\n"  # missing colon
        r = check_syntax(bad)
        assert r["ok"] is False
        assert isinstance(r["line"], int)
        assert r["line"] >= 1
        assert r["msg"]

    def test_syntax_error_message_is_human_readable(self):
        bad = "def on_tick(ctx, params)\n    x = (\n"
        r = check_syntax(bad)
        assert r["ok"] is False
        assert len(r["msg"]) > 0

    def test_empty_string_is_valid_syntax(self):
        r = check_syntax("")
        assert r["ok"] is True  # empty module is syntactically valid

    def test_indentation_error_caught(self):
        bad = "def on_tick(ctx, params):\n    x = 1\n  y = 2\n"
        r = check_syntax(bad)
        assert r["ok"] is False


# ===========================================================================
# 2. check_ast — allowed
# ===========================================================================

class TestCheckASTAllowed:
    def test_valid_strategy_passes(self):
        r = check_ast(VALID_STRATEGY)
        assert r["ok"] is True, r["violations"]

    def test_multiple_allowed_imports_pass(self):
        r = check_ast(VALID_MULTI_IMPORT)
        assert r["ok"] is True, r["violations"]

    def test_from_math_import_passes(self):
        code = "from math import sqrt\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]

    def test_from_numpy_import_passes(self):
        code = "from numpy import array\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]

    def test_from_pandas_import_passes(self):
        code = "from pandas import DataFrame\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]

    def test_all_allowed_modules_accepted(self):
        for mod in ALLOWED_MODULES:
            code = f"import {mod}\ndef on_tick(ctx, params):\n    pass\n"
            r = check_ast(code)
            assert r["ok"] is True, f"module {mod!r} was unexpectedly rejected"

    def test_on_tick_with_ctx_operations_passes(self):
        code = """
def on_tick(ctx, params):
    candles = ctx.candles
    price = float(candles[-1]['close'])
    ctx.buy(price)
    ctx.sell(price)
    ctx.log("ok")
"""
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]

    def test_nested_function_defs_allowed(self):
        code = """
def on_tick(ctx, params):
    def helper(x):
        return x * 2
    ctx.log(str(helper(1)))
"""
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]

    def test_list_comprehension_allowed(self):
        code = """
import math
def on_tick(ctx, params):
    vals = [math.sqrt(float(c['close'])) for c in ctx.candles]
    ctx.log(str(vals))
"""
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]


# ===========================================================================
# 3. check_ast — forbidden imports
# ===========================================================================

class TestCheckASTForbiddenImports:
    def test_import_os_blocked(self):
        code = "import os\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_socket_blocked(self):
        code = "import socket\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_subprocess_blocked(self):
        code = "import subprocess\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_sys_blocked(self):
        code = "import sys\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_ctypes_blocked(self):
        code = "import ctypes\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_from_os_import_system_blocked(self):
        code = "from os import system\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_from_os_path_import_join_blocked(self):
        code = "from os.path import join\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_inside_function_blocked(self):
        """Import inside function body must also be caught."""
        code = """
def on_tick(ctx, params):
    import os
    os.system("id")
"""
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_io_blocked(self):
        code = "import io\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")

    def test_import_importlib_blocked(self):
        code = "import importlib\ndef on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_import")


# ===========================================================================
# 4. check_ast — forbidden calls
# ===========================================================================

class TestCheckASTForbiddenCalls:
    def test_eval_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    eval("1+1")\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call") or _has_rule(r, "forbidden_name")

    def test_exec_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    exec("x=1")\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_open_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    open("/etc/passwd")\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call") or _has_rule(r, "forbidden_name")

    def test_dunder_import_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    __import__("os")\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_getattr_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    getattr(ctx, "secret")\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call")

    def test_setattr_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    setattr(ctx, "x", 1)\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call")

    def test_delattr_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    delattr(ctx, "x")\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call")

    def test_hasattr_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    hasattr(ctx, "secret")\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call")

    def test_globals_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    g = globals()\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call") or _has_rule(r, "forbidden_name")

    def test_locals_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    l = locals()\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_vars_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    v = vars()\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_input_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = input("prompt")\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_compile_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    compile("x=1","<>","exec")\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_memoryview_call_blocked(self):
        code = 'def on_tick(ctx, params):\n    memoryview(b"data")\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_call")

    def test_forbidden_calls_inside_nested_function_blocked(self):
        """Calls inside nested function bodies must also be caught."""
        code = """
def on_tick(ctx, params):
    def helper():
        return eval("1")
    helper()
"""
        r = check_ast(code)
        assert r["ok"] is False


# ===========================================================================
# 5. check_ast — forbidden attribute access (dunder)
# ===========================================================================

class TestCheckASTForbiddenAttributes:
    def test_class_attr_blocked(self):
        """() .__class__ — classic CPython escape step 1."""
        code = 'def on_tick(ctx, params):\n    x = ().__class__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_bases_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = ().__class__.__bases__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_subclasses_attr_blocked(self):
        """Full classic escape: ().__class__.__bases__[0].__subclasses__()"""
        code = (
            "def on_tick(ctx, params):\n"
            "    x = ().__class__.__bases__[0].__subclasses__()\n"
        )
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_globals_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = on_tick.__globals__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_builtins_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = on_tick.__globals__["__builtins__"]\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_code_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = on_tick.__code__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_mro_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = int.__mro__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_dict_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = ctx.__dict__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_import_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = ctx.__import__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")

    def test_closure_attr_blocked(self):
        code = 'def on_tick(ctx, params):\n    x = on_tick.__closure__\n'
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_attr")


# ===========================================================================
# 6. check_ast — dangerous name references
# ===========================================================================

class TestCheckASTDangerousNames:
    def test_eval_name_reference_blocked(self):
        """Assigning eval to a variable (not calling) is also forbidden."""
        code = "def on_tick(ctx, params):\n    fn = eval\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "forbidden_name") or _has_rule(r, "forbidden_call")

    def test_exec_name_reference_blocked(self):
        code = "def on_tick(ctx, params):\n    fn = exec\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_open_name_reference_blocked(self):
        code = "def on_tick(ctx, params):\n    fn = open\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_dunder_import_name_reference_blocked(self):
        code = "def on_tick(ctx, params):\n    fn = __import__\n"
        r = check_ast(code)
        assert r["ok"] is False


# ===========================================================================
# 7. check_ast — on_tick validation
# ===========================================================================

class TestCheckASTOnTick:
    def test_missing_on_tick_returns_violation(self):
        code = "import math\nx = 1\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "missing_on_tick")

    def test_on_tick_with_zero_params_invalid(self):
        code = "def on_tick():\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "invalid_on_tick_signature")

    def test_on_tick_with_one_param_invalid(self):
        code = "def on_tick(ctx):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "invalid_on_tick_signature")

    def test_on_tick_with_three_params_invalid(self):
        code = "def on_tick(ctx, params, extra):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "invalid_on_tick_signature")

    def test_on_tick_only_nested_not_accepted(self):
        """on_tick defined only inside another function is NOT accepted."""
        code = """
def wrapper():
    def on_tick(ctx, params):
        pass
"""
        r = check_ast(code)
        assert r["ok"] is False
        assert _has_rule(r, "missing_on_tick")

    def test_on_tick_with_correct_signature_valid(self):
        code = "def on_tick(ctx, params):\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]

    def test_on_tick_with_type_annotations_valid(self):
        """Type hints on parameters are fine — still 2 positional args."""
        code = "def on_tick(ctx: object, params: dict) -> None:\n    pass\n"
        r = check_ast(code)
        assert r["ok"] is True, r["violations"]


# ===========================================================================
# 8. exec_strategy — happy path
# ===========================================================================

class TestExecStrategyHappyPath:
    def test_exec_valid_strategy_returns_callable(self):
        fn = exec_strategy(VALID_STRATEGY)
        assert callable(fn)

    def test_exec_returns_on_tick_function(self):
        fn = exec_strategy(VALID_STRATEGY)
        assert fn.__name__ == "on_tick"

    def test_exec_multi_import_strategy_works(self):
        fn = exec_strategy(VALID_MULTI_IMPORT)
        assert callable(fn)

    def test_exec_with_math_import_works(self):
        code = """
import math
def on_tick(ctx, params):
    return math.pi
"""
        fn = exec_strategy(code)
        assert callable(fn)

    def test_exec_allowed_modules_override_works(self):
        """Custom allowed_modules parameter is respected."""
        code = "import math\ndef on_tick(ctx, params):\n    pass\n"
        fn = exec_strategy(code, allowed_modules={"math"})
        assert callable(fn)

    def test_exec_custom_allowed_module_blocks_default_module(self):
        """When using a custom allowed_modules, the default list is replaced."""
        code = "import statistics\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError):
            exec_strategy(code, allowed_modules={"math"})  # statistics not in custom set


# ===========================================================================
# 9. exec_strategy — blocked imports at exec time
# ===========================================================================

class TestExecStrategyBlockedImports:
    def test_exec_import_os_raises_import_error(self):
        """Even without AST check, exec_strategy must block os import."""
        code = "import os\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError, match="os"):
            exec_strategy(code)

    def test_exec_import_subprocess_raises_import_error(self):
        code = "import subprocess\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_exec_import_socket_raises_import_error(self):
        code = "import socket\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_exec_import_sys_raises_import_error(self):
        code = "import sys\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_exec_import_ctypes_raises_import_error(self):
        code = "import ctypes\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_exec_from_os_import_system_raises_import_error(self):
        code = "from os import system\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_exec_relative_import_raises_import_error(self):
        """Relative imports (level > 0) must also be blocked."""
        code = "from . import something\ndef on_tick(ctx, params):\n    pass\n"
        with pytest.raises((ImportError, SyntaxError)):
            exec_strategy(code)


# ===========================================================================
# 10. exec_strategy — missing on_tick
# ===========================================================================

class TestExecStrategyMissingOnTick:
    def test_exec_no_on_tick_raises_value_error(self):
        code = "x = 1 + 1\n"
        with pytest.raises(ValueError, match="on_tick"):
            exec_strategy(code)

    def test_exec_on_tick_is_not_callable_raises_value_error(self):
        """If on_tick is defined as a non-callable (e.g. variable), raise."""
        code = "on_tick = 42\n"
        with pytest.raises(ValueError, match="on_tick"):
            exec_strategy(code)


# ===========================================================================
# 11. build_safe_builtins — whitelist checks
# ===========================================================================

class TestBuildSafeBuiltins:
    def test_safe_builtins_has_math_ops(self):
        sb = build_safe_builtins()
        for name in ("abs", "min", "max", "len", "range", "sum", "round"):
            assert name in sb, f"Expected {name!r} in safe builtins"

    def test_safe_builtins_excludes_dangerous_builtins(self):
        sb = build_safe_builtins()
        for name in ("open", "eval", "exec", "compile", "__import__",
                     "globals", "locals", "vars", "input", "memoryview"):
            assert name not in sb, (
                f"Dangerous builtin {name!r} must NOT be in safe builtins"
            )

    def test_safe_builtins_excludes_getattr_family(self):
        sb = build_safe_builtins()
        for name in ("getattr", "setattr", "delattr", "hasattr"):
            assert name not in sb, (
                f"{name!r} must NOT be in safe builtins (dynamic attribute dispatch)"
            )

    def test_safe_builtins_has_type_constructors(self):
        sb = build_safe_builtins()
        for name in ("int", "float", "str", "list", "dict", "tuple", "set", "bool"):
            assert name in sb, f"Type constructor {name!r} should be in safe builtins"


# ===========================================================================
# 12. Escape-attempt payloads (adversarial)
# ===========================================================================

class TestEscapeAttempts:
    """Test that well-known CPython sandbox escape techniques are blocked.

    Each test represents a real-world sandbox escape pattern.  For each we
    assert that:
      - AST check catches it, OR
      - exec_strategy with restricted builtins prevents the dangerous action.

    A payload that slips through AST must not be able to reach os.system or
    subprocess.  We verify the escape *fails* (raises an exception).
    """

    def test_escape_via_subclasses(self):
        """Classic: ().__class__.__bases__[0].__subclasses__() to find subprocess."""
        code = """
def on_tick(ctx, params):
    classes = ().__class__.__bases__[0].__subclasses__()
    for cls in classes:
        if cls.__name__ == 'Popen':
            cls(['id'])
"""
        # AST must catch the __class__/__bases__/__subclasses__ attribute access.
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __class__/__bases__/__subclasses__"

    def test_escape_via_globals_to_builtins(self):
        """Access __globals__ to retrieve the real __builtins__."""
        code = """
def on_tick(ctx, params):
    real_builtins = on_tick.__globals__['__builtins__']
    evil_eval = real_builtins['eval'] if isinstance(real_builtins, dict) else real_builtins.eval
    evil_eval('import os; os.system("id")')
"""
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __globals__ access"

    def test_escape_via_builtins_attr(self):
        """Retrieve __builtins__ from a function's globals to get eval."""
        code = """
def on_tick(ctx, params):
    b = (lambda: None).__globals__['__builtins__']
"""
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __globals__ access on lambda"

    def test_escape_via_exec_in_builtins(self):
        """exec is in the __FORBIDDEN_CALLS__ and __DANGEROUS_NAMES__ lists."""
        code = """
def on_tick(ctx, params):
    exec("import os; os.system('id')")
"""
        r = check_ast(code)
        assert r["ok"] is False

    def test_escape_via_eval(self):
        code = 'def on_tick(ctx, params):\n    eval("__import__(\'os\').system(\'id\')")\n'
        r = check_ast(code)
        assert r["ok"] is False

    def test_escape_via_import_os_exec_time(self):
        """Even if AST check is skipped, exec_strategy's controlled __import__ blocks os."""
        code = "import os\ndef on_tick(ctx, params):\n    os.system('id')\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_escape_via_import_subprocess_exec_time(self):
        code = "import subprocess\ndef on_tick(ctx, params):\n    subprocess.run(['id'])\n"
        with pytest.raises(ImportError):
            exec_strategy(code)

    def test_exec_namespace_has_no_open(self):
        """In the exec namespace, open is not available."""
        code = """
def on_tick(ctx, params):
    return 'open' in dir(__builtins__) if isinstance(__builtins__, dict) else hasattr(__builtins__, 'open')
"""
        # AST catches __builtins__ attribute and hasattr call.
        r = check_ast(code)
        assert r["ok"] is False

    def test_exec_namespace_cannot_call_open(self):
        """Directly calling open in exec'd code is blocked by the safe namespace.

        The user code wraps open() in try/except, so the NameError is caught
        internally (result stays the error string, never 'OPENED').  AST should
        also catch this statically.
        """
        code = """
result = None
try:
    f = open('/etc/passwd', 'r')
    result = 'OPENED'
except Exception as e:
    result = str(e)

def on_tick(ctx, params):
    return result
"""
        # AST catches the open() call.
        r = check_ast(code)
        assert r["ok"] is False, "AST should catch open() call"
        # Exec-time: open is not in safe builtins → NameError is raised inside
        # the user's try/except, so exec itself completes but result != 'OPENED'.
        from core.strategy.safe_exec import build_safe_builtins, _make_controlled_import, ALLOWED_MODULES
        safe_b = build_safe_builtins()
        safe_b["__import__"] = _make_controlled_import(ALLOWED_MODULES)
        ns = {"__builtins__": safe_b}
        exec(code, ns)  # noqa: S102  — intentional test of restricted namespace
        assert ns.get("result") != "OPENED", (
            "open() must not succeed in a safe exec namespace"
        )

    def test_exec_namespace_cannot_access_real_builtins_via_dict(self):
        """User code cannot retrieve real builtins via __builtins__ dict access."""
        code = """
def on_tick(ctx, params):
    pass

# Module-level attempt to grab real builtins
try:
    b = globals()['__builtins__']
    real_eval = b.get('eval') if isinstance(b, dict) else getattr(b, 'eval', None)
except Exception:
    real_eval = None
"""
        # globals() is in _FORBIDDEN_CALLS; AST should block.
        r = check_ast(code)
        assert r["ok"] is False

    def test_exec_eval_not_in_safe_builtins(self):
        """Verify at exec time that eval is not reachable in the safe namespace."""
        code = """
try:
    result = eval('1+1')
except NameError:
    result = 'blocked'
def on_tick(ctx, params):
    return result
"""
        # exec_strategy runs with safe builtins: eval is absent → NameError →
        # caught by except NameError → result = 'blocked' → on_tick callable.
        fn = exec_strategy(code)
        assert callable(fn)
        # Verify the result variable was set to 'blocked' (not a computed value).
        from core.strategy.safe_exec import build_safe_builtins, _make_controlled_import, ALLOWED_MODULES
        safe_b = build_safe_builtins()
        safe_b["__import__"] = _make_controlled_import(ALLOWED_MODULES)
        ns2 = {"__builtins__": safe_b}
        exec(code, ns2)  # noqa: S102
        assert ns2.get("result") == "blocked", (
            "eval should not be available in safe exec namespace"
        )

    def test_escape_via_mro(self):
        """Access to __mro__ could lead to finding subclasses."""
        code = "def on_tick(ctx, params):\n    x = int.__mro__\n"
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __mro__ access"

    def test_escape_via_code_object(self):
        """Access to __code__ can be used to craft malicious bytecode."""
        code = "def on_tick(ctx, params):\n    c = on_tick.__code__\n"
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __code__ access"

    def test_escape_via_closure(self):
        """Access to __closure__ can leak references to outer scopes."""
        code = "def on_tick(ctx, params):\n    c = on_tick.__closure__\n"
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __closure__ access"

    def test_escape_via_reduce(self):
        """__reduce__ / __reduce_ex__ can be used with pickle for code exec."""
        code = "def on_tick(ctx, params):\n    ctx.__reduce__()\n"
        r = check_ast(code)
        assert r["ok"] is False, "AST should block __reduce__ access"


# ===========================================================================
# 13. Frame / traceback RCE regression tests (Critical fix)
# ===========================================================================

class TestFrameTracebackEscapes:
    """Regression tests for the frame/traceback RCE escape chain.

    The attack vector:
        try: raise ValueError()
        except ValueError as e:
            e.__traceback__.tb_frame.f_back.f_builtins["__import__"]("os").system(...)

    This works because:
      1. e.__traceback__ gives the traceback object.
      2. .tb_frame gives the frame where the exception was raised.
      3. .f_back walks up the call stack.
      4. .f_builtins gives the real __builtins__ dict of that frame.
      5. ["__import__"] retrieves the unguarded built-in __import__.
      6. ("os") imports os, .system("id") achieves RCE.

    Fix: AST now blocks ALL dunder attributes (startswith "__") PLUS explicit
    frame/traceback attribute names (tb_frame, f_back, f_builtins, etc.).
    """

    # ---- The exact reviewer RCE payload ------------------------------------

    def test_reviewer_rce_payload_blocked(self):
        """Exact payload from security review — must be blocked by check_ast."""
        code = """
def on_tick(ctx, params):
    try:
        raise ValueError()
    except ValueError as e:
        e.__traceback__.tb_frame.f_back.f_builtins["__import__"]("os").system("id")
"""
        r = check_ast(code)
        assert r["ok"] is False, (
            "CRITICAL: frame RCE payload must be blocked by AST check"
        )
        # Must catch at least the __traceback__ dunder or tb_frame/f_back/f_builtins
        rules = {v["rule"] for v in r["violations"]}
        assert "forbidden_attr" in rules

    # ---- __traceback__ dunder is caught by all-dunder rule -----------------

    def test_traceback_dunder_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = err.__traceback__\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert any(v["rule"] == "forbidden_attr" for v in r["violations"])

    # ---- frame attribute names caught by _FORBIDDEN_FRAME_ATTRS ------------

    def test_tb_frame_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = tb.tb_frame\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert any(v["rule"] == "forbidden_attr" for v in r["violations"])

    def test_tb_next_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = tb.tb_next\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_f_back_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = frame.f_back\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert any(v["rule"] == "forbidden_attr" for v in r["violations"])

    def test_f_globals_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = frame.f_globals\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_f_builtins_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = frame.f_builtins\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_f_locals_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = frame.f_locals\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_f_code_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = frame.f_code\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_gi_frame_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = gen.gi_frame\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_cr_frame_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = coro.cr_frame\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_ag_frame_attr_blocked(self):
        code = "def on_tick(ctx, params):\n    x = agen.ag_frame\n"
        r = check_ast(code)
        assert r["ok"] is False

    # ---- All-dunder rule catches previously-unlisted dunders ---------------

    def test_getattribute_dunder_blocked(self):
        """__getattribute__ can bypass attribute-level restrictions."""
        code = "def on_tick(ctx, params):\n    x = ctx.__getattribute__('secret')\n"
        r = check_ast(code)
        assert r["ok"] is False
        assert any(v["rule"] == "forbidden_attr" for v in r["violations"])

    def test_getattr_dunder_blocked(self):
        """__getattr__ hook access blocked."""
        code = "def on_tick(ctx, params):\n    x = ctx.__getattr__\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_new_dunder_blocked(self):
        """__new__ used for instance creation bypass."""
        code = "def on_tick(ctx, params):\n    x = object.__new__(object)\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_init_dunder_blocked(self):
        code = "def on_tick(ctx, params):\n    x = ctx.__init__()\n"
        r = check_ast(code)
        assert r["ok"] is False

    def test_arbitrary_unknown_dunder_blocked(self):
        """Any future/unknown dunder must also be blocked."""
        code = "def on_tick(ctx, params):\n    x = ctx.__future_escape_vector__\n"
        r = check_ast(code)
        assert r["ok"] is False

    # ---- Multi-step chain is caught at first dunder ------------------------

    def test_full_rce_chain_blocked_at_traceback_step(self):
        """The chain e.__traceback__.tb_frame.f_back.f_builtins is blocked."""
        code = """
def on_tick(ctx, params):
    try:
        1/0
    except ZeroDivisionError as e:
        tb = e.__traceback__
        frame = tb.tb_frame
        builtins_dict = frame.f_builtins
        import_fn = builtins_dict["__import__"]
        import_fn("os").system("id")
"""
        r = check_ast(code)
        assert r["ok"] is False
        # Multiple violations: __traceback__ (dunder), tb_frame, f_builtins, __import__ key
        assert len(r["violations"]) >= 1

    def test_alternate_traceback_access_via_sys_exc_info_blocked(self):
        """import sys → blocked at import level (sys not in whitelist)."""
        code = """
import sys
def on_tick(ctx, params):
    exc_type, exc_val, tb = sys.exc_info()
    tb.tb_frame.f_builtins["__import__"]("os")
"""
        r = check_ast(code)
        assert r["ok"] is False
        assert any(v["rule"] == "forbidden_import" for v in r["violations"])

