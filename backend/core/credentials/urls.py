from rest_framework.routers import DefaultRouter

from core.credentials.views import CredentialViewSet

router = DefaultRouter()
router.register("", CredentialViewSet, basename="credential")

urlpatterns = router.urls
