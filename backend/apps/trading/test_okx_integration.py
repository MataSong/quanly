"""真实 OKX 对接打桩测试(不真连):验证 adapter 新方法与 mode 分流逻辑。"""


def _stub_adapter(monkeypatch):
    from apps.exchanges.okx.adapter import OKXAdapter

    def fake_init(self, credential, env):
        self.credential = credential
        self.env = env

    monkeypatch.setattr(OKXAdapter, "__init__", fake_init)
    return OKXAdapter


def test_get_instruments_maps(monkeypatch):
    OKXAdapter = _stub_adapter(monkeypatch)
    a = OKXAdapter(None, None)
    a._public = type("P", (), {
        "get_instruments": lambda self, instType: {
            "data": [
                {"instId": "BTC-USDT", "state": "live"},
                {"instId": "ETH-USDT", "state": "live"},
                {"instId": "OLD-USDT", "state": "suspend"},
            ]
        }
    })()
    insts = a.get_instruments("SPOT")
    assert insts == ["BTC-USDT", "ETH-USDT"]  # 只保留 live
