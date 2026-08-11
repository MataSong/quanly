import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


class StrategyLogConsumer(AsyncWebsocketConsumer):
    """前端连 /ws/strategy/{run_id};订阅该运行的日志频道并转发。"""

    async def connect(self):
        self.run_id = self.scope["url_route"]["kwargs"]["run_id"]
        await self.accept()
        self._redis = aioredis.from_url(settings.REDIS_URL)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(f"strategy:{self.run_id}")
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
