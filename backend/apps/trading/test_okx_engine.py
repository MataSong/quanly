"""OKXEngine / OKXAdapter 交易路径打桩测试(不真连 OKX)。

本机连不上 OKX,这里 monkeypatch OKX SDK 的 API 对象,验证:
1) get_engine 在 EXCHANGE_MODE=okx 时返回 OKXEngine
2) OKXEngine.place 通过 OKXAdapter 下单并回填 exchange_order_id
"""
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model

from apps.trading.models import InstType, Order, OrderSide, OrdType


def test_get_engine_okx():
    from apps.trading.engine import OKXEngine, get_engine

    assert isinstance(get_engine(), OKXEngine)


@pytest.mark.django_db
def test_okx_engine_place_maps_and_records(settings, monkeypatch):
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    from apps.credentials.models import ExchangeCredential
    from apps.credentials.crypto import encrypt
    from apps.exchanges.okx.adapter import OKXAdapter
    from apps.trading.engine import OKXEngine

    u = get_user_model().objects.create_user("okx", password="pass12345")
    cred = ExchangeCredential.objects.create(
        user=u, env="sim", label="d", api_key="AK",
        secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )
    order = Order.objects.create(
        user=u, env="sim", inst_type=InstType.SPOT, symbol="BTC-USDT",
        side=OrderSide.BUY, ord_type=OrdType.MARKET, sz="0.01", credential=cred,
    )

    # 打桩:OKXAdapter 构造不连网 + place_order 返回交易所订单号
    def fake_init(self, credential, env):
        self.credential = credential
        self.env = env

    monkeypatch.setattr(OKXAdapter, "__init__", fake_init)
    from apps.exchanges.types import Order as XOrder

    monkeypatch.setattr(
        OKXAdapter, "place_order",
        lambda self, req: XOrder(order_id="OKX-999", symbol=req.symbol, state="live"),
    )

    OKXEngine().place(order)
    order.refresh_from_db()
    assert order.exchange_order_id == "OKX-999"
    assert order.state == "live"


def test_get_engine_returns_okx_engine():
    from apps.trading.engine import OKXEngine, get_engine

    assert isinstance(get_engine(), OKXEngine)


def test_no_mock_engine_symbol():
    import apps.trading.engine as engine_mod

    assert not hasattr(engine_mod, "MockEngine")
    assert not hasattr(engine_mod, "MOCK_INITIAL_USDT")
