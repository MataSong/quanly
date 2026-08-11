from decimal import Decimal

from apps.trading import risk
from apps.trading.models import Position

D = Decimal


def test_liq_price_long_formula():
    pos = Position(symbol="BTC-USDT", pos_side="long", qty=D("1"),
                   avg_px=D("60000"), lever=10)
    lp = risk.liq_price(pos)
    # 60000 * (1 - 0.1 + 0.004 + 0.0005) = 60000 * 0.9045 = 54270
    assert abs(lp - D("54270")) < D("1")


def test_liq_price_short_formula():
    pos = Position(symbol="BTC-USDT", pos_side="short", qty=D("1"),
                   avg_px=D("60000"), lever=10)
    lp = risk.liq_price(pos)
    # 60000 * (1 + 0.1 - 0.004 - 0.0005) = 60000 * 1.0955 = 65730
    assert abs(lp - D("65730")) < D("1")
