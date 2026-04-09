from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # ── App APIs ───────────────────────────────────────────────────────────
    path("api/v1/",      include("apps.rigging.urls")),
    path("api/v1/auth/", include("apps.users.urls")),
    path("api/v1/",      include("apps.posts.urls")),    # posts

    # ── JWT ────────────────────────────────────────────────────────────────
    path("api/v1/auth/token/",         TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(),    name="token_refresh"),
    path("api/v1/auth/token/verify/",  TokenVerifyView.as_view(),     name="token_verify"),

    # ── Swagger ────────────────────────────────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(),                          name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"),     name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),       name="redoc"),
]

if getattr(settings, "MEDIA_ROOT", None):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)