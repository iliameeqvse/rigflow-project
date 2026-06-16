from rest_framework import serializers
from .models import RiggedModel, AnimationExport


class RiggedModelSerializer(serializers.ModelSerializer):
    rigged_glb_url = serializers.SerializerMethodField()
    landmark_debug_image_url = serializers.SerializerMethodField()

    class Meta:
        model = RiggedModel
        fields = [
            "id",
            "name",
            "status",
            "original_format",
            "rigged_glb_url",
            "landmark_debug_image_url",
            "bone_mapping",
            "file_size_mb",
            "error_message",
            "rig_log",
            "detected_pose",
            "pose_angle_deg",
            "pose_confidence",
            "detection_method",
            "used_existing_rig",
            "created_at",
        ]
        read_only_fields = fields

    def get_rigged_glb_url(self, obj) -> str | None:
        if obj.rigged_glb:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.rigged_glb.url)
            return obj.rigged_glb.url
        return None

    def get_landmark_debug_image_url(self, obj) -> str | None:
        if obj.landmark_debug_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.landmark_debug_image.url)
            return obj.landmark_debug_image.url
        return None


class AnimationExportSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = AnimationExport
        fields = [
            "id", "rig", "animation_ids", "export_format",
            "status", "download_url", "report", "error_message", "created_at",
        ]
        read_only_fields = fields

    def get_download_url(self, obj) -> str | None:
        if obj.output_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.output_file.url)
            return obj.output_file.url
        return None


class RigStatusSerializer(serializers.Serializer):
    rig_id = serializers.UUIDField()
    status = serializers.CharField()
    progress = serializers.DictField(required=False)
    rigged_glb_url = serializers.URLField(allow_null=True)
    error_message = serializers.CharField(allow_blank=True, required=False)
    detection_method = serializers.CharField(allow_blank=True, required=False)
