from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import register_view, login_view, me_view

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", me_view, name="me"),
]