from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.credentials.urls")),
    path("api/", include("apps.market.urls")),
    path("api/", include("apps.trading.urls")),
    path("api/", include("apps.assets.urls")),
    path("api/", include("apps.strategy.urls")),
    path("api/", include("apps.backtest.urls")),
    path("api/", include("apps.finance.urls")),
]
