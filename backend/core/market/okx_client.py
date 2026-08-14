"""OKX public market data client (no API key required).

Only connects to real OKX via python-okx.  No mock/fallback data.
OKX_FLAG env: "1" = demo/testnet, "0" = production (default "0" for public market data).
"""
import os
import logging
from typing import Any

logger = logging.getLogger("quanly.market")

_OKX_FLAG = int(os.environ.get("OKX_FLAG", "0"))


def _market_api():
    """Return a python-okx MarketData instance (public, no key needed)."""
    from okx import MarketData  # type: ignore[import]
    return MarketData.MarketAPI(
        api_key="",
        api_secret_key="",
        passphrase="",
        use_server_time=False,
        flag=str(_OKX_FLAG),
    )


def _public_api():
    """Return a python-okx PublicData instance (public, no key needed)."""
    from okx import PublicData  # type: ignore[import]
    return PublicData.PublicAPI(
        api_key="",
        api_secret_key="",
        passphrase="",
        use_server_time=False,
        flag=str(_OKX_FLAG),
    )


def get_candles(symbol: str, bar: str = "1m", limit: int = 100) -> list[dict[str, Any]]:
    """Fetch historical candlestick data for a SPOT instrument.

    Returns a list of dicts with keys: ts, o, h, l, c, vol, volCcy.
    Raises on OKX error — callers should handle exceptions.
    """
    api = _market_api()
    resp = api.get_candlesticks(instId=symbol, bar=bar, limit=str(limit))
    if resp.get("code") != "0":
        msg = resp.get("msg", "unknown OKX error")
        raise RuntimeError(f"OKX get_candlesticks error: {msg}")

    raw: list[list[str]] = resp.get("data", [])
    candles = []
    for row in raw:
        # row layout: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        candles.append({
            "ts": int(row[0]),
            "o": row[1],
            "h": row[2],
            "l": row[3],
            "c": row[4],
            "vol": row[5],
            "volCcy": row[6],
        })
    # OKX returns newest-first; reverse to oldest-first for chart init
    candles.reverse()
    return candles


def get_history_candles(
    symbol: str, bar: str = "1m", after: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Fetch older historical candlestick data (pagination backward in time).

    Uses MarketData.get_history_candlesticks which returns data before the
    given ``after`` timestamp (milliseconds string).  OKX single-page limit
    is 100.  Returns the same structure as get_candles.
    """
    api = _market_api()
    kwargs: dict[str, str] = {
        "instId": symbol,
        "bar": bar,
        "limit": str(min(limit, 100)),
    }
    if after is not None:
        kwargs["after"] = str(after)
    resp = api.get_history_candlesticks(**kwargs)
    if resp.get("code") != "0":
        msg = resp.get("msg", "unknown OKX error")
        raise RuntimeError(f"OKX get_history_candlesticks error: {msg}")

    raw: list[list[str]] = resp.get("data", [])
    candles = []
    for row in raw:
        candles.append({
            "ts": int(row[0]),
            "o": row[1],
            "h": row[2],
            "l": row[3],
            "c": row[4],
            "vol": row[5],
            "volCcy": row[6],
        })
    # OKX returns newest-first; reverse to oldest-first
    candles.reverse()
    return candles



def get_spot_symbols() -> list[dict[str, Any]]:
    """Fetch all SPOT instrument definitions from OKX.

    Returns a list of dicts with keys: instId, baseCcy, quoteCcy, state.
    Raises on OKX error.
    """
    api = _public_api()
    resp = api.get_instruments(instType="SPOT")
    if resp.get("code") != "0":
        msg = resp.get("msg", "unknown OKX error")
        raise RuntimeError(f"OKX get_instruments error: {msg}")

    raw: list[dict] = resp.get("data", [])
    return [
        {
            "instId": item["instId"],
            "baseCcy": item.get("baseCcy", ""),
            "quoteCcy": item.get("quoteCcy", ""),
            "state": item.get("state", ""),
        }
        for item in raw
        if item.get("state") == "live"
    ]
