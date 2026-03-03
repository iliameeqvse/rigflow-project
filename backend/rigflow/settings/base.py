from .base import *
import environ

env = environ.Env()

DEBUG = False

DATABASES = {
    "default": env.db("DATABASE_URL")
}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = "django-db"

# S3 storage — only if AWS keys are set
AWS_BUCKET = env("AWS_BUCKET_NAME", default="")
if AWS_BUCKET:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
else:
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

ALLOWED_HOSTS = ["*"]
SECRET_KEY = env("SECRET_KEY")