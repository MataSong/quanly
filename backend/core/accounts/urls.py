from django.urls import path
from rest_framework.routers import DefaultRouter

from core.accounts.views import (
    PermissionsListView, RoleViewSet, UserViewSet,
)

router = DefaultRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("permissions/", PermissionsListView.as_view(), name="permissions"),
] + router.urls
