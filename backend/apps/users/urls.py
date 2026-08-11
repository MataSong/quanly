from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import MeView, RegisterView

urlpatterns = [
    path("auth/register", RegisterView.as_view()),
    path("auth/login", TokenObtainPairView.as_view()),
    path("auth/refresh", TokenRefreshView.as_view()),
    path("auth/me", MeView.as_view()),
]
