import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.engine import OKXEngine
from apps.trading.models import OrderState


@pytest.fixture
def auth(db, monkeypatch):
    # OKXEngine.place 不真连交易所:仅置为 LIVE 并保存(成交回填由 WS/REST 同步负责)
    def fake_place(self, order):
        order.state = OrderState.LIVE
        order.save()
        return order

    monkeypatch.setattr(OKXEngine, "place", fake_place)
    u = get_user_model().objects.create_user("p7", password="pass12345")
    c = APIClient()
    c.force_authenticate(u)
    return c, u


def test_idempotent_order(auth):
    c, u = auth
    body = {
        "env": "sim", "inst_type": "SPOT", "symbol": "BTC-USDT",
        "side": "buy", "ord_type": "market", "sz": "0.01", "client_order_id": "abc-123",
    }
    r1 = c.post("/api/trading/orders/place", body, format="json")
    assert r1.status_code == 201
    r2 = c.post("/api/trading/orders/place", body, format="json")
    # 同 client_order_id 返回原订单(200),不重复下单
    assert r2.status_code == 200
    assert r1.data["id"] == r2.data["id"]
    from apps.trading.models import Order
    assert Order.objects.filter(user=u, client_order_id="abc-123").count() == 1
