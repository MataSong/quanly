"""strategy-runner/runner.py

Polls the backend for candles and calls on_tick() for the loaded strategy.
Communicates exclusively via RUN_TOKEN — no credential keys in this container.

Environment variables (all required except POLL_INTERVAL):
  RUN_TOKEN     — one-shot token for X-Run-Token header
  BACKEND_URL   — e.g. http://backend:8000
  CODE_REF      — strategy identifier, e.g. "dual_ma"
  SYMBOL        — trading pair, e.g. "BTC-USDT"
  PARAMS        — JSON string of strategy parameters
  POLL_INTERVAL — seconds between ticks (default: 5)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
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

# How many consecutive errors before we give up and exit.
MAX_CONSECUTIVE_ERRORS = 5

# ---------------------------------------------------------------------------
# Validate required env vars immediately
# ---------------------------------------------------------------------------
_missing = [k for k, v in [
    ("RUN_TOKEN", RUN_TOKEN),
    ("BACKEND_URL", BACKEND_URL),
    ("CODE_REF", CODE_REF),
    ("SYMBOL", SYMBOL),
] if not v]
if _missing:
    log.error("Missing required environment variables: %s", ", ".join(_missing))
    sys.exit(1)

try:
    PARAMS: dict[str, Any] = json.loads(PARAMS_RAW)
except json.JSONDecodeError as e:
    log.error("PARAMS is not valid JSON: %s — raw=%r", e, PARAMS_RAW)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown = False


def _handle_sigterm(signum, frame):  # noqa: ANN001
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


# ---------------------------------------------------------------------------
# Runner Context
# ---------------------------------------------------------------------------

class RunnerCtx:
    """Duck-typed context object passed to on_tick(ctx, params).

    All methods communicate with the backend via X-Run-Token authentication.
    Network errors are retried with exponential backoff.
    A 401 response causes an immediate exit (token revoked / expired).
    """

    def __init__(self, token: str, backend_url: str, symbol: str) -> None:
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
            except requests.RequestException as exc:
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
            except requests.RequestException as exc:
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
            "/api/strategy/runner/candles",
            params={"bar": bar, "limit": limit},
        )
        # Backend returns {"candles": [...]}
        return data.get("candles", [])

    def buy(self, sz: str, ord_type: str = "market", px: str | None = None) -> str:
        """Place a buy order, returns ordId."""
        body: dict[str, Any] = {"side": "buy", "sz": sz, "ord_type": ord_type}
        if px is not None:
            body["px"] = px
        data = self._post("/api/strategy/runner/order", body)
        return data.get("ordId", "")

    def sell(self, sz: str, ord_type: str = "market", px: str | None = None) -> str:
        """Place a sell order, returns ordId."""
        body: dict[str, Any] = {"side": "sell", "sz": sz, "ord_type": ord_type}
        if px is not None:
            body["px"] = px
        data = self._post("/api/strategy/runner/order", body)
        return data.get("ordId", "")

    def log(self, level: str, message: str) -> None:
        """Post a log entry to the backend. Best-effort: won't raise."""
        try:
            # Log locally too so Docker logs capture it even if backend is down.
            log.info("[%s] %s", level.upper(), message)
            self._post("/api/strategy/runner/log", {"level": level, "message": message})
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
# Strategy loader
# ---------------------------------------------------------------------------

def load_on_tick(code_ref: str):
    """Load on_tick function for the given code_ref.

    Currently supports built-in strategies only.
    Raises ImportError / AttributeError for unknown code_ref.
    """
    if code_ref == "dual_ma":
        from builtin.dual_ma import on_tick
        return on_tick
    raise ValueError(f"Unknown CODE_REF: {code_ref!r}. Supported: dual_ma")


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("runner starting: code_ref=%s symbol=%s poll_interval=%ss", CODE_REF, SYMBOL, POLL_INTERVAL)

    # Load strategy
    try:
        on_tick = load_on_tick(CODE_REF)
    except (ValueError, ImportError, AttributeError) as exc:
        log.error("Failed to load strategy %r: %s", CODE_REF, exc)
        sys.exit(1)

    ctx = RunnerCtx(token=RUN_TOKEN, backend_url=BACKEND_URL, symbol=SYMBOL)

    ctx.log("info", f"strategy started: code_ref={CODE_REF} symbol={SYMBOL} poll_interval={POLL_INTERVAL}s")

    consecutive_errors = 0

    while not _shutdown:
        tick_start = time.monotonic()
        try:
            on_tick(ctx, PARAMS)
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

    ctx.log("info", f"strategy stopped: code_ref={CODE_REF} symbol={SYMBOL}")
    log.info("runner exiting cleanly")


if __name__ == "__main__":
    main()
