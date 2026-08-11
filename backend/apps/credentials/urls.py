from rest_framework.routers import DefaultRouter

from .views import CredentialViewSet

router = DefaultRouter()
router.register("credentials", CredentialViewSet, basename="credential")

urlpatterns = router.urls
