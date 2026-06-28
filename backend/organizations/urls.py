from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AreaViewSet, SiteViewSet


router = DefaultRouter()
router.register("sites", SiteViewSet, basename="site")
router.register("areas", AreaViewSet, basename="area")

urlpatterns = [path("", include(router.urls))]
