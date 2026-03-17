from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnimationViewSet, CategoryListView

router = DefaultRouter()
router.register(r"animations", AnimationViewSet, basename="animation")

urlpatterns = [
    path("", include(router.urls)),
    path("animations/categories/", CategoryListView.as_view(), name="animation-categories"),
]