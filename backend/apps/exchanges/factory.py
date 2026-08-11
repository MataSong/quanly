from .base import ExchangeAdapter
from .types import Env

_REGISTRY: dict[str, type[ExchangeAdapter]] = {}


def register_adapter(name: str, cls: type[ExchangeAdapter]) -> None:
    _REGISTRY[name] = cls


class AdapterFactory:
    @staticmethod
    def create(exchange: str, env: Env, credential) -> ExchangeAdapter:
        return _REGISTRY[exchange](credential, env)
