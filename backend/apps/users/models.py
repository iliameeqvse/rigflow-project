import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user — we use email as the login field instead of username.
    Always define this before the first migration.
    """
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    # username is still required by AbstractUser internals
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email


class UserProfile(models.Model):
    """
    Extra data attached to each user.
    Separated from User so auth logic stays clean.
    """
    PLAN_FREE   = "free"
    PLAN_PRO    = "pro"
    PLAN_STUDIO = "studio"
    PLAN_CHOICES = [
        (PLAN_FREE,   "Free (500MB, 3 rigs)"),
        (PLAN_PRO,    "Pro — $15/mo (5GB, unlimited rigs)"),
        (PLAN_STUDIO, "Studio — $49/mo (50GB, team features)"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile"
    )
    stripe_customer_id = models.CharField(max_length=128, blank=True)
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, default=PLAN_FREE)
    storage_quota_mb = models.PositiveIntegerField(default=500)
    storage_used_mb  = models.FloatField(default=0.0)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def storage_remaining_mb(self):
        return self.storage_quota_mb - self.storage_used_mb

    def has_quota_for(self, file_size_bytes: int) -> bool:
        required_mb = file_size_bytes / (1024 * 1024)
        return self.storage_remaining_mb >= required_mb

    def __str__(self):
        return f"{self.user.email} [{self.plan}]"