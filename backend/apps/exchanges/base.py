from abc import ABC, abstractmethod

from .types import Capability, Env


class ExchangeAdapter(ABC):
    """通用交易所抽象接口。上层业务只依赖本类型,不感知具体交易所。"""

    capabilities: set = set()

    def __init__(self, credential, env: Env):
        self.credential = credential
        self.env = env

    def supports(self, cap: Capability) -> bool:
        return cap in self.capabilities

    @abstractmethod
    def get_candles(self, symbol, timeframe, limit=100):
        ...

    @abstractmethod
    def get_ticker(self, symbol):
        ...

    @abstractmethod
    def get_balances(self):
        ...

    @abstractmethod
    def get_positions(self):
        ...

    @abstractmethod
    def place_order(self, req):
        ...

    @abstractmethod
    def cancel_order(self, order_id):
        ...
