"""Offline tests for strategy-runner/runner.py.

Mocks `requests.Session` to verify:
  - ctx.candles() sends GET with correct path and X-Run-Token header
  - ctx.buy() / ctx.sell() send POST with correct body
  - ctx.log() sends POST with level+message
  - 401 response causes sys.exit(1)
  - consecutive errors trigger exit after MAX_CONSECUTIVE_ERRORS
"""
from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helper: build a mock response
# ---------------------------------------------------------------------------

def _mock_resp(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# We load runner with env vars patched at import time
# ---------------------------------------------------------------------------

BASE_ENV = {
    "RUN_TOKEN": "tok-test",
    "BACKEND_URL": "http://backend:8000",
    "CODE_REF": "dual_ma",
    "SYMBOL": "BTC-USDT",
    "PARAMS": "{}",
    "POLL_INTERVAL": "5",
}


def _load_runner():
    """Import (or reload) runner with BASE_ENV in os.environ."""
    with patch.dict("os.environ", BASE_ENV, clear=False):
        # Remove cached module so env is re-read
        if "runner" in sys.modules:
            del sys.modules["runner"]
        import runner as r
        return r


class TestRunnerCtx(unittest.TestCase):

    def setUp(self):
        self.runner = _load_runner()
        self.ctx = self.runner.RunnerCtx(
            token="tok-test",
            backend_url="http://backend:8000",
            symbol="BTC-USDT",
        )

    # ------------------------------------------------------------------
    # candles()
    # ------------------------------------------------------------------

    def test_candles_get_correct_path_and_header(self):
        candle_data = [{"ts": 1, "o": 1, "h": 1, "l": 1, "c": 50000, "vol": 1, "volCcy": 1}]
        mock_resp = _mock_resp(200, {"candles": candle_data})

        with patch.object(self.ctx._session, "get", return_value=mock_resp) as mock_get:
            result = self.ctx.candles(bar="1m", limit=50)

        mock_get.assert_called_once_with(
            "http://backend:8000/api/strategy/runner/v1/candles",
            params={"bar": "1m", "limit": 50},
            timeout=15,
        )
        # X-Run-Token is set on the session headers, not per-call params
        self.assertEqual(self.ctx._session.headers["X-Run-Token"], "tok-test")
        self.assertEqual(result, candle_data)

    def test_candles_returns_empty_list_on_missing_key(self):
        mock_resp = _mock_resp(200, {})
        with patch.object(self.ctx._session, "get", return_value=mock_resp):
            result = self.ctx.candles()
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # buy()
    # ------------------------------------------------------------------

    def test_buy_posts_correct_body(self):
        mock_resp = _mock_resp(200, {"ordId": "ord-123"})
        with patch.object(self.ctx._session, "post", return_value=mock_resp) as mock_post:
            ord_id = self.ctx.buy("0.001")

        mock_post.assert_called_once_with(
            "http://backend:8000/api/strategy/runner/v1/order",
            json={"side": "buy", "sz": "0.001", "ord_type": "market"},
            timeout=15,
        )
        self.assertEqual(ord_id, "ord-123")

    def test_buy_includes_px_when_provided(self):
        mock_resp = _mock_resp(200, {"ordId": "ord-456"})
        with patch.object(self.ctx._session, "post", return_value=mock_resp) as mock_post:
            self.ctx.buy("0.001", ord_type="limit", px="50000")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["px"], "50000")
        self.assertEqual(kwargs["json"]["ord_type"], "limit")

    # ------------------------------------------------------------------
    # sell()
    # ------------------------------------------------------------------

    def test_sell_posts_correct_body(self):
        mock_resp = _mock_resp(200, {"ordId": "ord-789"})
        with patch.object(self.ctx._session, "post", return_value=mock_resp) as mock_post:
            ord_id = self.ctx.sell("0.002")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["side"], "sell")
        self.assertEqual(kwargs["json"]["sz"], "0.002")
        self.assertEqual(ord_id, "ord-789")

    # ------------------------------------------------------------------
    # log()
    # ------------------------------------------------------------------

    def test_log_posts_level_and_message(self):
        mock_resp = _mock_resp(201, {"id": 1})
        with patch.object(self.ctx._session, "post", return_value=mock_resp) as mock_post:
            self.ctx.log("info", "hello world")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["level"], "info")
        self.assertEqual(kwargs["json"]["message"], "hello world")

    def test_log_does_not_raise_on_network_error(self):
        """log() must be best-effort — never propagate exceptions."""
        from requests.exceptions import ConnectionError as ReqConnErr
        with patch.object(self.ctx._session, "post", side_effect=ReqConnErr("down")):
            # Should not raise
            self.ctx.log("error", "backend is down")

    # ------------------------------------------------------------------
    # 401 causes sys.exit(1)
    # ------------------------------------------------------------------

    def test_candles_401_causes_exit(self):
        mock_resp = _mock_resp(401, {"detail": "invalid token"})
        mock_resp.raise_for_status.return_value = None  # don't raise HTTPError on 401
        with patch.object(self.ctx._session, "get", return_value=mock_resp):
            with self.assertRaises(SystemExit) as cm:
                self.ctx.candles()
        self.assertEqual(cm.exception.code, 1)

    def test_order_401_causes_exit(self):
        mock_resp = _mock_resp(401, {"detail": "invalid token"})
        mock_resp.raise_for_status.return_value = None
        with patch.object(self.ctx._session, "post", return_value=mock_resp):
            with self.assertRaises(SystemExit) as cm:
                self.ctx.buy("0.001")
        self.assertEqual(cm.exception.code, 1)

    # ------------------------------------------------------------------
    # price()
    # ------------------------------------------------------------------

    def test_price_returns_latest_close(self):
        candle = {"ts": 1, "o": 1, "h": 1, "l": 1, "c": "49999.5", "vol": 1, "volCcy": 1}
        mock_resp = _mock_resp(200, {"candles": [candle]})
        with patch.object(self.ctx._session, "get", return_value=mock_resp):
            p = self.ctx.price()
        self.assertAlmostEqual(p, 49999.5)


class TestStrategyLoader(unittest.TestCase):

    def test_load_dual_ma(self):
        runner = _load_runner()
        on_tick = runner.load_on_tick("dual_ma")
        self.assertTrue(callable(on_tick))

    def test_unknown_code_ref_raises_value_error(self):
        runner = _load_runner()
        with self.assertRaises(ValueError):
            runner.load_on_tick("unknown_strategy")


class TestDualMaIntegration(unittest.TestCase):
    """Run dual_ma.on_tick() against a mock ctx to verify signal→order path."""

    def _make_ctx(self):
        ctx = MagicMock()
        ctx.log = MagicMock()
        ctx.buy = MagicMock(return_value="ord-buy-1")
        ctx.sell = MagicMock(return_value="ord-sell-1")
        return ctx

    def _make_candles(self, closes: list[float]) -> list[dict]:
        return [{"ts": i, "o": c, "h": c, "l": c, "c": c, "vol": 1, "volCcy": 1}
                for i, c in enumerate(closes)]

    def test_golden_cross_triggers_buy(self):
        from builtin.dual_ma import on_tick

        # Build prices where fast MA (5) crosses above slow MA (20):
        # 21 flat prices then a spike on the last bar to force crossover.
        closes = [100.0] * 21
        closes[-1] = 200.0   # spike causes fast MA >> slow MA
        ctx = self._make_ctx()
        ctx.candles.return_value = self._make_candles(closes)
        on_tick(ctx, {"fast_period": 5, "slow_period": 20, "sz": "0.001"})
        ctx.buy.assert_called_once_with("0.001")

    def test_no_signal_does_not_place_order(self):
        from builtin.dual_ma import on_tick

        closes = [100.0] * 25   # flat — no crossover
        ctx = self._make_ctx()
        ctx.candles.return_value = self._make_candles(closes)
        on_tick(ctx, {"fast_period": 5, "slow_period": 20, "sz": "0.001"})
        ctx.buy.assert_not_called()
        ctx.sell.assert_not_called()

    def test_insufficient_data_does_not_place_order(self):
        from builtin.dual_ma import on_tick

        closes = [100.0] * 5   # too few bars
        ctx = self._make_ctx()
        ctx.candles.return_value = self._make_candles(closes)
        on_tick(ctx, {"fast_period": 5, "slow_period": 20, "sz": "0.001"})
        ctx.buy.assert_not_called()
        ctx.sell.assert_not_called()


class TestControlledExec(unittest.TestCase):
    """UC-T6: controlled-exec of user code (noise-reduction layer, not a boundary)."""

    def test_extracts_valid_on_tick(self):
        runner = _load_runner()
        code = (
            "def on_tick(ctx, params):\n"
            "    ctx.log('info', 'hi')\n"
        )
        fn = runner.load_on_tick("", code)
        self.assertTrue(callable(fn))

    def test_user_code_can_import_whitelisted(self):
        runner = _load_runner()
        code = (
            "import math\n"
            "import statistics\n"
            "def on_tick(ctx, params):\n"
            "    return math.sqrt(4) + statistics.mean([1, 2, 3])\n"
        )
        fn = runner.load_on_tick("", code)
        self.assertTrue(callable(fn))

    def test_import_os_is_blocked(self):
        runner = _load_runner()
        code = (
            "import os\n"
            "def on_tick(ctx, params):\n"
            "    return os.getcwd()\n"
        )
        with self.assertRaises(ImportError):
            runner.load_on_tick("", code)

    def test_import_sys_is_blocked(self):
        runner = _load_runner()
        code = "import sys\ndef on_tick(ctx, params):\n    pass\n"
        with self.assertRaises(ImportError):
            runner.load_on_tick("", code)

    def test_open_is_not_available(self):
        runner = _load_runner()
        # open() must NOT be in the restricted builtins → NameError at exec/run.
        code = (
            "def on_tick(ctx, params):\n"
            "    return open('/etc/passwd')\n"
        )
        fn = runner.load_on_tick("", code)  # defining is fine
        with self.assertRaises(NameError):
            fn(None, {})

    def test_eval_is_not_available(self):
        runner = _load_runner()
        code = "x = eval('1+1')\ndef on_tick(ctx, params):\n    pass\n"
        with self.assertRaises(NameError):
            runner.load_on_tick("", code)

    def test_missing_on_tick_raises(self):
        runner = _load_runner()
        code = "def something_else(ctx, params):\n    pass\n"
        with self.assertRaises(RuntimeError):
            runner.load_on_tick("", code)

    def test_non_callable_on_tick_raises(self):
        runner = _load_runner()
        code = "on_tick = 42\n"
        with self.assertRaises(RuntimeError):
            runner.load_on_tick("", code)

    def test_syntax_error_raises(self):
        runner = _load_runner()
        code = "def on_tick(ctx, params)\n    pass\n"  # missing colon
        with self.assertRaises(SyntaxError):
            runner.load_on_tick("", code)

    def test_user_code_takes_precedence_over_code_ref(self):
        runner = _load_runner()
        code = "def on_tick(ctx, params):\n    ctx.log('info', 'user')\n"
        fn = runner.load_on_tick("dual_ma", code)  # user_code wins
        self.assertTrue(callable(fn))
        self.assertEqual(fn.__name__, "on_tick")


TRIAL_ENV = {
    "TRIAL_MODE": "1",
    "PARAMS": "{}",
    "CODE_REF": "",
}


def _run_trial_subprocess(env_overrides: dict) -> dict:
    """Run runner.py in TRIAL_MODE as a subprocess; return parsed stdout JSON.

    Fully offline (no requests needed). Logs AND user print() go to stderr; stdout
    carries ONLY the result JSON, so we json.loads(stdout.strip()) directly.
    """
    proc = _run_trial_raw(env_overrides)
    # stdout must be exactly the result JSON — no need to hunt for the last line.
    return json.loads(proc.stdout.strip())


def _run_trial_raw(env_overrides: dict):
    """Run runner.py in TRIAL_MODE; return the completed subprocess (stdout+stderr)."""
    import os
    import subprocess

    env = dict(os.environ)
    env.update(TRIAL_ENV)
    env.update(env_overrides)
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(
        [sys.executable, os.path.join(here, "runner.py")],
        env=env,
        capture_output=True,
        text=True,
        cwd=here,
        timeout=60,
    )


def _synthetic_candles(closes: list[float]) -> str:
    data = [{"ts": i, "o": c, "h": c, "l": c, "c": c, "vol": 1, "volCcy": 1}
            for i, c in enumerate(closes)]
    return json.dumps(data)


class TestTrialMode(unittest.TestCase):
    """UC-T6: one-shot offline trial mode. Runs runner.py as a subprocess."""

    def test_trial_counts_signals(self):
        # dual_ma golden cross: 21 flat bars, spike on last → one buy signal.
        closes = [100.0] * 21
        closes[-1] = 200.0
        code = (
            "def on_tick(ctx, params):\n"
            "    cs = ctx.candles()\n"
            "    closes = [float(c['c']) for c in cs]\n"
            "    if len(closes) < 21:\n"
            "        return\n"
            "    fast = sum(closes[-5:]) / 5\n"
            "    slow = sum(closes[-20:]) / 20\n"
            "    if fast > slow:\n"
            "        ctx.buy('0.001')\n"
        )
        result = _run_trial_subprocess({
            "USER_CODE": code,
            "TRIAL_CANDLES": _synthetic_candles(closes),
        })
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["signal_count"], 1)

    def test_trial_no_signal(self):
        closes = [100.0] * 25  # flat, no cross
        code = (
            "def on_tick(ctx, params):\n"
            "    cs = ctx.candles()\n"
            "    closes = [float(c['c']) for c in cs]\n"
            "    if len(closes) < 21:\n"
            "        return\n"
            "    fast = sum(closes[-5:]) / 5\n"
            "    slow = sum(closes[-20:]) / 20\n"
            "    if fast > slow:\n"
            "        ctx.buy('0.001')\n"
        )
        result = _run_trial_subprocess({
            "USER_CODE": code,
            "TRIAL_CANDLES": _synthetic_candles(closes),
        })
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["signal_count"], 0)

    def test_trial_on_tick_exception_reports_tick(self):
        code = (
            "def on_tick(ctx, params):\n"
            "    raise ValueError('boom')\n"
        )
        result = _run_trial_subprocess({
            "USER_CODE": code,
            "TRIAL_CANDLES": _synthetic_candles([1.0, 2.0, 3.0]),
        })
        self.assertFalse(result["ok"], result)
        self.assertIn("boom", result["error"])
        self.assertEqual(result["tick"], 1)

    def test_trial_import_blocked_reports_load_failure(self):
        code = (
            "import os\n"
            "def on_tick(ctx, params):\n"
            "    pass\n"
        )
        result = _run_trial_subprocess({
            "USER_CODE": code,
            "TRIAL_CANDLES": _synthetic_candles([1.0, 2.0]),
        })
        self.assertFalse(result["ok"], result)
        self.assertIn("os", result["error"])

    def test_trial_builtin_dual_ma(self):
        # No USER_CODE → uses CODE_REF built-in.
        closes = [100.0] * 21
        closes[-1] = 200.0
        result = _run_trial_subprocess({
            "CODE_REF": "dual_ma",
            "TRIAL_CANDLES": _synthetic_candles(closes),
            "PARAMS": json.dumps({"fast_period": 5, "slow_period": 20, "sz": "0.001"}),
        })
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["signal_count"], 1)

    def test_trial_no_network_no_token_required(self):
        # No RUN_TOKEN / BACKEND_URL provided at all — trial must still work.
        code = "def on_tick(ctx, params):\n    ctx.buy('0.001')\n"
        result = _run_trial_subprocess({
            "USER_CODE": code,
            "TRIAL_CANDLES": _synthetic_candles([1.0, 2.0, 3.0, 4.0]),
        })
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["signal_count"], 4)

    def test_trial_user_print_goes_to_stderr_stdout_clean(self):
        # User print() must NOT pollute stdout — stdout is ONLY the result JSON so T3
        # can json.loads(stdout.strip()) directly and a user cannot forge the result.
        code = (
            "def on_tick(ctx, params):\n"
            "    print('FORGED {\"ok\": false, \"error\": \"hax\"}')\n"
            "    print('debug line from strategy')\n"
        )
        proc = _run_trial_raw({
            "USER_CODE": code,
            "TRIAL_CANDLES": _synthetic_candles([1.0, 2.0, 3.0]),
        })
        # stdout: exactly one JSON object, directly parseable (no last-line hunting).
        stdout = proc.stdout.strip()
        self.assertEqual(len(stdout.splitlines()), 1, f"stdout not clean: {stdout!r}")
        result = json.loads(stdout)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["signal_count"], 0)
        self.assertNotIn("FORGED", stdout)
        self.assertNotIn("debug line", stdout)
        # user print() landed on stderr instead.
        self.assertIn("FORGED", proc.stderr)
        self.assertIn("debug line from strategy", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
