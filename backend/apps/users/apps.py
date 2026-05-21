from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"  # ← must match the folder path

    def ready(self):
        # Side-effect import — registers the post_save handler that ensures
        # every User row has a UserProfile.
        from . import signals  # noqa: F401