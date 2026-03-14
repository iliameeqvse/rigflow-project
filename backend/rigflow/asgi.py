"""
ASGI config for rigflow project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application


# Default to local settings for development. In docker-compose and other
# deployment environments this is overridden via DJANGO_SETTINGS_MODULE.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rigflow.settings.local")

application = get_asgi_application()
