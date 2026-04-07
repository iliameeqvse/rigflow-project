from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")

DEBUG = False

ALLOWED_HOSTS: list[str] = []


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "channels",
    "django_celery_results",
    "django_celery_beat",
    "storages",
    "drf_spectacular",          # Swagger / OpenAPI
    # Project apps
    "apps.users",
    "apps.rigging",
    "apps.animations",
    "apps.projects",
    "apps.payments",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "rigflow.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


WSGI_APPLICATION = "rigflow.wsgi.application"
ASGI_APPLICATION  = "rigflow.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_I18N      = True
USE_TZ        = True


STATIC_URL  = "static/"
STATIC_ROOT = BASE_DIR.parent / "staticfiles"

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR.parent / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"


# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Wire drf-spectacular as the schema generator
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


# ── Simple JWT ────────────────────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":  True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ── drf-spectacular (Swagger) ─────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "RigFlow API",
    "DESCRIPTION": (
        "Auto-rigging platform API. "
        "Authenticate via /api/v1/auth/login/ to get a JWT, "
        "then click 'Authorize' and enter:  Bearer <your_token>"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,

    # Tell Swagger UI to show a Bearer token input box
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
}


# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True


# ── Celery / Redis ────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

CELERY_BROKER_URL    = REDIS_URL
CELERY_RESULT_BACKEND = "django-db"


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    },
}


DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

BLENDER_EXECUTABLE  = os.environ.get("BLENDER_PATH", "/usr/bin/blender")
BLENDER_SCRIPTS_DIR = BASE_DIR.parent / "scripts"