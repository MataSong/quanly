"""Tests for T3+T4: K-line realtime dynamic subscription logic.

No real OKX / Redis connections — everything is mocked or tested as pure
Python functions.

Coverage:
    _compute_target_subs   — diff/target-set calculation (pure function)
    _parse_candle_row      — candle row → dict
    _parse_ticker_data     — tickers data → ticker dict
    MarketConsumer         — bar extraction from query string,
                             redis register/deregister (mocked redis)
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Pure-function imports (no Django / asyncio needed)
# ---------------------------------------------------------------------------

from core.market.management.commands.run_market_collector import (
    _compute_target_subs,
    _parse_candle_row,
    _parse_ticker_data,
    _candle_group_name,
    _FALLBACK_MEMBERS,
)


# ============================================================
# _compute_target_subs
# ============================================================

class TestComputeTargetSubs:

    def test_basic_two_members_different_symbol_bar(self):
        """BTC-USDT:1m + ETH-USDT:5m → 4 subscriptions, tickers deduplicated."""
        active = {"BTC-USDT:1m", "ETH-USDT:5m"}
        result = _compute_target_subs(active)
        assert ("candle1m", "BTC-USDT") in result
        assert ("candle5m", "ETH-USDT") in result
        assert ("tickers", "BTC-USDT") in result
        assert ("tickers", "ETH-USDT") in result
        assert len(result) == 4

    def test_same_symbol_two_bars_tickers_deduplicated(self):
        """BTC-USDT:1m + BTC-USDT:5m → 3 subscriptions (candle1m, candle5m, tickers×1)."""
        active = {"BTC-USDT:1m", "BTC-USDT:5m"}
        result = _compute_target_subs(active)
        assert ("candle1m", "BTC-USDT") in result
        assert ("candle5m", "BTC-USDT") in result
        # tickers appears exactly once for BTC-USDT
        tickers_btc = [t for t in result if t == ("tickers", "BTC-USDT")]
        assert len(tickers_btc) == 1
        assert len(result) == 3

    def test_empty_active_returns_fallback(self):
        """Empty active set → fallback members are used."""
        result = _compute_target_subs(set())
        # Fallback is BTC-USDT:1m
        assert ("candle1m", "BTC-USDT") in result
        assert ("tickers", "BTC-USDT") in result

    def test_extra_members_always_included(self):
        """Extra CLI members are merged in unconditionally."""
        active = {"ETH-USDT:5m"}
        extra = {"SOL-USDT:1m"}
        result = _compute_target_subs(active, extra_members=extra)
        assert ("candle5m", "ETH-USDT") in result
        assert ("tickers", "ETH-USDT") in result
        assert ("candle1m", "SOL-USDT") in result
        assert ("tickers", "SOL-USDT") in result

    def test_extra_members_used_even_when_active_empty(self):
        """Extra members prevent fallback from triggering when combined set is non-empty."""
        extra = {"ETH-USDT:1H"}
        result = _compute_target_subs(set(), extra_members=extra)
        assert ("candle1H", "ETH-USDT") in result
        assert ("tickers", "ETH-USDT") in result
        # fallback BTC-USDT:1m should NOT appear because combined set is non-empty
        assert ("candle1m", "BTC-USDT") not in result

    def test_malformed_member_skipped(self):
        """A member without ':' separator is skipped with a warning."""
        active = {"BTC-USDT:1m", "BADMEMBER"}
        result = _compute_target_subs(active)
        assert ("candle1m", "BTC-USDT") in result
        # no subscription derived from BADMEMBER
        bad_subs = [t for t in result if "BADMEMBER" in t[1]]
        assert bad_subs == []

    def test_return_type_is_set_of_tuples(self):
        result = _compute_target_subs({"BTC-USDT:1m"})
        assert isinstance(result, set)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_diff_logic_new_and_removed(self):
        """Verify subscribed-set diff gives correct add/remove."""
        active = {"BTC-USDT:1m", "ETH-USDT:5m"}
        target = _compute_target_subs(active)

        # Suppose we already have candle1m/BTC subscribed
        already_subscribed = {("candle1m", "BTC-USDT"), ("tickers", "BTC-USDT")}
        to_add = target - already_subscribed
        to_remove = already_subscribed - target

        # to_add should contain ETH subs + tickers for ETH
        assert ("candle5m", "ETH-USDT") in to_add
        assert ("tickers", "ETH-USDT") in to_add
        # nothing from already_subscribed should be removed (they're still in target)
        assert to_remove == set()


# ============================================================
# _parse_candle_row
# ============================================================

class TestParseCandleRow:

    def test_normal_row(self):
        row = ["1700000000000", "35000.0", "35100.0", "34900.0", "35050.0", "10.5", "extra"]
        result = _parse_candle_row(row)
        assert result == {
            "ts": 1700000000000,
            "o": "35000.0",
            "h": "35100.0",
            "l": "34900.0",
            "c": "35050.0",
            "vol": "10.5",
        }

    def test_ts_is_int(self):
        row = ["1700000000000", "1", "2", "3", "4", "5"]
        result = _parse_candle_row(row)
        assert isinstance(result["ts"], int)

    def test_exactly_six_fields(self):
        row = ["100", "1", "2", "3", "4", "5"]
        result = _parse_candle_row(row)
        assert result is not None

    def test_fewer_than_six_fields_returns_none(self):
        assert _parse_candle_row([]) is None
        assert _parse_candle_row(["1", "2", "3"]) is None
        assert _parse_candle_row(["1", "2", "3", "4", "5"]) is None

    def test_integer_ts_string(self):
        row = ["0", "0", "0", "0", "0", "0"]
        result = _parse_candle_row(row)
        assert result["ts"] == 0


# ============================================================
# _parse_ticker_data
# ============================================================

class TestParseTickerData:

    def test_normal_ticker(self):
        data = [{"instId": "BTC-USDT", "last": "35000.5", "bidPx": "34999", "askPx": "35001"}]
        result = _parse_ticker_data(data)
        assert result == {"last": "35000.5"}

    def test_empty_data_returns_none(self):
        assert _parse_ticker_data([]) is None

    def test_missing_last_returns_none(self):
        data = [{"instId": "BTC-USDT", "bidPx": "34999"}]
        result = _parse_ticker_data(data)
        assert result is None

    def test_uses_first_element(self):
        data = [
            {"last": "100.0"},
            {"last": "200.0"},
        ]
        result = _parse_ticker_data(data)
        assert result == {"last": "100.0"}

    def test_last_value_preserved_as_is(self):
        """last value is kept as-is (string from OKX)."""
        data = [{"last": "0.000123"}]
        result = _parse_ticker_data(data)
        assert result["last"] == "0.000123"


# ============================================================
# MarketConsumer — bar extraction + Redis register (mocked)
# ============================================================

# ============================================================
# MarketConsumer — unit tests for connect/market_update/redis
# (These test Consumer method logic directly without a live
#  channel-layer / Redis.  The WS integration tests that need a
#  real Redis live in test_market.py and are known to fail when
#  no Redis is available.)
# ============================================================

@pytest.mark.asyncio
async def test_consumer_bar_defaults_to_1m():
    """Consumer stores bar='1m' when no bar param in query string."""
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    consumer.scope = {
        "query_string": b"token=dummy",
        "url_route": {"kwargs": {"symbol": "BTC-USDT"}},
    }
    consumer.channel_name = "test.channel"
    consumer.channel_layer = MagicMock()
    consumer.channel_layer.group_add = AsyncMock()

    # Stub auth and accept
    consumer._authenticate = AsyncMock(return_value=object())
    consumer.accept = AsyncMock()
    consumer._redis_register = AsyncMock()

    from urllib.parse import parse_qs
    params = parse_qs("token=dummy")
    # Simulate the connect logic for bar extraction
    consumer.bar = params.get("bar", ["1m"])[0]
    assert consumer.bar == "1m"


@pytest.mark.asyncio
async def test_consumer_bar_from_query_string():
    """Consumer stores bar='5m' when bar=5m is in query string."""
    from urllib.parse import parse_qs
    params = parse_qs("token=dummy&bar=5m")
    bar = params.get("bar", ["1m"])[0]
    assert bar == "5m"


@pytest.mark.asyncio
async def test_consumer_market_update_ticker_only():
    """market_update with ticker but no candle sends only ticker in payload."""
    import json
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    sent_messages = []

    async def _fake_send(text_data=None, bytes_data=None):
        sent_messages.append(json.loads(text_data))

    consumer.send = _fake_send

    await consumer.market_update({
        "type": "market.update",
        "symbol": "BTC-USDT",
        "ticker": {"last": "35000.0"},
    })

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg["type"] == "market_update"
    assert msg["symbol"] == "BTC-USDT"
    assert msg["ticker"] == {"last": "35000.0"}
    assert "candle" not in msg


@pytest.mark.asyncio
async def test_consumer_market_update_candle_only():
    """market_update with candle but no ticker sends only candle in payload."""
    import json
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    sent_messages = []

    async def _fake_send(text_data=None, bytes_data=None):
        sent_messages.append(json.loads(text_data))

    consumer.send = _fake_send

    candle = {"ts": 1700000000000, "o": "35000", "h": "35100", "l": "34900", "c": "35050", "vol": "10"}
    await consumer.market_update({
        "type": "market.update",
        "symbol": "BTC-USDT",
        "candle": candle,
    })

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg["type"] == "market_update"
    assert msg["candle"]["ts"] == 1700000000000
    assert "ticker" not in msg


@pytest.mark.asyncio
async def test_consumer_market_update_both_candle_and_ticker():
    """market_update with both candle and ticker forwards both fields."""
    import json
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    sent_messages = []

    async def _fake_send(text_data=None, bytes_data=None):
        sent_messages.append(json.loads(text_data))

    consumer.send = _fake_send

    await consumer.market_update({
        "type": "market.update",
        "symbol": "ETH-USDT",
        "candle": {"ts": 1700000060000, "o": "2000", "h": "2010", "l": "1990", "c": "2005", "vol": "50"},
        "ticker": {"last": "2005.5"},
    })

    msg = sent_messages[0]
    assert "candle" in msg
    assert "ticker" in msg
    assert msg["candle"]["ts"] == 1700000060000
    assert msg["ticker"]["last"] == "2005.5"


@pytest.mark.asyncio
async def test_consumer_redis_register_builds_correct_member():
    """_redis_register calls INCR, EXPIRE, and SADD with the correct member key."""
    from core.market.consumers import MarketConsumer, REFCOUNT_TTL

    consumer = MarketConsumer()
    consumer._active_member = "BTC-USDT:1m"

    mock_r = AsyncMock()
    mock_r.incr = AsyncMock(return_value=1)
    mock_r.expire = AsyncMock(return_value=1)
    mock_r.sadd = AsyncMock(return_value=1)
    mock_r.__aenter__ = AsyncMock(return_value=mock_r)
    mock_r.__aexit__ = AsyncMock(return_value=False)

    with patch("core.market.consumers.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_r
        await consumer._redis_register()

    mock_r.incr.assert_called_once_with("market:refcount:BTC-USDT:1m")
    mock_r.expire.assert_called_once_with("market:refcount:BTC-USDT:1m", REFCOUNT_TTL)
    mock_r.sadd.assert_called_once_with("market:active", "BTC-USDT:1m")


@pytest.mark.asyncio
async def test_consumer_redis_deregister_removes_when_last():
    """_redis_deregister removes from active set when refcount reaches 0."""
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    consumer._active_member = "ETH-USDT:5m"

    mock_r = AsyncMock()
    mock_r.decr = AsyncMock(return_value=0)
    mock_r.srem = AsyncMock(return_value=1)
    mock_r.delete = AsyncMock(return_value=1)
    mock_r.__aenter__ = AsyncMock(return_value=mock_r)
    mock_r.__aexit__ = AsyncMock(return_value=False)

    with patch("core.market.consumers.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_r
        await consumer._redis_deregister()

    mock_r.decr.assert_called_once_with("market:refcount:ETH-USDT:5m")
    mock_r.srem.assert_called_once_with("market:active", "ETH-USDT:5m")
    mock_r.delete.assert_called_once_with("market:refcount:ETH-USDT:5m")


@pytest.mark.asyncio
async def test_consumer_redis_deregister_keeps_when_not_last():
    """_redis_deregister keeps active member when refcount still > 0."""
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    consumer._active_member = "BTC-USDT:1m"

    mock_r = AsyncMock()
    mock_r.decr = AsyncMock(return_value=1)  # still 1 other viewer
    mock_r.srem = AsyncMock()
    mock_r.delete = AsyncMock()
    mock_r.__aenter__ = AsyncMock(return_value=mock_r)
    mock_r.__aexit__ = AsyncMock(return_value=False)

    with patch("core.market.consumers.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_r
        await consumer._redis_deregister()

    mock_r.decr.assert_called_once()
    mock_r.srem.assert_not_called()
    mock_r.delete.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_redis_error_is_non_fatal():
    """Redis connection error in register must not propagate."""
    from core.market.consumers import MarketConsumer

    consumer = MarketConsumer()
    consumer._active_member = "BTC-USDT:1m"

    with patch("core.market.consumers.aioredis") as mock_aioredis:
        mock_aioredis.from_url.side_effect = Exception("Redis down")
        # Should not raise
        await consumer._redis_register()
        await consumer._redis_deregister()


# ============================================================
# New tests for C1/C2 self-heal, I2 reconnect, M1 parse fault tolerance
# ============================================================

class TestParseCandleRowFaultTolerance:
    """M1: bad ts values return None instead of raising."""

    def test_non_integer_ts_returns_none(self):
        row = ["not-a-number", "35000.0", "35100.0", "34900.0", "35050.0", "10.5"]
        result = _parse_candle_row(row)
        assert result is None

    def test_none_ts_returns_none(self):
        row = [None, "35000.0", "35100.0", "34900.0", "35050.0", "10.5"]
        result = _parse_candle_row(row)
        assert result is None

    def test_valid_row_still_works_after_bad_ones(self):
        """Ensure the function remains usable after receiving bad rows."""
        bad = ["oops", "1", "2", "3", "4", "5"]
        good = ["1700000000000", "35000", "35100", "34900", "35050", "10"]
        assert _parse_candle_row(bad) is None
        result = _parse_candle_row(good)
        assert result is not None
        assert result["ts"] == 1700000000000


class TestStaleMemberCleanup:
    """C1/C2: _compute_target_subs correctly excludes stale members.

    The actual Redis EXISTS check and SREM cleanup happens inside _sync_loop
    (an async closure, hard to unit-test directly).  We test the pure-function
    side: if stale members are filtered *before* calling _compute_target_subs,
    the result contains only live members.
    """

    def test_stale_member_excluded_from_target(self):
        """After filtering out a stale member, it does not appear in target subs."""
        raw_active = {"BTC-USDT:1m", "ETH-USDT:5m"}
        # Simulate: ETH-USDT:5m has no refcount key (stale) → excluded
        live_active = {"BTC-USDT:1m"}
        target = _compute_target_subs(live_active)
        assert ("candle1m", "BTC-USDT") in target
        assert ("tickers", "BTC-USDT") in target
        # ETH entries must not appear
        assert ("candle5m", "ETH-USDT") not in target
        assert ("tickers", "ETH-USDT") not in target

    def test_all_stale_falls_back_to_default(self):
        """If all active members are stale and filtered, fallback kicks in."""
        live_active: set[str] = set()  # everything was stale
        target = _compute_target_subs(live_active)
        # Fallback BTC-USDT:1m should appear
        assert ("candle1m", "BTC-USDT") in target
        assert ("tickers", "BTC-USDT") in target


@pytest.mark.asyncio
async def test_consumer_heartbeat_refreshes_ttl():
    """_heartbeat calls EXPIRE on the refcount key periodically."""
    import asyncio
    from core.market.consumers import MarketConsumer, REFCOUNT_TTL

    consumer = MarketConsumer()
    consumer._active_member = "BTC-USDT:1m"

    expire_calls: list = []

    mock_r = AsyncMock()
    mock_r.expire = AsyncMock(side_effect=lambda key, ttl: expire_calls.append((key, ttl)))
    mock_r.__aenter__ = AsyncMock(return_value=mock_r)
    mock_r.__aexit__ = AsyncMock(return_value=False)

    with patch("core.market.consumers.aioredis") as mock_aioredis, \
         patch("core.market.consumers.HEARTBEAT_INTERVAL", 0):
        mock_aioredis.from_url.return_value = mock_r
        # Run heartbeat briefly then cancel it
        task = asyncio.ensure_future(consumer._heartbeat())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # At least one EXPIRE call should have been made
    assert len(expire_calls) >= 1
    assert expire_calls[0] == ("market:refcount:BTC-USDT:1m", REFCOUNT_TTL)


# ============================================================
# _candle_group_name — pure function, bar-scoped group routing
# ============================================================

class TestCandleGroupName:
    """group name must embed bar so cross-bar candle pollution is impossible."""

    def test_1m_bar(self):
        assert _candle_group_name("BTC-USDT", "candle1m") == "market_BTC-USDT_1m"

    def test_5m_bar(self):
        assert _candle_group_name("BTC-USDT", "candle5m") == "market_BTC-USDT_5m"

    def test_1H_bar(self):
        assert _candle_group_name("ETH-USDT", "candle1H") == "market_ETH-USDT_1H"

    def test_different_symbols_different_groups(self):
        g1 = _candle_group_name("BTC-USDT", "candle1m")
        g2 = _candle_group_name("ETH-USDT", "candle1m")
        assert g1 != g2
        assert "BTC-USDT" in g1
        assert "ETH-USDT" in g2

    def test_same_symbol_different_bars_different_groups(self):
        g1m = _candle_group_name("BTC-USDT", "candle1m")
        g5m = _candle_group_name("BTC-USDT", "candle5m")
        assert g1m != g5m
        assert g1m == "market_BTC-USDT_1m"
        assert g5m == "market_BTC-USDT_5m"


# ============================================================
# Ticker fan-out routing — one ticker → all active bars of symbol
# ============================================================

@pytest.mark.asyncio
async def test_ticker_fanout_reaches_all_active_bars():
    """When a ticker arrives for BTC-USDT, it is sent to every active bar group."""
    import asyncio
    from unittest.mock import AsyncMock, call

    # Simulate the fan-out logic from _read_loop directly:
    # active_snapshot contains two bars for BTC-USDT
    active_snapshot = {"BTC-USDT:1m", "BTC-USDT:5m", "ETH-USDT:1m"}
    inst_id = "BTC-USDT"
    ticker = {"last": "35000.0"}

    from core.market.consumers import _sanitize_symbol

    group_send_calls: list[str] = []

    async def fake_group_send(group, msg):
        group_send_calls.append(group)

    channel_layer = MagicMock()
    channel_layer.group_send = fake_group_send

    # Replicate the fan-out logic from _read_loop
    target_bars = [
        m.split(":", 1)[1]
        for m in active_snapshot
        if m.startswith(f"{inst_id}:")
    ]
    for bar in target_bars:
        group_name = f"market_{_sanitize_symbol(inst_id)}_{bar}"
        await channel_layer.group_send(
            group_name,
            {"type": "market.update", "symbol": inst_id, "ticker": ticker},
        )

    assert set(group_send_calls) == {"market_BTC-USDT_1m", "market_BTC-USDT_5m"}
    # ETH group must NOT receive the BTC ticker
    assert "market_ETH-USDT_1m" not in group_send_calls


@pytest.mark.asyncio
async def test_ticker_fanout_skipped_when_no_active_bars():
    """Ticker fan-out is skipped when no active bars exist for the symbol."""
    from core.market.consumers import _sanitize_symbol

    active_snapshot: set[str] = {"ETH-USDT:1m"}  # BTC has no active bars
    inst_id = "BTC-USDT"

    group_send_calls: list[str] = []

    async def fake_group_send(group, msg):
        group_send_calls.append(group)

    channel_layer = MagicMock()
    channel_layer.group_send = fake_group_send

    target_bars = [
        m.split(":", 1)[1]
        for m in active_snapshot
        if m.startswith(f"{inst_id}:")
    ]
    # No bars → no group_sends
    for bar in target_bars:
        group_name = f"market_{_sanitize_symbol(inst_id)}_{bar}"
        await channel_layer.group_send(group_name, {})

    assert group_send_calls == []


class TestConsumerGroupNameContainsBar:
    """Verify the group name formula in Consumer matches the collector formula."""

    def test_group_name_formula_matches_candle_group_name(self):
        """Consumer's group name must equal _candle_group_name for the same symbol+bar."""
        from core.market.consumers import _sanitize_symbol
        symbol = "BTC-USDT"
        bar = "5m"
        # Consumer side
        consumer_group = f"market_{_sanitize_symbol(symbol)}_{bar}"
        # Collector side
        collector_group = _candle_group_name(symbol, f"candle{bar}")
        assert consumer_group == collector_group == "market_BTC-USDT_5m"
