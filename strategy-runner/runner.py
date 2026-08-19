"""strategy-runner/runner.py

Polls the backend for candles and calls on_tick() for the loaded strategy.
Communicates exclusively via RUN_TOKEN — no credential keys in this container.

Two run modes:
  1. Live/poll mode (default): connects to backend via RUN_TOKEN, polls candles,
     places orders. Requires RUN_TOKEN/BACKEND_URL/CODE_REF/SYMBOL.
  2. Trial mode (TRIAL_MODE=1): fully offline one-shot dry run against synthetic
     candles. No network, no backend, no RUN_TOKEN. Used by backend T3 to check a
     user strategy inside an isolated container. Emits a JSON result to stdout.

Strategy source:
  - USER_CODE env (non-empty): user-supplied Python source, on_tick extracted via a
    *controlled* exec (restricted __builtins__ + import whitelist). See load_on_tick.
  - Otherwise CODE_REF selects a built-in strategy (currently dual_ma).

SECURITY NOTE — the controlled exec here is a NOISE-REDUCTION layer, NOT a security
boundary. The real isolation is the container the backend launches this in
(cap_drop=ALL, read_only rootfs, network isolation, non-root, pids_limit — done in
backend tasks / T7). Do NOT rely on the restricted __builtins__ to stop hostile code.

Environment variables:
  Live/poll mode (all required except POLL_INTERVAL):
    RUN_TOKEN     — one-shot token for X-Run-Token header
    BACKEND_URL   — e.g. http://backend:8000
    CODE_REF      — strategy identifier, e.g. "dual_ma"
    SYMBOL        — trading pair, e.g. "BTC-USDT"
    PARAMS        — JSON string of strategy parameters
    POLL_INTERVAL — seconds between ticks (default: 5)
    USER_CODE     — (optional) user Python source; overrides CODE_REF when non-empty
  Trial mode:
    TRIAL_MODE    — "1" to enable one-shot offline trial
    TRIAL_CANDLES — JSON list of candles [{ts,o,h,l,c,vol,volCcy}, ...] oldest-first
    USER_CODE     — user Python source to trial (or CODE_REF for a built-in)
    PARAMS        — JSON string of strategy parameters
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from typing import Any

# NOTE: `requests` is imported lazily (inside RunnerCtx) so that trial mode and the
# offline tests run with zero third-party dependencies. The container image ships
# `requests` for the live/poll path.

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("runner")

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
RUN_TOKEN = os.environ.get("RUN_TOKEN", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
CODE_REF = os.environ.get("CODE_REF", "")
SYMBOL = os.environ.get("SYMBOL", "")
PARAMS_RAW = os.environ.get("PARAMS", "{}")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
USER_CODE = os.environ.get("USER_CODE", "")

TRIAL_MODE = os.environ.get("TRIAL_MODE", "") == "1"
TRIAL_CANDLES_RAW = os.environ.get("TRIAL_CANDLES", "[]")

# How many consecutive errors before we give up and exit.
MAX_CONSECUTIVE_ERRORS = 5

# How many ticks to run in trial mode (one on_tick per synthetic bar, capped).
TRIAL_MAX_TICKS = int(os.environ.get("TRIAL_MAX_TICKS", "200"))


def _parse_params() -> dict[str, Any]:
    try:
        return json.loads(PARAMS_RAW)
    except json.JSONDecodeError as e:
        log.error("PARAMS is not valid JSON: %s — raw=%r", e, PARAMS_RAW)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Graceful shutdown (live/poll mode only)
# ---------------------------------------------------------------------------
_shutdown = False


def _handle_sigterm(signum, frame):  # noqa: ANN001
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


# ---------------------------------------------------------------------------
# Controlled exec of user code
#
# SECURITY NOTE: this is a NOISE-REDUCTION layer, not a security boundary. It limits
# the __builtins__ visible to user code and whitelists importable top-level packages
# so accidental / careless code fails loudly rather than silently reaching the OS.
# It does NOT stop a determined attacker — the container isolation (cap_drop /
# read_only / network isolation / non-root / pids_limit, applied by the backend when
# it launches this container in T7) is the real boundary. Implemented standalone here
# so the runner has zero backend dependency.
# ---------------------------------------------------------------------------

# Top-level packages user code is allowed to import (pure compute + data libs).
_ALLOWED_IMPORTS = frozenset({
    "math", "statistics", "json", "datetime", "decimal", "numpy", "pandas",
})

# Names to expose in the restricted __builtins__ (pure computation only).
_SAFE_BUILTIN_NAMES = (
    "abs", "min", "max", "len", "range", "sum", "round", "sorted", "reversed",
    "enumerate", "zip", "map", "filter", "float", "int", "str", "list", "dict",
    "tuple", "set", "bool", "isinstance", "print", "divmod", "pow", "all", "any",
    # exceptions user code may legitimately raise / catch
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "ZeroDivisionError", "ArithmeticError", "RuntimeError", "StopIteration",
    "True", "False", "None",
)


def _make_safe_builtins() -> dict[str, Any]:
    """Build a restricted __builtins__ mapping for user code.

    Explicitly EXCLUDED (never exposed): open, eval, exec, compile, __import__ (the
    raw one), globals, locals, vars, input, getattr, setattr, delattr, and everything
    else not in the whitelist above. A controlled __import__ (below) is substituted so
    only whitelisted top-level packages can be imported.
    """
    import builtins as _b

    safe: dict[str, Any] = {}
    for name in _SAFE_BUILTIN_NAMES:
        if hasattr(_b, name):
            safe[name] = getattr(_b, name)

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        # Only allow absolute imports of whitelisted top-level packages.
        top = name.split(".")[0]
        if level != 0 or top not in _ALLOWED_IMPORTS:
            raise ImportError(
                f"import of {name!r} is not allowed in user strategy code "
                f"(allowed: {sorted(_ALLOWED_IMPORTS)})"
            )
        return __import__(name, globals, locals, fromlist, level)

    safe["__import__"] = _safe_import
    return safe


def _load_on_tick_from_user_code(code: str):
    """Controlled-exec the user's source and return its on_tick callable.

    Raises RuntimeError / SyntaxError / ImportError on any failure — the caller logs
    and exits. This is a noise-reduction layer, not a security boundary (see above).
    """
    safe_builtins = _make_safe_builtins()
    ns: dict[str, Any] = {"__builtins__": safe_builtins}
    # exec compiles + runs in one shot; import statements route through _safe_import.
    exec(code, ns)  # noqa: S102 — intentional controlled exec; boundary is the container
    on_tick = ns.get("on_tick")
    if not callable(on_tick):
        raise RuntimeError("user code does not define a callable on_tick(ctx, params)")
    return on_tick


# ---------------------------------------------------------------------------
# Strategy loader
# ---------------------------------------------------------------------------

def load_on_tick(code_ref: str, user_code: str = ""):
    """Load the on_tick function.

    If user_code is non-empty → controlled-exec it (noise-reduction layer; real
    boundary is the container). Otherwise select a built-in by code_ref.

    Raises ValueError / ImportError / AttributeError / SyntaxError / RuntimeError.
    """
    if user_code:
        return _load_on_tick_from_user_code(user_code)
    if code_ref == "dual_ma":
        from builtin.dual_ma import on_tick
        return on_tick
    raise ValueError(f"Unknown CODE_REF: {code_ref!r}. Supported: dual_ma")


# ---------------------------------------------------------------------------
# Runner Context (live/poll mode) — talks to backend via X-Run-Token
# ---------------------------------------------------------------------------

class RunnerCtx:
    """Duck-typed context object passed to on_tick(ctx, params).

    All methods communicate with the backend via X-Run-Token authentication.
    Network errors are retried with exponential backoff.
    A 401 response causes an immediate exit (token revoked / expired).
    """

    def __init__(self, token: str, backend_url: str, symbol: str) -> None:
        import requests  # lazy: only the live/poll path needs it

        self._requests = requests
        self._token = token
        self._backend_url = backend_url
        self._symbol = symbol
        self._session = requests.Session()
        self._session.headers.update({"X-Run-Token": token})

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None, retries: int = 3) -> Any:
        url = f"{self._backend_url}{path}"
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._session.get(url, params=params, timeout=15)
                if resp.status_code == 401:
                    self.log("error", f"runner: RUN_TOKEN rejected by backend (401) on GET {path}, exiting")
                    sys.exit(1)
                resp.raise_for_status()
                return resp.json()
            except self._requests.RequestException as exc:
                last_exc = exc
                log.warning("GET %s attempt %d/%d failed: %s", path, attempt + 1, retries, exc)
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
        raise RuntimeError(f"GET {path} failed after {retries} attempts: {last_exc}")

    def _post(self, path: str, body: dict, retries: int = 3) -> Any:
        url = f"{self._backend_url}{path}"
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._session.post(url, json=body, timeout=15)
                if resp.status_code == 401:
                    self.log("error", f"runner: RUN_TOKEN rejected by backend (401) on POST {path}, exiting")
                    sys.exit(1)
                resp.raise_for_status()
                return resp.json()
            except self._requests.RequestException as exc:
                last_exc = exc
                log.warning("POST %s attempt %d/%d failed: %s", path, attempt + 1, retries, exc)
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
        raise RuntimeError(f"POST {path} failed after {retries} attempts: {last_exc}")

    # ------------------------------------------------------------------
    # Public ctx API (matches dual_ma.py interface contract)
    # ------------------------------------------------------------------

    def candles(self, bar: str = "1m", limit: int = 100) -> list[dict]:
        """Fetch candles oldest-first: [{ts, o, h, l, c, vol, volCcy}, ...]"""
        data = self._get(
            "/api/strategy/runner/v1/candles",
            params={"bar": bar, "limit": limit},
        )
        # Backend returns {"candles": [...]}
        return data.get("candles", [])

    def buy(self, sz: str, ord_type: str = "market", px: str | None = None) -> str:
        """Place a buy order, returns ordId."""
        body: dict[str, Any] = {"side": "buy", "sz": sz, "ord_type": ord_type}
        if px is not None:
            body["px"] = px
        data = self._post("/api/strategy/runner/v1/order", body)
        return data.get("ordId", "")

    def sell(self, sz: str, ord_type: str = "market", px: str | None = None) -> str:
        """Place a sell order, returns ordId."""
        body: dict[str, Any] = {"side": "sell", "sz": sz, "ord_type": ord_type}
        if px is not None:
            body["px"] = px
        data = self._post("/api/strategy/runner/v1/order", body)
        return data.get("ordId", "")

    def log(self, level: str, message: str) -> None:
        """Post a log entry to the backend. Best-effort: won't raise."""
        try:
            # Log locally too so Docker logs capture it even if backend is down.
            log.info("[%s] %s", level.upper(), message)
            self._post("/api/strategy/runner/v1/log", {"level": level, "message": message})
        except Exception as exc:
            log.warning("log POST failed (continuing): %s", exc)

    def price(self) -> float | None:
        """Return latest close price from candles, or None if unavailable."""
        try:
            candles = self.candles(limit=1)
            if candles:
                return float(candles[-1]["c"])
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Trial Context (trial mode) — fully offline, in-memory, no network
# ---------------------------------------------------------------------------

class TrialCtx:
    """In-memory ctx for one-shot offline trial runs.

    - candles() returns TRIAL_CANDLES up to the current cursor (inclusive).
    - buy()/sell() only tally signal counts; no orders are placed.
    - log() prints (best-effort) to stderr.
    - price() returns the latest visible close.

    No network, no backend, no RUN_TOKEN. Cursor is advanced by the trial loop.
    """

    def __init__(self, all_candles: list[dict]) -> None:
        self._all = all_candles
        self._cursor = 0  # number of bars visible so far
        self.signal_count = 0

    def _advance(self, n: int) -> None:
        self._cursor = n

    def candles(self, bar: str = "1m", limit: int = 100) -> list[dict]:
        visible = self._all[: self._cursor]
        if limit and limit < len(visible):
            return visible[-limit:]
        return visible

    def buy(self, sz: str, ord_type: str = "market", px: str | None = None) -> str:
        self.signal_count += 1
        return f"trial-buy-{self.signal_count}"

    def sell(self, sz: str, ord_type: str = "market", px: str | None = None) -> str:
        self.signal_count += 1
        return f"trial-sell-{self.signal_count}"

    def log(self, level: str, message: str) -> None:
        try:
            log.info("[trial:%s] %s", level.upper(), message)
        except Exception:
            pass

    def price(self) -> float | None:
        visible = self.candles(limit=1)
        if visible:
            try:
                return float(visible[-1]["c"])
            except (KeyError, ValueError, TypeError):
                return None
        return None


def _emit_trial_result(result: dict[str, Any]) -> None:
    """Write the trial result as a single-line JSON object to stdout."""
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


def run_trial() -> int:
    """Execute a one-shot offline trial. Returns process exit code.

    Emits to stdout exactly one JSON object:
      {"ok": true, "signal_count": N}
      {"ok": false, "error": "...", "tick": i}   (tick omitted for load errors)
    """
    params = _parse_params()

    # Parse synthetic candles.
    try:
        all_candles = json.loads(TRIAL_CANDLES_RAW)
        if not isinstance(all_candles, list):
            raise ValueError("TRIAL_CANDLES must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        _emit_trial_result({"ok": False, "error": f"invalid TRIAL_CANDLES: {exc}"})
        return 0

    # Load strategy (user code via controlled exec, or built-in).
    try:
        on_tick = load_on_tick(CODE_REF, USER_CODE)
    except Exception as exc:  # noqa: BLE001 — surface any load failure as ok:false
        _emit_trial_result({"ok": False, "error": f"load on_tick failed: {exc}"})
        return 0

    ctx = TrialCtx(all_candles)

    # Feed bars one at a time (cursor grows), running on_tick each step, capped.
    total_bars = len(all_candles)
    max_ticks = min(total_bars, TRIAL_MAX_TICKS) if total_bars else 0
    for i in range(1, max_ticks + 1):
        ctx._advance(i)
        try:
            on_tick(ctx, params)
        except Exception as exc:  # noqa: BLE001 — report the failing tick
            _emit_trial_result({"ok": False, "error": str(exc), "tick": i})
            return 0

    _emit_trial_result({"ok": True, "signal_count": ctx.signal_count})
    return 0


# ---------------------------------------------------------------------------
# Main polling loop (live mode)
# ---------------------------------------------------------------------------

def run_live() -> None:
    # Validate required env vars for live/poll mode.
    _missing = [k for k, v in [
        ("RUN_TOKEN", RUN_TOKEN),
        ("BACKEND_URL", BACKEND_URL),
        ("SYMBOL", SYMBOL),
    ] if not v]
    # CODE_REF is only required when there's no USER_CODE.
    if not USER_CODE and not CODE_REF:
        _missing.append("CODE_REF")
    if _missing:
        log.error("Missing required environment variables: %s", ", ".join(_missing))
        sys.exit(1)

    params = _parse_params()

    src = "user_code" if USER_CODE else f"code_ref={CODE_REF}"
    log.info("runner starting: %s symbol=%s poll_interval=%ss", src, SYMBOL, POLL_INTERVAL)

    # Load strategy
    try:
        on_tick = load_on_tick(CODE_REF, USER_CODE)
    except Exception as exc:  # noqa: BLE001 — any load failure is fatal
        log.error("Failed to load strategy (%s): %s", src, exc)
        sys.exit(1)

    ctx = RunnerCtx(token=RUN_TOKEN, backend_url=BACKEND_URL, symbol=SYMBOL)

    ctx.log("info", f"strategy started: {src} symbol={SYMBOL} poll_interval={POLL_INTERVAL}s")

    consecutive_errors = 0

    while not _shutdown:
        tick_start = time.monotonic()
        try:
            on_tick(ctx, params)
            consecutive_errors = 0  # reset on success
        except SystemExit:
            # Propagate intentional exits (e.g. 401 token revoked).
            raise
        except Exception as exc:
            consecutive_errors += 1
            log.error("on_tick error (%d/%d): %s", consecutive_errors, MAX_CONSECUTIVE_ERRORS, exc)
            ctx.log("error", f"on_tick error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {exc}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                ctx.log("error", f"too many consecutive errors ({MAX_CONSECUTIVE_ERRORS}), exiting")
                sys.exit(1)

        if _shutdown:
            break

        # Sleep for remainder of poll interval
        elapsed = time.monotonic() - tick_start
        sleep_for = max(0.0, POLL_INTERVAL - elapsed)
        # Wake up in small chunks so SIGTERM is caught promptly
        deadline = time.monotonic() + sleep_for
        while time.monotonic() < deadline and not _shutdown:
            time.sleep(min(0.5, deadline - time.monotonic()))

    ctx.log("info", f"strategy stopped: {src} symbol={SYMBOL}")
    log.info("runner exiting cleanly")


def main() -> None:
    if TRIAL_MODE:
        # One-shot offline trial: no network, no backend, no RUN_TOKEN.
        sys.exit(run_trial())
    run_live()


if __name__ == "__main__":
    main()
