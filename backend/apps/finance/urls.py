from django.urls import path

from . import views

urlpatterns = [
    path("finance/transfer", views.transfer),
    path("finance/transfers", views.transfers),
]
