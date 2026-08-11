import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.credentials.models import ExchangeCredential
from apps.finance import views as finance_views


class _FakeAdapter:
    def get_savings_products(self):
        return [{"ccy": "USDT", "apr": 0.03}, {"ccy": "BTC", "apr": 0.02}]

    def subscribe_savings(self, ccy, amount):
        return {"ok": True}

    def redeem_savings(self, ccy, amount):
        return {"ok": True}

    def transfer(self, ccy, amount, **kw):
        return {"ok": True}


@pytest.fixture
def auth(db, monkeypatch):
    u = get_user_model().objects.create_user("fin", password="pass12345")
    ExchangeCredential.objects.create(
        user=u, env="sim", exchange="okx",
        api_key="k", secret_enc="s", passphrase_enc="p",
    )
    monkeypatch.setattr(finance_views, "_okx", lambda user, env: _FakeAdapter())
    c = APIClient()
    c.force_authenticate(u)
    return c, u


def test_products_from_okx(auth):
    c, u = auth
    r = c.get("/api/finance/products?env=sim")
    assert r.status_code == 200
    ccys = {p["ccy"] for p in r.data}
    assert "USDT" in ccys and "BTC" in ccys


def test_subscribe_and_redeem(auth):
    c, u = auth
    prod = c.get("/api/finance/products?env=sim&category=earn").data
    flexible = next(p for p in prod if p["category"] == "flexible")
    r = c.post(
        "/api/finance/subscribe",
        {"env": "sim", "product_id": flexible["id"], "amount": "1000"},
        format="json",
    )
    assert r.status_code == 201
    hid = r.data["id"]
    h = c.get("/api/finance/holdings?env=sim").data
    assert len(h) == 1 and h[0]["principal"] == 1000.0
    r = c.post(f"/api/finance/redeem/{hid}", {"env": "sim"}, format="json")
    assert r.status_code == 200
    assert len(c.get("/api/finance/holdings?env=sim").data) == 0


def test_subscribe_requires_credential(db, monkeypatch):
    u = get_user_model().objects.create_user("nocred", password="pass12345")
    monkeypatch.setattr(finance_views, "_okx", lambda user, env: None)
    c = APIClient()
    c.force_authenticate(u)
    from apps.finance.models import FinanceProduct
    p = FinanceProduct.objects.create(name="USDT 活期", category="flexible", ccy="USDT", apr="0.03")
    r = c.post(
        "/api/finance/subscribe",
        {"env": "sim", "product_id": p.id, "amount": "10"},
        format="json",
    )
    assert r.status_code == 400


def test_transfer(auth):
    c, u = auth
    r = c.post(
        "/api/finance/transfer",
        {"env": "sim", "ccy": "USDT", "amount": "500", "from_acct": "trading", "to_acct": "funding"},
        format="json",
    )
    assert r.status_code == 201
    assert len(c.get("/api/finance/transfers?env=sim").data) == 1
