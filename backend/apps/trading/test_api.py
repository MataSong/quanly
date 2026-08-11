import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.engine import OKXEngine
from apps.trading.models import OrderState


@pytest.fixture
def auth_client(db, monkeypatch):
    # OKXEngine.place 不真连交易所:仅置为 LIVE 并保存
    def fake_place(self, order):
        order.state = OrderState.LIVE
        order.save()
        return order

    monkeypatch.setattr(OKXEngine, "place", fake_place)
    u = get_user_model().objects.create_user("trader", password="pass12345")
    c = APIClient()
    c.force_authenticate(u)
    return c, u


def test_env_isolation(auth_client):
    c, u = auth_client
    c.post(
        "/api/trading/orders/place",
        {"env": "sim", "inst_type": "SPOT", "symbol": "BTC-USDT",
         "side": "buy", "ord_type": "market", "sz": "0.1"},
        format="json",
    )
    # live 环境无任何订单
    r = c.get("/api/trading/orders?env=live")
    assert len(r.data) == 0
    r = c.get("/api/trading/orders?env=sim")
    assert len(r.data) == 1


def test_requires_auth():
    c = APIClient()
    r = c.get("/api/trading/orders")
    assert r.status_code == 401
