from apps.exchanges.okx.adapter import OKXAdapter
from apps.exchanges.types import Candle, Env, Ticker


def test_flag_maps_from_env():
    assert OKXAdapter._flag_for(Env.SIM) == "1"
    assert OKXAdapter._flag_for(Env.LIVE) == "0"


def test_get_ticker_returns_standard(monkeypatch):
    a = OKXAdapter(credential=None, env=Env.SIM)
    monkeypatch.setattr(
        a,
        "_market",
        type(
            "M",
            (),
            {
                "get_ticker": lambda self, instId: {
                    "data": [{"last": "42000.5", "ts": "1700000000000"}]
                }
            },
        )(),
    )
    t = a.get_ticker("BTC-USDT")
    assert isinstance(t, Ticker)
    assert t.last == 42000.5
    assert t.symbol == "BTC-USDT"


def test_registered_in_factory():
    from apps.exchanges.factory import AdapterFactory

    a = AdapterFactory.create("okx", Env.SIM, credential=None)
    assert isinstance(a, OKXAdapter)


def test_get_candles_returns_ascending_standard(monkeypatch):
    a = OKXAdapter(credential=None, env=Env.SIM)
    # OKX 返回时间倒序:[ts, o, h, l, c, vol, volCcy, ...]
    monkeypatch.setattr(
        a,
        "_market",
        type(
            "M",
            (),
            {
                "get_candlesticks": lambda self, instId, bar, limit: {
                    "data": [
                        ["1700000060000", "101", "102", "100", "101.5", "10", "x"],
                        ["1700000000000", "100", "101", "99", "100.5", "12", "x"],
                    ]
                }
            },
        )(),
    )
    candles = a.get_candles("BTC-USDT", "1m", limit=2)
    assert len(candles) == 2
    assert all(isinstance(c, Candle) for c in candles)
    # 升序:先旧后新
    assert candles[0].ts == 1700000000000
    assert candles[1].ts == 1700000060000
    assert candles[0].open == 100.0 and candles[0].close == 100.5
