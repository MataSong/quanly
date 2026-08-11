from django.urls import path

from . import sync_views, views

urlpatterns = [
    path("assets/summary", views.summary),
    path("assets/bills", views.bills),
    path("assets/sync", sync_views.full_sync),
]
