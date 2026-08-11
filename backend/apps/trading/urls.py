from django.urls import path

from . import views

urlpatterns = [
    path("trading/credentials", views.list_credentials),
    path("trading/orders", views.list_orders),
    path("trading/orders/place", views.place_order),
    path("trading/orders/<int:pk>/cancel", views.cancel_order),
    path("trading/orders/<int:pk>/tpsl", views.set_tpsl),
    path("trading/positions", views.list_positions),
    path("trading/positions/<int:pk>/close", views.close_position),
    path("trading/balances", views.list_balances),
    path("trading/trades", views.list_trades),
    path("trading/reconcile", views.reconcile_view),
]
