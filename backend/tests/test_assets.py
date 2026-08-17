"""Tests for P5-A: Assets backend — OKX net value / positions / bills aggregation.

Patch points (import style: from core.trading import okx_ext):
  core.assets.views.okx_ext.get_balance
  core.assets.views.okx_ext.get_positions
  core.assets.views.okx_ext.get_bills

All OKX calls are unittest.mock stubs — zero real external calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from django.contrib.auth.models import User

from core.accounts.models import Role, UserRole
from core.credentials.crypto import encrypt
from core.credentials.models import Credential


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username: str, perms: list[str] | None = None) -> User:
    user = User.objects.create_user(username, password="pw")
    if perms:
        role = Role.objects.create(name=f"role_{username}", permissions=perms)
        UserRole.objects.create(user=user, role=role)
    return user


def _make_credential(user: User, env: str = Credential.ENV_SIM, label: str = "test") -> Credential:
    return Credential.objects.create(
        user=user,
        env=env,
        label=label,
        api_key_enc=encrypt("dummy-api-key"),
        secret_enc=encrypt("dummy-secret"),
        passphrase_enc=encrypt("dummy-passphrase"),
    )


# ---------------------------------------------------------------------------
# Stub OKX responses
# ---------------------------------------------------------------------------

_STUB_BALANCE = [
    {
        "totalEq": "12345.67",
        "details": [
            {"ccy": "BTC",  "eq": "0.5",    "eqUsd": "10000.00", "availBal": "0.5",  "frozenBal": "0.0"},
            {"ccy": "USDT", "eq": "2345.67", "eqUsd": "2345.67",  "availBal": "2000", "frozenBal": "345.67"},
            {"ccy": "ETH",  "eq": "0.0",     "eqUsd": "0.0",      "availBal": "0.0",  "frozenBal": "0.0"},
            {"ccy": "OKB",  "eq": "1.0",     "eqUsd": "-0.01",    "availBal": "1.0",  "frozenBal": "0.0"},
        ],
    }
]

_STUB_POSITIONS = [
    {"instId": "BTC-USDT-SWAP", "posSide": "long", "pos": "1", "avgPx": "20000",
     "upl": "100", "uplRatio": "0.005", "notionalUsd": "20100", "lever": "10"},
]

_STUB_BILLS = [
    {"billId": "B001", "type": "2", "subType": "1", "ts": "1700000000000",
     "balChg": "-10.5", "bal": "2335.17", "ccy": "USDT"},
    {"billId": "B002", "type": "1", "subType": "1", "ts": "1700000100000",
     "balChg": "100.0", "bal": "2435.17", "ccy": "USDT"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_assets_summary_no_permission_returns_403(api_client):
    """GET /api/assets/summary without assets:view → 403."""
    user = _make_user("assets_no_perm", [])
    cred = _make_credential(user)
    api_client.force_authenticate(user)
    resp = api_client.get(f"/api/assets/summary?credential_id={cred.pk}")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_assets_summary_missing_credential_id_returns_400(api_client):
    """GET /api/assets/summary without credential_id → 400."""
    user = _make_user("assets_no_cid", ["assets:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/assets/summary")
    assert resp.status_code == 400
    assert "credential_id" in resp.data["detail"]


@pytest.mark.django_db
def test_assets_summary_other_user_credential_returns_404(api_client):
    """GET /api/assets/summary with another user's credential_id → 404."""
    alice = _make_user("assets_alice", ["assets:view"])
    bob   = _make_user("assets_bob",   [])
    bob_cred = _make_credential(bob, label="bob_cred")

    api_client.force_authenticate(alice)
    resp = api_client.get(f"/api/assets/summary?credential_id={bob_cred.pk}")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_assets_summary_success(api_client):
    """GET /api/assets/summary with valid credential + patched OKX → 200 with correct aggregation."""
    user = _make_user("assets_ok", ["assets:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    with patch("core.assets.views.okx_ext.get_balance", return_value=_STUB_BALANCE), \
         patch("core.assets.views.okx_ext.get_positions", return_value=_STUB_POSITIONS), \
         patch("core.assets.views.okx_ext.get_bills", return_value=_STUB_BILLS):
        resp = api_client.get(f"/api/assets/summary?credential_id={cred.pk}")

    assert resp.status_code == 200
    data = resp.data

    # net_value
    assert abs(data["net_value"] - 12345.67) < 1e-6

    # currencies: only eqUsd > 0 → BTC (10000) and USDT (2345.67); ETH and OKB excluded
    assert len(data["currencies"]) == 2
    ccys = [c["ccy"] for c in data["currencies"]]
    assert ccys[0] == "BTC"   # highest eqUsd first
    assert ccys[1] == "USDT"
    assert "ETH" not in ccys
    assert "OKB" not in ccys

    # descending order of eqUsd
    eq_usd_values = [float(c["eqUsd"]) for c in data["currencies"]]
    assert eq_usd_values == sorted(eq_usd_values, reverse=True)

    # positions and bills passed through unchanged
    assert data["positions"] == _STUB_POSITIONS
    assert data["bills"] == _STUB_BILLS


@pytest.mark.django_db
def test_assets_summary_okx_error_returns_502(api_client):
    """GET /api/assets/summary when get_balance raises RuntimeError → 502."""
    user = _make_user("assets_err", ["assets:view"])
    cred = _make_credential(user)
    api_client.force_authenticate(user)

    with patch(
        "core.assets.views.okx_ext.get_balance",
        side_effect=RuntimeError("OKX get_account_balance error [50011]: sign error"),
    ):
        resp = api_client.get(f"/api/assets/summary?credential_id={cred.pk}")

    assert resp.status_code == 502
    assert "OKX error" in resp.data["detail"]


@pytest.mark.django_db
def test_assets_summary_invalid_credential_id_returns_404(api_client):
    """GET /api/assets/summary with non-integer credential_id → 404."""
    user = _make_user("assets_badid", ["assets:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/assets/summary?credential_id=abc")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_assets_summary_nonexistent_credential_returns_404(api_client):
    """GET /api/assets/summary with valid int but non-existent credential → 404."""
    user = _make_user("assets_noexist", ["assets:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/assets/summary?credential_id=999999")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_assets_summary_unauthenticated_returns_401(api_client):
    """GET /api/assets/summary without authentication → 401."""
    resp = api_client.get("/api/assets/summary?credential_id=1")
    assert resp.status_code == 401
