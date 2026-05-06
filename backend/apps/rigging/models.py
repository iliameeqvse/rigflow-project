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

    # Landmarks for rig fitting
    landmarks = models.JSONField(
        null=True, blank=True,
        help_text=(
            "14 anatomical landmarks (chin, groin, L/R × {shoulder, elbow, "
            "wrist, hip, knee, ankle}) in three.js editor space, used to fit "
            "the rigify metarig to non-human-proportion meshes. Populated by "
            "auto-rig; editable via /landmarks/ + /rerig-landmarks/."
        ),
    )

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

    # Pose classification from the Blender pipeline. Helps the user
    # understand whether their model is in a Rigify-friendly stance.
    POSE_T        = "t_pose"
    POSE_A        = "a_pose"
    POSE_ARMS_DOWN = "arms_down"
    POSE_UNCLEAR  = "unclear"
    POSE_CHOICES = [
        (POSE_T,        "T-pose"),
        (POSE_A,        "A-pose"),
        (POSE_ARMS_DOWN, "Arms down"),
        (POSE_UNCLEAR,  "Unclear"),
    ]
    detected_pose = models.CharField(
        max_length=16, choices=POSE_CHOICES, default=POSE_UNCLEAR, blank=True
    )
    pose_angle_deg = models.FloatField(null=True, blank=True)
    pose_confidence = models.FloatField(default=0.0)

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