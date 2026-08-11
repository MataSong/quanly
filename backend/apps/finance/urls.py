from django.urls import path

from . import views

urlpatterns = [
    path("finance/products", views.products),
    path("finance/holdings", views.holdings),
    path("finance/subscribe", views.subscribe),
    path("finance/redeem/<int:pk>", views.redeem),
    path("finance/transfer", views.transfer),
    path("finance/transfers", views.transfers),
]
