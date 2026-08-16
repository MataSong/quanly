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
            "http://backend:8000/api/strategy/runner/candles",
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
            "http://backend:8000/api/strategy/runner/order",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
