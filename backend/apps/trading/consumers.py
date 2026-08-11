import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from urllib.parse import parse_qs


def _uid_from_token(token: str):
    """校验 JWT access token,返回其 user_id;无效返回 None。"""
    try:
        from rest_framework_simplejwt.tokens import AccessToken

        return str(AccessToken(token)["user_id"])
    except Exception:
        return None


class TradeConsumer(AsyncWebsocketConsumer):
    """前端连 /ws/trade/{user_id}/{env}?token=<access>;校验 token 与 url user_id 一致。"""

    async def connect(self):
        self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
        self.env = self.scope["url_route"]["kwargs"]["env"]
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        token = (qs.get("token") or [None])[0]
        if not token or _uid_from_token(token) != str(self.user_id):
            await self.close(code=4001)
            return
        await self.accept()
        self._redis = aioredis.from_url(settings.REDIS_URL)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(f"trade:{self.user_id}:{self.env}")
        self._task = __import__("asyncio").create_task(self._listen())

    async def _listen(self):
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                await self.send(text_data=data)

    async def disconnect(self, code):
        task = getattr(self, "_task", None)
        if task:
            task.cancel()
        pubsub = getattr(self, "_pubsub", None)
        if pubsub:
            await pubsub.close()
        client = getattr(self, "_redis", None)
        if client:
            await client.close()

    async def receive(self, text_data=None, bytes_data=None):
        pass
