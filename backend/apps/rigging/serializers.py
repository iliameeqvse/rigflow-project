from rest_framework import serializers
from .models import RiggedModel


class RiggedModelSerializer(serializers.ModelSerializer):
    rigged_glb_url = serializers.SerializerMethodField()

    class Meta:
        model = RiggedModel
        fields = [
            "id",
            "name",
            "status",
            "original_format",
            "rigged_glb_url",
            "bone_mapping",
            "file_size_mb",
            "error_message",
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


class RigStatusSerializer(serializers.Serializer):
    rig_id = serializers.UUIDField()
    status = serializers.CharField()
    progress = serializers.DictField(required=False)
    rigged_glb_url = serializers.URLField(allow_null=True)
    error_message = serializers.CharField(allow_blank=True, required=False)
