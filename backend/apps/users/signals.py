"""
post_save signal that guarantees every User row has a matching UserProfile.

Wired up in `UsersConfig.ready()`. Without this, code paths that create users
outside of `RegisterSerializer` (Django admin, `createsuperuser`, third-party
SSO, fixture loaders) would leak users with no profile — and `rigging.views`
would silently fall back to the shared `demo@rigflow.local` profile when
that authenticated user uploaded a rig.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
