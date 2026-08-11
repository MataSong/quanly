from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Env(str, Enum):
    SIM = "sim"
    LIVE = "live"


class InstType(str, Enum):
    SPOT = "SPOT"
    MARGIN = "MARGIN"
    SWAP = "SWAP"
    FUTURES = "FUTURES"
    OPTION = "OPTION"


class Capability(str, Enum):
    SPOT = "spot"
    SWAP = "swap"
    FUTURES = "futures"
    OPTION = "option"
    EARN = "earn"
    LOAN = "loan"


@dataclass
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    vol: float


@dataclass
class Ticker:
    symbol: str
    last: float
    ts: int


@dataclass
class Balance:
    ccy: str
    total: float
    available: float
    frozen: float


@dataclass
class Position:
    symbol: str
    side: str
    qty: float
    avg_price: float
    upl: float
    liq_price: float = 0.0


@dataclass
class OrderRequest:
    symbol: str
    inst_type: InstType
    side: str
    ord_type: str
    sz: float
    px: Optional[float] = None
    td_mode: str = "cash"
    lever: Optional[int] = None
    pos_side: Optional[str] = None


@dataclass
class Order:
    order_id: str
    symbol: str
    state: str
    filled_sz: float = 0.0
    avg_px: float = 0.0
