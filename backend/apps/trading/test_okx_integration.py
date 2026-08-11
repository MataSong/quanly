"""真实 OKX 对接打桩测试(不真连):验证 adapter 新方法与 mode 分流逻辑。"""
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model


def _stub_adapter(monkeypatch):
    from apps.exchanges.okx.adapter import OKXAdapter

    def fake_init(self, credential, env):
        self.credential = credential
        self.env = env

    monkeypatch.setattr(OKXAdapter, "__init__", fake_init)
    return OKXAdapter


def test_get_instruments_maps(monkeypatch):
    OKXAdapter = _stub_adapter(monkeypatch)
    a = OKXAdapter(None, None)
    a._public = type("P", (), {
        "get_instruments": lambda self, instType: {
            "data": [
                {"instId": "BTC-USDT", "state": "live"},
                {"instId": "ETH-USDT", "state": "live"},
                {"instId": "OLD-USDT", "state": "suspend"},
            ]
        }
    })()
    insts = a.get_instruments("SPOT")
    assert insts == ["BTC-USDT", "ETH-USDT"]  # 只保留 live


@pytest.mark.django_db
def test_finance_subscribe_okx_mode_calls_adapter(settings, monkeypatch):
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    from apps.credentials.crypto import encrypt
    from apps.credentials.models import ExchangeCredential
    from apps.finance import views as fv
    from rest_framework.test import APIClient

    u = get_user_model().objects.create_user("fx", password="pass12345")
    ExchangeCredential.objects.create(
        user=u, env="sim", label="d", api_key="AK",
        secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )
    called = {}

    class FakeAdapter:
        def get_savings_products(self):
            return [{"ccy": "USDT", "apr": 0.03}]

        def subscribe_savings(self, ccy, amount):
            called["sub"] = (ccy, float(amount))

    monkeypatch.setattr(fv, "_okx", lambda user, env: FakeAdapter())
    c = APIClient()
    c.force_authenticate(u)
    prod = c.get("/api/finance/products?env=sim&category=earn").data
    flexible = next(p for p in prod if p["category"] == "flexible")
    r = c.post("/api/finance/subscribe",
               {"env": "sim", "product_id": flexible["id"], "amount": "100"}, format="json")
    assert r.status_code == 201
    assert called.get("sub") == (flexible["ccy"], 100.0)
