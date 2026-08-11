from django.urls import path

from . import views

urlpatterns = [
    path("market/symbols", views.symbols),
    path("market/<str:symbol>/instrument", views.instrument),
    path("market/<str:symbol>/candles", views.candles),
]
