from django.urls import path

from . import views

urlpatterns = [
    path("backtests/run", views.run),
    path("backtests", views.list_backtests),
    path("backtests/<int:pk>", views.detail),
]
