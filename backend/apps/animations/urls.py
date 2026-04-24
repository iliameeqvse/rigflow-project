from django.urls import path

from .views import (
    AnimationListOrUploadView,
    AnimationCategoryListView,
)

urlpatterns = [
    path("animations/categories/", AnimationCategoryListView.as_view(),
         name="animation-categories"),
    path("animations/", AnimationListOrUploadView.as_view(),
         name="animation-list-or-upload"),
]
