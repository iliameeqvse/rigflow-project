from django.contrib import admin

from .models import RiggedModel


@admin.register(RiggedModel)
class RiggedModelAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "user", "status", "detection_method",
        "detected_pose", "pose_confidence", "created_at",
    )
    list_filter = ("status", "detection_method", "detected_pose", "original_format", "created_at")
    search_fields = ("id", "name", "user__user__email")
    readonly_fields = (
        "id", "celery_task_id", "processing_time_s",
        "vertex_count", "rig_log", "created_at", "updated_at",
        "bone_mapping", "landmarks", "bone_corrections",
        "pose_angle_deg", "pose_confidence",
        "detection_method", "vision_response_raw",
    )
    ordering = ("-created_at",)
