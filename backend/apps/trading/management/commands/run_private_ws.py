"""OKX 私有 WebSocket 常驻采集器：订阅 account/positions/orders，回填本地表。"""
import asyncio
import json

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "运行 OKX 私有 WS 采集器（按用户凭证登录，实时回填余额/持仓/订单）"

    def add_arguments(self, parser):
        parser.add_argument("--env", choices=["sim", "live"], default="sim")

    def handle(self, *args, **opts):
        env = opts["env"]
        asyncio.run(self._run(env))

    async def _run(self, env):
        from apps.credentials.models import ExchangeCredential

        creds = await sync_to_async(
            lambda: list(ExchangeCredential.objects.filter(env=env, exchange="okx"))
        )()
        if not creds:
            self.stderr.write("无可用凭证，退出")
            return
        await asyncio.gather(*[self._run_one(c, env) for c in creds])

    async def _run_one(self, cred, env):
        from okx.websocket.WsPrivateAsync import WsPrivateAsync

        from apps.credentials.models import Env
        from apps.exchanges.factory import AdapterFactory
        from apps.trading import sync
        from django.db import close_old_connections

        x_env = Env.SIM if env == "sim" else Env.LIVE
        adapter = AdapterFactory.create("okx", x_env, cred)
        api_key, secret, passphrase = await sync_to_async(adapter._decrypt_keys)()
        url = settings.OKX_PRIVATE_WS_SIM if env == "sim" else settings.OKX_PRIVATE_WS_LIVE
        user = await sync_to_async(lambda: cred.user)()
        loop = asyncio.get_running_loop()

        def _handle_account(data):
            close_old_connections()
            sync.upsert_balances(user, env, adapter.parse_ws_balances(data))

        def _handle_positions(data):
            close_old_connections()
            sync.upsert_positions(user, env, adapter.parse_ws_positions(data))

        def _handle_orders(data):
            close_old_connections()
            for o in adapter.parse_ws_orders(data):
                sync.upsert_order(user, env, o)

        handlers = {
            "account": _handle_account,
            "positions": _handle_positions,
            "orders": _handle_orders,
        }

        def _dispatch(raw):
            """WsPrivateAsync 在事件循环里同步调用本回调，收到的是原始 JSON 字符串。
            按 arg.channel 分发，ORM 写入丢到线程池执行，避免 SynchronousOnlyOperation。"""
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                return
            if data.get("event") or not data.get("data"):
                return
            channel = (data.get("arg") or {}).get("channel")
            handler = handlers.get(channel)
            if handler:
                loop.run_in_executor(None, handler, data)

        backoff = 1
        while True:
            try:
                ws = WsPrivateAsync(
                    apiKey=api_key, passphrase=passphrase, secretKey=secret,
                    url=url, useServerTime=False,
                )
                await ws.start()
                # 单次订阅传入全部频道：WsPrivateAsync.subscribe 每次调用都会重新
                # login，重复登录同一连接会被 OKX 判为 4001，故必须一次订阅完。
                await ws.subscribe(
                    [
                        {"channel": "account"},
                        {"channel": "positions", "instType": "ANY"},
                        {"channel": "orders", "instType": "ANY"},
                    ],
                    _dispatch,
                )
                backoff = 1
                while True:
                    await asyncio.sleep(30)
            except Exception as e:  # noqa: BLE001
                self.stderr.write(f"WS 断线重连({backoff}s): {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
