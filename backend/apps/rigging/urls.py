from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RiggedModelViewSet

router = DefaultRouter()
router.register(r"rigs", RiggedModelViewSet, basename="rig")

urlpatterns = [
    path("", include(router.urls)),
]
