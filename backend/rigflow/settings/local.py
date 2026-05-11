import os
import shutil
from pathlib import Path
from .base import *

# Load backend/.env into os.environ if the file exists.
# django-environ is already in requirements; this lets you drop
# ANTHROPIC_API_KEY / LANDMARK_VISION_PROVIDER there without
# having to export them in every terminal session.
_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    import environ
    environ.Env.read_env(_env_file)


DEBUG = True

# Prefer BLENDER_PATH if set; otherwise look up `blender` on PATH;
# otherwise fall back to a tarball install at /usr/local/bin/blender.
# This handles WSL/Linux out-of-the-box and still respects an explicit
# override (e.g. a Windows path or a versioned tarball install).
BLENDER_EXECUTABLE = (
    os.environ.get("BLENDER_PATH")
    or shutil.which("blender")
    or "/usr/local/bin/blender"
)


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


# Relax all throttle rates for local development. The production caps
# (rig_upload=10/hour, user=10/min, etc.) are trivial to hit while
# iterating on landmark placement / animations / re-rigs and produce
# confusing 429 errors mid-debug. Throttle counters live in the cache,
# which is local-memory by default — they reset whenever runserver
# restarts, so this is purely a dev-quality-of-life change.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        "anon":             "10000/minute",
        "user":             "10000/minute",
        "anon_upload":      "10000/minute",
        "user_upload":      "10000/hour",
        "rig_upload":       "10000/hour",
        "animation_upload": "10000/hour",
        "rig_list":         "10000/minute",
        "animation_list":   "10000/minute",
        "posts_list":       "10000/minute",
        "posts_create":     "10000/minute",
        "post_burst":       "10000/10seconds",
        "strict_ip":        "10000/minute",
    },
}