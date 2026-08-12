import json


def test_build_depth_payload():
    from apps.market.consumers import build_depth_payload
    row = {"bids": [["100.5", "2", "0", "1"]], "asks": [["100.6", "3", "0", "1"]]}
    out = json.loads(build_depth_payload("BTC-USDT", row))
    assert out["type"] == "depth"
    assert out["symbol"] == "BTC-USDT"
    assert out["bids"] == [[100.5, 2.0]]
    assert out["asks"] == [[100.6, 3.0]]
