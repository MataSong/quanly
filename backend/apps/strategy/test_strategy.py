import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.strategy import runner_api
from apps.strategy.models import Strategy, StrategyRun
from apps.trading.models import Order


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("strat", password="pass12345")


def test_builtins_seeded_on_list(user):
    c = APIClient()
    c.force_authenticate(user)
    r = c.get("/api/strategies/")
    assert r.status_code == 200
    names = [s["name"] for s in r.data]
    assert any("MA" in n or "均线" in n for n in names)
    assert any("Grid" in n or "网格" in n for n in names)


def test_strategy_api_order_via_run_token(user, monkeypatch):
    from apps.trading.engine import OKXEngine
    from apps.trading.models import OrderState

    def fake_place(self, order):
        order.state = OrderState.LIVE
        order.save()
        return order

    monkeypatch.setattr(OKXEngine, "place", fake_place)
    monkeypatch.setattr(runner_api, "get_last_price", lambda s: 50000.0)
    strat = Strategy.objects.create(user=user, name="t", source="x")
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT",
        status=StrategyRun.Status.RUNNING,
    )
    c = APIClient()  # 无 JWT,用 run_token
    # 用错 token 被拒
    r = c.post("/api/strategy-api/order", {"side": "buy", "sz": "0.01"},
               format="json", HTTP_X_RUN_TOKEN="wrong")
    assert r.status_code == 403
    # 正确 token 下单成功(状态回填由 WS/REST 同步负责)
    r = c.post("/api/strategy-api/order", {"side": "buy", "sz": "0.01"},
               format="json", HTTP_X_RUN_TOKEN=run.run_token)
    assert r.status_code == 201
    # 订单归属该 run 的 user+env
    o = Order.objects.get(id=r.data["id"])
    assert o.user_id == user.id and o.env == "sim"


def test_strategy_api_market(user, monkeypatch):
    monkeypatch.setattr(runner_api, "get_last_price", lambda s: 12345.0)
    strat = Strategy.objects.create(user=user, name="t", source="x")
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT",
        status=StrategyRun.Status.RUNNING,
    )
    c = APIClient()
    r = c.get("/api/strategy-api/market?symbol=BTC-USDT", HTTP_X_RUN_TOKEN=run.run_token)
    assert r.status_code == 200 and r.data["price"] == 12345.0
