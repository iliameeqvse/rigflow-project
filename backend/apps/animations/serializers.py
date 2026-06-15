import json as json_mod
import struct

from django.utils.text import slugify
from rest_framework import serializers
from .models import Animation, AnimationCategory


def _extract_animation_metadata(file) -> tuple[int, float]:
    """Return (duration_frames, frame_rate) from a GLB or GLTF file.

    GLB stores a GLTF JSON chunk starting at byte 20. GLTF is plain JSON.
    The animation input accessor's `max[0]` is the clip duration in seconds
    (precomputed by the exporter; no binary parsing needed).
    Returns (0, 30.0) for FBX or on any parse error.
    """
    name = getattr(file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext not in ("glb", "gltf"):
        return 0, 30.0

    try:
        file.seek(0)
        raw = file.read()
        file.seek(0)

        if ext == "glb":
            # GLB header: magic(4) version(4) length(4) | JSON chunk: len(4) type(4) data
            if len(raw) < 20 or struct.unpack_from("<I", raw, 0)[0] != 0x46546C67:
                return 0, 30.0
            json_len = struct.unpack_from("<I", raw, 12)[0]
            gltf = json_mod.loads(raw[20:20 + json_len])
        else:
            gltf = json_mod.loads(raw)

        accessors = gltf.get("accessors", [])
        max_time = 0.0
        for anim in gltf.get("animations", []):
            for sampler in anim.get("samplers", []):
                idx = sampler.get("input")
                if idx is not None and idx < len(accessors):
                    acc_max = accessors[idx].get("max", [])
                    if acc_max:
                        max_time = max(max_time, float(acc_max[0]))

        if max_time <= 0:
            return 0, 30.0

        fps = 30.0
        return round(max_time * fps), fps

    except Exception:
        return 0, 30.0


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
            "id", "name", "slug", "description", "category",
            "gltf_file", "preview_gif", "duration_frames", "frame_rate",
            "is_looping", "is_public", "is_user_uploaded",
            "moderation_status", "tags", "like_count", "download_count",
            "created_at",
        ]
        read_only_fields = fields

    def _abs(self, path):
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request and path else path

    def get_gltf_file(self, obj):
        return self._abs(obj.gltf_file.url) if obj.gltf_file else None

    def get_preview_gif(self, obj):
        return self._abs(obj.preview_gif.url) if obj.preview_gif else None


class AnimationUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    # Plain CharField — no slug validation, empty string is fine
    category_slug = serializers.CharField(required=False, allow_blank=True, default="")
    # FormData sends "true"/"false" strings — normalise in validate_
    is_looping = serializers.CharField(required=False, default="false")
    # Comma-separated e.g. "walk,cycle,locomotion"
    tags = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_file(self, value):
        ext = (value.name or "").rsplit(".", 1)[-1].lower()
        if ext not in {"glb", "gltf", "fbx"}:
            raise serializers.ValidationError(
                f"Unsupported format: .{ext}. Upload GLB, GLTF, or FBX."
            )
        if value.size > 100 * 1024 * 1024:
            raise serializers.ValidationError("File exceeds 100 MB limit.")
        return value

    def validate_is_looping(self, value):
        return str(value).strip().lower() in ("true", "1", "yes")

    def validate_tags(self, value):
        if not value:
            return []
        return [t.strip().lower() for t in value.split(",") if t.strip()]

    def create(self, validated_data):
        name = validated_data["name"].strip()[:255]

        category = None
        cat_slug = validated_data.get("category_slug", "")
        if cat_slug:
            category = AnimationCategory.objects.filter(slug=cat_slug).first()

        # Build a unique slug — slugify + uniqueness suffix.
        base = slugify(name)[:270] or "anim"
        slug = base
        n = 0
        while Animation.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"

        request = self.context.get("request")
        uploader = None
        if request and request.user.is_authenticated:
            uploader = getattr(request.user, "profile", None)

        duration_frames, frame_rate = _extract_animation_metadata(validated_data["file"])

        return Animation.objects.create(
            name=name,
            slug=slug,
            description=validated_data.get("description", ""),
            category=category,
            gltf_file=validated_data["file"],
            duration_frames=duration_frames,
            frame_rate=frame_rate,
            is_looping=validated_data.get("is_looping", False),
            tags=validated_data.get("tags", []),
            uploaded_by=uploader,
            is_public=True,
            is_user_uploaded=True,
            moderation_status=Animation.MOD_APPROVED,
        )