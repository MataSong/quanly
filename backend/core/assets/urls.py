from django.urls import path

from .views import AssetsSummaryView

urlpatterns = [
    path("summary", AssetsSummaryView.as_view()),
]
