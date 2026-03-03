import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField


class AnimationCategory(models.Model):
    name  = models.CharField(max_length=64)
    slug  = models.SlugField(unique=True)
    icon  = models.CharField(max_length=8, default="🎭")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name_plural = "Animation Categories"

    def __str__(self):
        return self.name


class Animation(models.Model):
    MOD_PENDING  = "pending"
    MOD_APPROVED = "approved"
    MOD_REJECTED = "rejected"
    MOD_CHOICES = [
        (MOD_PENDING,  "Pending Review"),
        (MOD_APPROVED, "Approved"),
        (MOD_REJECTED, "Rejected"),
    ]

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=280)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        AnimationCategory, on_delete=models.SET_NULL,
        null=True, related_name="animations"
    )

    # The actual animation file (GLTF/GLB)
    gltf_file   = models.FileField(upload_to="animations/library/")
    preview_gif = models.ImageField(upload_to="animations/previews/", blank=True)
    thumbnail   = models.ImageField(upload_to="animations/thumbs/", blank=True)

    # Animation metadata
    duration_frames = models.PositiveIntegerField(default=0)
    frame_rate      = models.FloatField(default=30.0)
    is_looping      = models.BooleanField(default=False)
    tags            = models.JSONField(default=list, blank=True)  # ["walk","locomotion"]

    # Ownership
    uploaded_by      = models.ForeignKey(
        "users.UserProfile", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="animations"
    )
    is_public        = models.BooleanField(default=False)
    is_user_uploaded = models.BooleanField(default=False)

    # Moderation
    moderation_status = models.CharField(
        max_length=16, choices=MOD_CHOICES, default=MOD_PENDING
    )
    moderation_notes = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="moderated_animations"
    )

    # Stats
    download_count = models.PositiveIntegerField(default=0)
    like_count     = models.PositiveIntegerField(default=0)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["moderation_status", "is_public"]),
            models.Index(fields=["category", "is_public"]),
        ]

    def __str__(self):
        return f"{self.name} [{self.moderation_status}]"