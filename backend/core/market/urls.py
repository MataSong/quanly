from django.urls import path
from . import views

urlpatterns = [
    path("candles", views.candles_view, name="market-candles"),
    path("symbols", views.symbols_view, name="market-symbols"),
]
