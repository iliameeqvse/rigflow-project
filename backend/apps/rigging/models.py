import uuid
from django.db import models
from django.core.files import File


def rig_upload_path(instance, filename):
    # Files stored as: rigs/<user_id>/<rig_id>/filename
    return f"rigs/{instance.user.user.id}/{instance.id}/{filename}"


class RiggedModel(models.Model):
    STATUS_PENDING    = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE       = "done"
    STATUS_FAILED     = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING,    "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE,       "Done"),
        (STATUS_FAILED,     "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.UserProfile", on_delete=models.CASCADE, related_name="rigs"
    )
    name = models.CharField(max_length=255)

    # The original uploaded file (FBX, GLB, OBJ)
    original_file   = models.FileField(upload_to=rig_upload_path)
    original_format = models.CharField(max_length=8)   # "fbx", "glb", "obj"
    file_size_mb    = models.FloatField(default=0)

    # Output from Blender
    rigged_glb        = models.FileField(upload_to=rig_upload_path, blank=True)
    preview_thumbnail = models.ImageField(upload_to=rig_upload_path, blank=True)

    # Bone data — stored as JSON so it's queryable and editable
    bone_mapping    = models.JSONField(default=dict)   # Rigify→Mixamo name map
    bone_corrections = models.JSONField(default=dict)  # manual user tweaks

    # Stats
    vertex_count = models.IntegerField(default=0)
    bone_count   = models.IntegerField(default=0)

    # Task tracking
    status         = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    rig_log        = models.TextField(blank=True)     # Blender stdout
    error_message  = models.TextField(blank=True)
    processing_time_s = models.FloatField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.name} — {self.get_status_display()}"