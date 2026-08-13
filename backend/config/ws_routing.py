from django.urls import re_path
from core.market.consumers import MarketConsumer

websocket_urlpatterns = [
    re_path(r"^ws/market/(?P<symbol>[\w\-]+)/$", MarketConsumer.as_asgi()),
]
