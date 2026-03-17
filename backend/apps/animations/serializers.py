from rest_framework import serializers
from .models import Animation, AnimationCategory


class AnimationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AnimationCategory
        fields = ["id", "name", "slug", "icon"]


class AnimationSerializer(serializers.ModelSerializer):
    category = AnimationCategorySerializer(read_only=True)
    gltf_file = serializers.SerializerMethodField()
    preview_gif = serializers.SerializerMethodField()

    class Meta:
        model = Animation
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "gltf_file",
            "preview_gif",
            "duration_frames",
            "frame_rate",
            "is_looping",
            "tags",
            "is_public",
            "is_user_uploaded",
            "moderation_status",
            "like_count",
            "download_count",
            "created_at",
        ]
        read_only_fields = fields

    def _abs(self, path):
        request = self.context.get("request")
        if request and path:
            return request.build_absolute_uri(path)
        return path

    def get_gltf_file(self, obj):
        return self._abs(obj.gltf_file.url) if obj.gltf_file else None

    def get_preview_gif(self, obj):
        return self._abs(obj.preview_gif.url) if obj.preview_gif else None


class AnimationUploadSerializer(serializers.Serializer):
    """Write-only serializer used when a user POSTs a new animation."""
    file = serializers.FileField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    category_slug = serializers.SlugField(required=False, allow_blank=True, default="")
    is_looping = serializers.BooleanField(required=False, default=False)
    is_public = serializers.BooleanField(required=False, default=False)
    # Comma-separated tags e.g. "walk,locomotion,cycle"
    tags = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_file(self, value):
        ext = (value.name or "").rsplit(".", 1)[-1].lower()
        if ext not in {"glb", "gltf", "fbx"}:
            raise serializers.ValidationError(
                f"Unsupported format: .{ext}. Upload GLB, GLTF, or FBX."
            )
        max_mb = 100
        if value.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(f"File exceeds {max_mb} MB limit.")
        return value

    def validate_tags(self, value):
        """Turn 'walk, locomotion , cycle' → ['walk', 'locomotion', 'cycle']."""
        if not value:
            return []
        return [t.strip().lower() for t in value.split(",") if t.strip()]