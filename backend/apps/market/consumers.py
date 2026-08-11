import asyncio
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


class MarketConsumer(AsyncWebsocketConsumer):
    """前端连 /ws/market/{symbol}?bar=1m;直连 OKX 公共 WS 实时转发该 symbol 的
    K线 + Ticker,任意品种即时有数据、低延迟。不再依赖 collector 只推少数币。

    输出消息与 collector 一致:
      {"type":"candle","symbol","bar","ts","open","high","low","close","vol"}
      {"type":"ticker","symbol","last"}
    """

    async def connect(self):
        self.symbol = self.scope["url_route"]["kwargs"]["symbol"]
        qs = (self.scope.get("query_string") or b"").decode()
        self.bar = "1m"
        for part in qs.split("&"):
            if part.startswith("bar="):
                self.bar = part[4:] or "1m"
        await self.accept()
        self._closing = False
        self._task = asyncio.create_task(self._run_okx())

    async def _run_okx(self):
        from okx.websocket.WsPublicAsync import WsPublicAsync

        url = settings.OKX_PUBLIC_WS_SIM
        loop = asyncio.get_running_loop()
        bar_channel = "candle" + self.bar  # OKX 频道名如 candle1m

        def on_message(raw):
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                return
            arg = msg.get("arg", {})
            data = msg.get("data")
            if not data:
                return
            channel = arg.get("channel", "")
            symbol = arg.get("instId", "")
            if channel.startswith("candle"):
                row = data[0]  # [ts,o,h,l,c,vol,...]
                payload = json.dumps(
                    {
                        "type": "candle",
                        "symbol": symbol,
                        "bar": self.bar,
                        "ts": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "vol": float(row[5]),
                    }
                )
            elif channel == "tickers":
                d = data[0]
                payload = json.dumps(
                    {"type": "ticker", "symbol": symbol, "last": float(d["last"])}
                )
            else:
                return
            # on_message 在 OKX WS 自己的线程回调,跨线程安全地投递到本事件循环
            asyncio.run_coroutine_threadsafe(self.send(text_data=payload), loop)

        backoff = 1
        while not self._closing:
            try:
                ws = WsPublicAsync(url=url)
                self._ws = ws
                await ws.start()
                await ws.subscribe(
                    [
                        {"channel": bar_channel, "instId": self.symbol},
                        {"channel": "tickers", "instId": self.symbol},
                    ],
                    callback=on_message,
                )
                backoff = 1
                while not self._closing:
                    await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def disconnect(self, code):
        self._closing = True
        task = getattr(self, "_task", None)
        if task:
            task.cancel()
        ws = getattr(self, "_ws", None)
        if ws:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def receive(self, text_data=None, bytes_data=None):
        # 前端目前只订阅、不发消息
        pass
