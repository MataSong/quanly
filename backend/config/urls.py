from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
]

# --- core app routes ---
# 各 app 的 urls.py 骨架已就位(初期为空 urlpatterns),后续任务往里加路由。
# 不用 try/except 包裹:让 urls 里的导入/语法错误正常暴露,避免路由被静默吞掉难排查。
urlpatterns += [
    path("api/auth/", include("core.auth.urls")),
    path("api/accounts/", include("core.accounts.urls")),
]

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
