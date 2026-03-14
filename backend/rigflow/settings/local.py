import os
from .base import *


DEBUG = True

# Steam Blender path (Windows). Override with BLENDER_PATH env var if needed.
BLENDER_STEAM = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
BLENDER_EXECUTABLE = os.environ.get("BLENDER_PATH", BLENDER_STEAM)


# SQLite for local dev without Docker. Use PostgreSQL in production (Docker).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR.parent / "db.sqlite3",
    }
}


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# Run Celery tasks synchronously in local dev so you don't need a worker
# running all the time.
CELERY_TASK_ALWAYS_EAGER = True