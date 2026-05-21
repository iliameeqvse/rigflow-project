"""
Backfill UserProfile rows for any User created before the post_save signal
was wired up (e.g. via `createsuperuser`, fixture loaders, or pre-fix
registrations that never got a profile).
"""
from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserProfile = apps.get_model("users", "UserProfile")
    for user in User.objects.filter(profile__isnull=True).iterator():
        UserProfile.objects.create(user=user)


def noop_reverse(apps, schema_editor):
    # Nothing to undo — leaving profiles in place is safe.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, noop_reverse),
    ]
