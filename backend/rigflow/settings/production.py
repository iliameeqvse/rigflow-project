from .base import *
import environ


env = environ.Env()


DEBUG = False


# Database — reads from DATABASE_URL environment variable
DATABASES = {
    "default": env.db("DATABASE_URL"),
}


# Redis broker — reads from REDIS_URL environment variable
CELERY_BROKER_URL = env("REDIS_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = "django-db"


# S3 storage — only if AWS keys are set
AWS_BUCKET = env("AWS_BUCKET_NAME", default="")
if AWS_BUCKET:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"


ALLOWED_HOSTS = ["*"]


# Security
SECRET_KEY = env("SECRET_KEY")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")