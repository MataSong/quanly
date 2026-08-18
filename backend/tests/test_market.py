"""Tests for P1-C: Market feature — REST endpoints + MarketConsumer WebSocket.

OKX calls are stubbed with unittest.mock (test doubles, not product mocks).
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User

from core.accounts.models import Role, UserRole


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_market_viewer(username: str) -> User:
    """Create a user with market:view and page:market permissions."""
    user = User.objects.create_user(username, password="pw")
    role = Role.objects.create(
        name=f"market_viewer_{username}",
        permissions=["market:view", "page:market"],
    )
    UserRole.objects.create(user=user, role=role)
    return user


FAKE_CANDLES = [
    {
        "ts": 1700000000000,
        "o": "35000.0",
        "h": "35100.0",
        "l": "34900.0",
        "c": "35050.0",
        "vol": "10.5",
        "volCcy": "367500.0",
    }
]

FAKE_SYMBOLS = [
    {"instId": "BTC-USDT", "baseCcy": "BTC", "quoteCcy": "USDT", "state": "live"},
    {"instId": "ETH-USDT", "baseCcy": "ETH", "quoteCcy": "USDT", "state": "live"},
]


# ──────────────────────────────────────────────
# GET /api/market/candles — permission checks
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_candles_unauthenticated_returns_401(api_client):
    resp = api_client.get("/api/market/candles?symbol=BTC-USDT&bar=1m")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_candles_without_market_view_returns_403(api_client):
    user = User.objects.create_user("candles_noperm", password="pw")
    api_client.force_authenticate(user)
    with patch("core.market.okx_client.get_candles", return_value=FAKE_CANDLES):
        resp = api_client.get("/api/market/candles?symbol=BTC-USDT&bar=1m")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_candles_with_market_view_returns_200(api_client):
    user = _make_market_viewer("candles_ok")
    api_client.force_authenticate(user)
    with patch("core.market.views.okx_client.get_candles", return_value=FAKE_CANDLES):
        resp = api_client.get("/api/market/candles?symbol=BTC-USDT&bar=1m")
    assert resp.status_code == 200
    data = resp.data
    assert data["symbol"] == "BTC-USDT"
    assert data["bar"] == "1m"
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 1
    candle = data["data"][0]
    assert "ts" in candle
    assert "o" in candle
    assert "h" in candle
    assert "l" in candle
    assert "c" in candle


@pytest.mark.django_db
def test_candles_superuser_bypasses_permission(api_client):
    su = User.objects.create_superuser("candles_su", "su@x.com", "pw")
    api_client.force_authenticate(su)
    with patch("core.market.views.okx_client.get_candles", return_value=FAKE_CANDLES):
        resp = api_client.get("/api/market/candles?symbol=ETH-USDT&bar=5m")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_candles_okx_error_returns_502(api_client):
    user = _make_market_viewer("candles_502")
    api_client.force_authenticate(user)
    with patch("core.market.views.okx_client.get_candles", side_effect=RuntimeError("OKX down")):
        resp = api_client.get("/api/market/candles?symbol=BTC-USDT&bar=1m")
    assert resp.status_code == 502


# ──────────────────────────────────────────────
# GET /api/market/symbols — permission checks
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_symbols_unauthenticated_returns_401(api_client):
    resp = api_client.get("/api/market/symbols")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_symbols_without_market_view_returns_403(api_client):
    user = User.objects.create_user("symbols_noperm", password="pw")
    api_client.force_authenticate(user)
    with patch("core.market.views.okx_client.get_spot_symbols", return_value=FAKE_SYMBOLS):
        resp = api_client.get("/api/market/symbols")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_symbols_with_market_view_returns_200(api_client):
    user = _make_market_viewer("symbols_ok")
    api_client.force_authenticate(user)
    with patch("core.market.views.okx_client.get_spot_symbols", return_value=FAKE_SYMBOLS):
        resp = api_client.get("/api/market/symbols")
    assert resp.status_code == 200
    data = resp.data
    assert "data" in data
    assert len(data["data"]) == 2
    assert data["data"][0]["instId"] == "BTC-USDT"


@pytest.mark.django_db
def test_symbols_response_structure(api_client):
    user = _make_market_viewer("symbols_struct")
    api_client.force_authenticate(user)
    with patch("core.market.views.okx_client.get_spot_symbols", return_value=FAKE_SYMBOLS):
        resp = api_client.get("/api/market/symbols")
    assert resp.status_code == 200
    for sym in resp.data["data"]:
        assert "instId" in sym
        assert "baseCcy" in sym
        assert "quoteCcy" in sym

@pytest.mark.django_db
def test_candles_with_after_calls_history(api_client):
    """When `after` query param is provided, view uses get_history_candles."""
    user = _make_market_viewer("candles_after")
    api_client.force_authenticate(user)
    with patch(
        "core.market.views.okx_client.get_history_candles", return_value=FAKE_CANDLES
    ) as mock_hist:
        resp = api_client.get(
            "/api/market/candles?symbol=BTC-USDT&bar=1m&limit=100&after=1700000000000"
        )
    assert resp.status_code == 200
    mock_hist.assert_called_once_with(
        symbol="BTC-USDT", bar="1m", after="1700000000000", limit=100
    )
    data = resp.data
    assert data["symbol"] == "BTC-USDT"
    assert len(data["data"]) == 1


@pytest.mark.django_db
def test_candles_without_after_calls_get_candles(api_client):
    """When no `after` param, view uses get_candles (latest data)."""
    user = _make_market_viewer("candles_no_after")
    api_client.force_authenticate(user)
    with patch(
        "core.market.views.okx_client.get_candles", return_value=FAKE_CANDLES
    ) as mock_candles:
        resp = api_client.get("/api/market/candles?symbol=BTC-USDT&bar=1m")
    assert resp.status_code == 200
    mock_candles.assert_called_once()


@pytest.mark.django_db
def test_history_candles_okx_error_returns_502(api_client):
    """get_history_candles raising an error should return 502."""
    user = _make_market_viewer("hist_502")
    api_client.force_authenticate(user)
    with patch(
        "core.market.views.okx_client.get_history_candles",
        side_effect=RuntimeError("OKX history down"),
    ):
        resp = api_client.get(
            "/api/market/candles?symbol=BTC-USDT&bar=1m&after=1700000000000"
        )
    assert resp.status_code == 502


# ──────────────────────────────────────────────
# okx_client.get_history_candles unit tests
# ──────────────────────────────────────────────

def _fake_history_response(rows):
    return {"code": "0", "data": rows}


def test_get_history_candles_returns_oldest_first():
    """get_history_candles reverses OKX newest-first data to oldest-first."""
    fake_rows = [
        ["1700000060000", "35100", "35200", "35000", "35150", "5", "175750"],
        ["1700000000000", "35000", "35100", "34900", "35050", "10", "350000"],
    ]
    with patch(
        "core.market.okx_client._market_api"
    ) as mock_api_factory:
        mock_api = MagicMock()
        mock_api.get_history_candlesticks.return_value = _fake_history_response(fake_rows)
        mock_api_factory.return_value = mock_api

        from core.market.okx_client import get_history_candles
        result = get_history_candles("BTC-USDT", bar="1m", after="1700000060000", limit=2)

    assert len(result) == 2
    # Oldest bar first (ts=1700000000000)
    assert result[0]["ts"] == 1700000000000
    assert result[1]["ts"] == 1700000060000
    mock_api.get_history_candlesticks.assert_called_once_with(
        instId="BTC-USDT", bar="1m", limit="2", after="1700000060000"
    )


def test_get_history_candles_without_after():
    """after=None should not pass after kwarg to OKX."""
    fake_rows = [
        ["1700000000000", "35000", "35100", "34900", "35050", "10", "350000"],
    ]
    with patch("core.market.okx_client._market_api") as mock_api_factory:
        mock_api = MagicMock()
        mock_api.get_history_candlesticks.return_value = _fake_history_response(fake_rows)
        mock_api_factory.return_value = mock_api

        from core.market.okx_client import get_history_candles
        result = get_history_candles("BTC-USDT", bar="1m", after=None, limit=10)

    assert len(result) == 1
    call_kwargs = mock_api.get_history_candlesticks.call_args.kwargs
    assert "after" not in call_kwargs


def test_get_history_candles_okx_error_raises():
    """OKX non-zero code should raise RuntimeError."""
    with patch("core.market.okx_client._market_api") as mock_api_factory:
        mock_api = MagicMock()
        mock_api.get_history_candlesticks.return_value = {
            "code": "50001", "msg": "service unavailable"
        }
        mock_api_factory.return_value = mock_api

        from core.market.okx_client import get_history_candles
        import pytest as _pytest
        with _pytest.raises(RuntimeError, match="OKX get_history_candlesticks error"):
            get_history_candles("BTC-USDT")




def _make_access_token(user) -> str:
    """Mint a SimpleJWT AccessToken for user. Must be called in sync context."""
    from rest_framework_simplejwt.tokens import AccessToken
    tok = AccessToken()
    tok["user_id"] = user.pk
    return str(tok)

@pytest.mark.django_db
@pytest.mark.asyncio
async def test_ws_no_token_closes_4001():
    """Connection without token should be rejected with close code 4001."""
    from channels.testing import WebsocketCommunicator
    from config.asgi import application

    communicator = WebsocketCommunicator(
        application,
        "/ws/market/BTC-USDT/",  # no token
    )
    # consumer 在 accept 前 close(4001) → connect() 返回 (False, 4001)
    connected, close_code = await communicator.connect()
    assert connected is False
    assert close_code == 4001
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_ws_invalid_token_closes_4001():
    """Connection with a bogus token should be rejected with close code 4001."""
    from channels.testing import WebsocketCommunicator
    from config.asgi import application

    communicator = WebsocketCommunicator(
        application,
        "/ws/market/BTC-USDT/?token=notavalidjwt",
    )
    connected, close_code = await communicator.connect()
    assert connected is False
    assert close_code == 4001
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ws_valid_token_connects_and_receives_broadcast():
    """Valid JWT token allows connection; group_send message is forwarded to client."""
    from channels.testing import WebsocketCommunicator
    from channels.layers import get_channel_layer
    from asgiref.sync import sync_to_async
    from rest_framework_simplejwt.tokens import AccessToken
    from config.asgi import application

    # Create user and mint a JWT without any DB write (AccessToken constructor
    # only writes to DB via RefreshToken.for_user; AccessToken() + set claims avoids that)
    user = await sync_to_async(User.objects.create_user)(
        username="ws_valid_user", password="pw"
    )
    # Build token in sync context to avoid SynchronousOnlyOperation from token blacklist
    token = await sync_to_async(_make_access_token)(user)

    communicator = WebsocketCommunicator(
        application,
        f"/ws/market/BTC-USDT/?token={token}",
    )
    connected, _ = await communicator.connect()
    assert connected, "Expected WS connection to succeed with valid token"

    # Broadcast a market_update to the group — group now includes bar (default 1m)
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        "market_BTC-USDT_1m",
        {
            "type": "market.update",
            "symbol": "BTC-USDT",
            "candle": {"ts": 1700000060000, "o": "35100", "h": "35200", "l": "35000", "c": "35150", "vol": "5"},
        },
    )

    # The consumer should forward it to the WebSocket
    response = await communicator.receive_json_from(timeout=3)
    assert response["type"] == "market_update"
    assert response["symbol"] == "BTC-USDT"
    assert "candle" in response
    assert response["candle"]["ts"] == 1700000060000

    await communicator.disconnect()
