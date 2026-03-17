from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.rigging.urls")),
    path("api/v1/", include("apps.animations.urls")),   # ← new
    path("api/v1/auth/", include("apps.users.urls")),
]

if getattr(settings, "MEDIA_ROOT", None):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)