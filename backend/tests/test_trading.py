"""Tests for P2-A: Trading backend — OKX place/cancel/positions/balance.

All OKX calls are patched with unittest.mock (test doubles).
Zero real OKX calls in this suite.
"""
import pytest
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User

from core.credentials.crypto import encrypt
from core.credentials.models import Credential
from core.accounts.models import Role, UserRole
from core.audit.models import AuditLog


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_user_with_perms(username: str, perms: list[str]) -> User:
    user = User.objects.create_user(username, password="pw")
    role = Role.objects.create(name=f"role_{username}", permissions=perms)
    UserRole.objects.create(user=user, role=role)
    return user


def _make_credential(user: User, env: str = Credential.ENV_SIM, label: str = "default") -> Credential:
    return Credential.objects.create(
        user=user,
        env=env,
        label=label,
        api_key_enc=encrypt("test-api-key"),
        secret_enc=encrypt("test-secret"),
        passphrase_enc=encrypt("test-passphrase"),
    )


def _okx_place_success(ord_id: str = "ORD123") -> dict:
    return {
        "code": "0",
        "msg": "",
        "data": [{"ordId": ord_id, "clOrdId": "CL001", "sCode": "0", "sMsg": ""}],
    }


def _okx_cancel_success(ord_id: str = "ORD123") -> dict:
    return {
        "code": "0",
        "msg": "",
        "data": [{"ordId": ord_id, "clOrdId": "CL001"}],
    }


def _okx_orders_success() -> dict:
    return {"code": "0", "msg": "", "data": [{"ordId": "ORD999", "instId": "BTC-USDT"}]}


def _okx_positions_success() -> dict:
    return {"code": "0", "msg": "", "data": [{"posId": "POS1", "instId": "BTC-USDT-SWAP"}]}


def _okx_balance_success() -> dict:
    return {"code": "0", "msg": "", "data": [{"totalEq": "10000"}]}


# ──────────────────────────────────────────────
# ① 无 trading:place_order 权限 → 403;有权限调 OKX(打桩)
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_place_order_without_perm_returns_403(api_client):
    """User without trading:place_order gets 403."""
    user = _make_user_with_perms("no_trade_perm", ["trading:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)
    resp = api_client.post("/api/trading/order", {
        "credential_id": cred.id,
        "inst_type": "SPOT",
        "inst_id": "BTC-USDT",
        "side": "buy",
        "ord_type": "limit",
        "sz": "0.01",
        "px": "50000",
    }, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_place_order_with_perm_calls_okx(api_client):
    """User with trading:place_order calls OKX (stubbed) and gets 201."""
    user = _make_user_with_perms("trade_ok", ["trading:place_order"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_trade_api = MagicMock()
    mock_trade_api.place_order.return_value = _okx_place_success("ORD_OK")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_trade_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "BTC-USDT",
            "side": "buy",
            "ord_type": "limit",
            "sz": "0.01",
            "px": "50000",
        }, format="json")

    assert resp.status_code == 201
    assert resp.data["okx"]["ordId"] == "ORD_OK"
    mock_trade_api.place_order.assert_called_once()


# ──────────────────────────────────────────────
# ② 多租户:用别人 credential_id → 404
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_place_order_other_user_credential_returns_404(api_client):
    """Using another user's credential_id must return 404 (multi-tenant)."""
    owner = _make_user_with_perms("cred_owner", ["trading:place_order"])
    attacker = _make_user_with_perms("attacker", ["trading:place_order"])
    cred = _make_credential(owner)

    api_client.force_authenticate(attacker)
    resp = api_client.post("/api/trading/order", {
        "credential_id": cred.id,
        "inst_type": "SPOT",
        "inst_id": "BTC-USDT",
        "side": "buy",
        "ord_type": "market",
        "sz": "0.01",
    }, format="json")
    assert resp.status_code == 404


# ──────────────────────────────────────────────
# ③ flag 映射: sim → "1", live → "0"
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_flag_mapping_sim_credential(api_client):
    """sim credential must produce flag='1' when constructing TradeAPI."""
    user = _make_user_with_perms("flag_sim", ["trading:place_order"])
    cred = _make_credential(user, env=Credential.ENV_SIM)
    api_client.force_authenticate(user)

    captured_flags = []

    def fake_trade_api(c):
        from okx import Trade  # type: ignore[import]
        from core.credentials.crypto import decrypt
        api_key = decrypt(c.api_key_enc)
        secret = decrypt(c.secret_enc)
        passphrase = decrypt(c.passphrase_enc)
        flag = "1" if c.env == Credential.ENV_SIM else "0"
        captured_flags.append(flag)
        m = MagicMock()
        m.place_order.return_value = _okx_place_success()
        return m

    with patch("core.trading.okx_ext._trade_api", side_effect=fake_trade_api):
        api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "BTC-USDT",
            "side": "buy",
            "ord_type": "market",
            "sz": "0.01",
        }, format="json")

    assert captured_flags == ["1"]


@pytest.mark.django_db
def test_flag_mapping_live_credential(api_client):
    """live credential must produce flag='0' when constructing TradeAPI."""
    user = _make_user_with_perms("flag_live", ["trading:place_order"])
    cred = _make_credential(user, env=Credential.ENV_LIVE)
    api_client.force_authenticate(user)

    captured_flags = []

    def fake_trade_api(c):
        flag = "1" if c.env == Credential.ENV_SIM else "0"
        captured_flags.append(flag)
        m = MagicMock()
        m.place_order.return_value = _okx_place_success()
        return m

    with patch("core.trading.okx_ext._trade_api", side_effect=fake_trade_api):
        api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "ETH-USDT",
            "side": "sell",
            "ord_type": "market",
            "sz": "0.1",
        }, format="json")

    assert captured_flags == ["0"]


@pytest.mark.django_db
def test_flag_in_okx_ext_directly():
    """Unit test _flag() directly: sim→'1', live→'0'."""
    from core.trading.okx_ext import _flag
    user = User.objects.create_user("flag_unit", password="pw")
    sim_cred = _make_credential(user, env=Credential.ENV_SIM, label="sim")
    live_cred = _make_credential(user, env=Credential.ENV_LIVE, label="live")
    assert _flag(sim_cred) == "1"
    assert _flag(live_cred) == "0"


# ──────────────────────────────────────────────
# ④ 下单成功 → Order 字段正确落库
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_place_order_creates_order_record(api_client):
    """Successful order places an Order record with correct fields."""
    from core.trading.models import Order

    user = _make_user_with_perms("order_record", ["trading:place_order"])
    cred = _make_credential(user, env=Credential.ENV_SIM)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = _okx_place_success("ORD_FIELDS")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "BTC-USDT",
            "side": "buy",
            "ord_type": "limit",
            "sz": "0.05",
            "px": "48000",
        }, format="json")

    assert resp.status_code == 201

    order = Order.objects.get(okx_ord_id="ORD_FIELDS")
    assert order.user == user
    assert order.credential == cred
    assert order.env == Credential.ENV_SIM
    assert order.inst_type == "SPOT"
    assert order.inst_id == "BTC-USDT"
    assert order.side == "buy"
    assert order.ord_type == "limit"
    assert order.sz == "0.05"
    assert order.px == "48000"
    assert order.td_mode == "cash"  # SPOT default
    assert order.reduce_only is False
    assert order.cl_ord_id == "CL001"


# ──────────────────────────────────────────────
# ⑤ 撤单
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_cancel_order_success(api_client):
    """POST /api/trading/cancel with valid credential and ordId returns 200."""
    user = _make_user_with_perms("cancel_ok", ["trading:cancel"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.cancel_order.return_value = _okx_cancel_success("ORD_CANCEL")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/cancel", {
            "credential_id": cred.id,
            "inst_id": "BTC-USDT",
            "ord_id": "ORD_CANCEL",
        }, format="json")

    assert resp.status_code == 200
    assert resp.data["okx"]["ordId"] == "ORD_CANCEL"
    mock_api.cancel_order.assert_called_once_with(instId="BTC-USDT", ordId="ORD_CANCEL")


@pytest.mark.django_db
def test_cancel_order_without_perm_returns_403(api_client):
    user = _make_user_with_perms("cancel_noperm", ["trading:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)
    resp = api_client.post("/api/trading/cancel", {
        "credential_id": cred.id,
        "inst_id": "BTC-USDT",
        "ord_id": "ORD1",
    }, format="json")
    assert resp.status_code == 403


# ──────────────────────────────────────────────
# ⑥ 现货 vs 永续 参数分支
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_spot_order_uses_cash_td_mode(api_client):
    """SPOT order without explicit td_mode uses 'cash'."""
    from core.trading.models import Order

    user = _make_user_with_perms("spot_cash", ["trading:place_order"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = _okx_place_success("ORD_SPOT")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "ETH-USDT",
            "side": "buy",
            "ord_type": "market",
            "sz": "0.1",
        }, format="json")

    assert resp.status_code == 201
    call_kwargs = mock_api.place_order.call_args[1]
    assert call_kwargs["tdMode"] == "cash"

    order = Order.objects.get(okx_ord_id="ORD_SPOT")
    assert order.td_mode == "cash"


@pytest.mark.django_db
def test_swap_order_uses_cross_td_mode_and_pos_side(api_client):
    """SWAP order without explicit td_mode uses 'cross', posSide is forwarded."""
    from core.trading.models import Order

    user = _make_user_with_perms("swap_cross", ["trading:place_order"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = _okx_place_success("ORD_SWAP")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SWAP",
            "inst_id": "BTC-USDT-SWAP",
            "side": "buy",
            "ord_type": "limit",
            "sz": "1",
            "px": "50000",
            "pos_side": "long",
        }, format="json")

    assert resp.status_code == 201
    call_kwargs = mock_api.place_order.call_args[1]
    assert call_kwargs["tdMode"] == "cross"
    assert call_kwargs["posSide"] == "long"

    order = Order.objects.get(okx_ord_id="ORD_SWAP")
    assert order.td_mode == "cross"
    assert order.pos_side == "long"
    assert order.inst_type == "SWAP"


@pytest.mark.django_db
def test_swap_order_reduce_only(api_client):
    """SWAP order with reduce_only=True passes reduceOnly='true' to OKX."""
    user = _make_user_with_perms("swap_reduce", ["trading:place_order"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = _okx_place_success("ORD_REDUCE")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SWAP",
            "inst_id": "ETH-USDT-SWAP",
            "side": "sell",
            "ord_type": "market",
            "sz": "2",
            "pos_side": "long",
            "reduce_only": True,
        }, format="json")

    assert resp.status_code == 201
    call_kwargs = mock_api.place_order.call_args[1]
    assert call_kwargs.get("reduceOnly") == "true"


# ──────────────────────────────────────────────
# ⑦ OKX 报错 → 502
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_place_order_okx_error_returns_502(api_client):
    """If OKX returns non-zero code, view returns 502."""
    user = _make_user_with_perms("okx_err", ["trading:place_order"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = {
        "code": "51000",
        "msg": "Parameter posSide error",
        "data": [],
    }

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "BTC-USDT",
            "side": "buy",
            "ord_type": "market",
            "sz": "0.01",
        }, format="json")

    assert resp.status_code == 502
    assert "detail" in resp.data


@pytest.mark.django_db
def test_cancel_order_okx_error_returns_502(api_client):
    user = _make_user_with_perms("cancel_err", ["trading:cancel"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.cancel_order.return_value = {
        "code": "51400",
        "msg": "Cancellation failed as order had already been filled",
        "data": [],
    }

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/cancel", {
            "credential_id": cred.id,
            "inst_id": "BTC-USDT",
            "ord_id": "ORD_FILLED",
        }, format="json")

    assert resp.status_code == 502


# ──────────────────────────────────────────────
# ⑧ @audit 写日志
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_place_order_writes_audit_log(api_client):
    """Successful place_order writes an AuditLog entry."""
    user = _make_user_with_perms("audit_test", ["trading:place_order"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = _okx_place_success("ORD_AUDIT")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/order", {
            "credential_id": cred.id,
            "inst_type": "SPOT",
            "inst_id": "BTC-USDT",
            "side": "buy",
            "ord_type": "market",
            "sz": "0.01",
        }, format="json")

    assert resp.status_code == 201
    log = AuditLog.objects.filter(user=user, action="trading.place_order").first()
    assert log is not None


@pytest.mark.django_db
def test_cancel_order_writes_audit_log(api_client):
    """Successful cancel_order writes an AuditLog entry."""
    user = _make_user_with_perms("audit_cancel", ["trading:cancel"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.cancel_order.return_value = _okx_cancel_success("ORD_AUD_C")

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.post("/api/trading/cancel", {
            "credential_id": cred.id,
            "inst_id": "BTC-USDT",
            "ord_id": "ORD_AUD_C",
        }, format="json")

    assert resp.status_code == 200
    log = AuditLog.objects.filter(user=user, action="trading.cancel_order").first()
    assert log is not None


# ──────────────────────────────────────────────
# GET endpoints: orders / positions / balance
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_get_orders_returns_okx_data(api_client):
    user = _make_user_with_perms("get_orders", ["trading:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_api = MagicMock()
    mock_api.get_order_list.return_value = _okx_orders_success()

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        resp = api_client.get(f"/api/trading/orders?credential_id={cred.id}")

    assert resp.status_code == 200
    assert resp.data["data"][0]["ordId"] == "ORD999"


@pytest.mark.django_db
def test_get_positions_returns_okx_data(api_client):
    user = _make_user_with_perms("get_positions", ["trading:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_account_api = MagicMock()
    mock_account_api.get_positions.return_value = _okx_positions_success()

    with patch("core.trading.okx_ext._account_api", return_value=mock_account_api):
        resp = api_client.get(f"/api/trading/positions?credential_id={cred.id}")

    assert resp.status_code == 200
    assert resp.data["data"][0]["posId"] == "POS1"


@pytest.mark.django_db
def test_get_balance_returns_okx_data(api_client):
    user = _make_user_with_perms("get_balance", ["trading:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    mock_account_api = MagicMock()
    mock_account_api.get_account_balance.return_value = _okx_balance_success()

    with patch("core.trading.okx_ext._account_api", return_value=mock_account_api):
        resp = api_client.get(f"/api/trading/balance?credential_id={cred.id}")

    assert resp.status_code == 200
    assert resp.data["data"][0]["totalEq"] == "10000"


@pytest.mark.django_db
def test_get_orders_without_view_perm_returns_403(api_client):
    user = _make_user_with_perms("orders_noperm", [])
    cred = _make_credential(user)
    api_client.force_authenticate(user)
    resp = api_client.get(f"/api/trading/orders?credential_id={cred.id}")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_get_orders_missing_credential_id_returns_400(api_client):
    user = _make_user_with_perms("orders_nocred", ["trading:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/trading/orders")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_get_orders_other_user_credential_returns_404(api_client):
    owner = _make_user_with_perms("ord_owner2", ["trading:view"])
    spy = _make_user_with_perms("ord_spy2", ["trading:view"])
    cred = _make_credential(owner)
    api_client.force_authenticate(spy)
    resp = api_client.get(f"/api/trading/orders?credential_id={cred.id}")
    assert resp.status_code == 404


# ──────────────────────────────────────────────
# okx_ext unit tests (pure function level)
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_okx_ext_place_order_raises_on_error():
    """okx_ext.place_order raises RuntimeError when OKX code != '0'."""
    from core.trading import okx_ext
    user = User.objects.create_user("ext_err_user", password="pw")
    cred = _make_credential(user)

    mock_api = MagicMock()
    mock_api.place_order.return_value = {"code": "51000", "msg": "bad param", "data": []}

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        with pytest.raises(RuntimeError, match="51000"):
            okx_ext.place_order(
                cred, inst_type="SPOT", inst_id="BTC-USDT",
                side="buy", ord_type="market", sz="0.01",
            )


@pytest.mark.django_db
def test_okx_ext_get_balance_raises_on_error():
    """okx_ext.get_balance raises RuntimeError when OKX code != '0'."""
    from core.trading import okx_ext
    user = User.objects.create_user("bal_err_user", password="pw")
    cred = _make_credential(user)

    mock_api = MagicMock()
    mock_api.get_account_balance.return_value = {"code": "50001", "msg": "auth fail", "data": []}

    with patch("core.trading.okx_ext._account_api", return_value=mock_api):
        with pytest.raises(RuntimeError, match="50001"):
            okx_ext.get_balance(cred)
