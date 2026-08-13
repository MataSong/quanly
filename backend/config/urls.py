from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
]

# --- core app routes (apps implemented in subsequent tasks) ---
# Each include is guarded so manage.py check/migrate pass before the apps exist.
try:
    urlpatterns += [path("api/auth/", include("core.auth.urls"))]
except Exception:
    pass

try:
    urlpatterns += [path("api/accounts/", include("core.accounts.urls"))]
except Exception:
    pass

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# SPA catch-all — serve index.html for any non-API/non-admin route when frontend is built.
if (settings.BASE_DIR / "frontend_dist" / "index.html").exists():
    urlpatterns += [
        re_path(
            r"^(?!api/|media/|static/|admin/).*$",
            TemplateView.as_view(template_name="index.html"),
        ),
    ]
