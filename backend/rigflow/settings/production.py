from .base import *
import environ

env = environ.Env()

DEBUG = False

# Database — reads from DATABASE_URL environment variable
DATABASES = {
    "default": env.db("DATABASE_URL")
}

# Redis broker — reads from REDIS_URL environment variable
CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = "django-db"

# Make sure ALL apps are listed including celery beat
INSTALLED_APPS += [
    "django_celery_beat",
    "django_celery_results",
]

# S3 storage — only if AWS keys are set
AWS_BUCKET = env("AWS_BUCKET_NAME", default="")
if AWS_BUCKET:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
else:
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

ALLOWED_HOSTS = ["*"]

# Security
SECRET_KEY = env("SECRET_KEY")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")