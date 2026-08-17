"""URL configuration for the backtest app."""
from django.urls import path

from core.backtest.views import BacktestDetailView, BacktestListCreateView

urlpatterns = [
    path("backtests", BacktestListCreateView.as_view(), name="backtest-list-create"),
    path("backtests/<int:pk>", BacktestDetailView.as_view(), name="backtest-detail"),
]
