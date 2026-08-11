import pytest

from apps.exchanges.base import ExchangeAdapter
from apps.exchanges.factory import AdapterFactory, register_adapter
from apps.exchanges.types import Env


class _Dummy(ExchangeAdapter):
    def get_candles(self, *a, **k):
        return []

    def get_ticker(self, *a, **k):
        return None

    def get_balances(self):
        return []

    def get_positions(self):
        return []

    def place_order(self, req):
        return None

    def cancel_order(self, oid):
        return None


def test_factory_creates_registered_adapter():
    register_adapter("dummy", _Dummy)
    a = AdapterFactory.create("dummy", Env.SIM, credential=None)
    assert isinstance(a, ExchangeAdapter)
    assert a.env == Env.SIM


def test_factory_unknown_raises():
    with pytest.raises(KeyError):
        AdapterFactory.create("nope", Env.SIM, credential=None)


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        ExchangeAdapter(credential=None, env=Env.SIM)
