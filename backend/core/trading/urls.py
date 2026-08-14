from django.urls import path

from .views import BalanceView, CancelOrderView, OrdersView, PlaceOrderView, PositionsView

urlpatterns = [
    path("order", PlaceOrderView.as_view(), name="trading-place-order"),
    path("cancel", CancelOrderView.as_view(), name="trading-cancel-order"),
    path("orders", OrdersView.as_view(), name="trading-orders"),
    path("positions", PositionsView.as_view(), name="trading-positions"),
    path("balance", BalanceView.as_view(), name="trading-balance"),
]
