import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.credentials.models import ExchangeCredential
from apps.finance import views as finance_views


class _FakeAdapter:
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


def test_transfer(auth):
    c, u = auth
    r = c.post(
        "/api/finance/transfer",
        {"env": "sim", "ccy": "USDT", "amount": "500", "from_acct": "trading", "to_acct": "funding"},
        format="json",
    )
    assert r.status_code == 201
    assert len(c.get("/api/finance/transfers?env=sim").data) == 1
