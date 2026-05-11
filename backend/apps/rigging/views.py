import json
import math
import threading
import time as time_module
from django.contrib.auth import get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import RiggedModel
from .serializers import RiggedModelSerializer, RigStatusSerializer
from .tasks import _run_rig_pipeline, auto_rig_model, auto_rig_model_with_landmarks
from apps.throttles import (
    AnonUploadThrottle,
    RigUploadThrottle,
    RigListThrottle,
)

User = get_user_model()

# Match the frontend's hard-coded 100 MB cap (frontend/src/app/upload/page.tsx).
# The check happens before RiggedModel.objects.create() so an oversized upload
# doesn't leave a half-written file in MEDIA_ROOT.
MAX_RIG_UPLOAD_MB = 100
MAX_RIG_UPLOAD_BYTES = MAX_RIG_UPLOAD_MB * 1024 * 1024

LANDMARK_KEYS = (
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)


def _get_or_create_demo_profile():
    """Shared anonymous-only demo profile. Used only when the request
    is genuinely unauthenticated; the throttle layer rejects anonymous
    *uploads* before we get here, but anonymous detail/status reads can
    still hit code paths that need a profile."""
    from apps.users.models import UserProfile
    user, _ = User.objects.get_or_create(
        email="demo@rigflow.local",
        defaults={"username": "demo"},
    )
    profile, _ = UserProfile.objects.get_or_create(
        user=user, defaults={"plan": UserProfile.PLAN_FREE},
    )
    return profile


def _profile_for(user):
    """Authenticated users always upload to *their own* profile, never the
    demo one. The post_save signal creates a profile on user creation, but
    we get_or_create here too so legacy users (created before the signal
    was wired) don't fall through to demo."""
    from apps.users.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _glb_url(request, rig) -> str | None:
    if not rig.rigged_glb:
        return None
    base = request.build_absolute_uri(rig.rigged_glb.url)
    ts   = int(rig.updated_at.timestamp()) if rig.updated_at else int(time_module.time())
    return f"{base}?v={ts}"


def _validate_landmark_payload(value):
    if not isinstance(value, dict):
        return None, "Landmarks must be an object keyed by landmark name."

    missing = [key for key in LANDMARK_KEYS if key not in value]
    if missing:
        return None, f"Missing landmark(s): {', '.join(missing)}"

    cleaned = {}
    for key in LANDMARK_KEYS:
        point = value[key]
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            return None, f"Landmark '{key}' must be a 3-number array."
        coords = []
        for coord in point:
            try:
                number = float(coord)
            except (TypeError, ValueError):
                return None, f"Landmark '{key}' contains a non-numeric coordinate."
            if not math.isfinite(number):
                return None, f"Landmark '{key}' contains a non-finite coordinate."
            coords.append(number)
        cleaned[key] = coords
    return cleaned, None


@method_decorator(csrf_exempt, name="dispatch")
class RiggedModelViewSet(ModelViewSet):
    queryset           = RiggedModel.objects.all()
    serializer_class   = RiggedModelSerializer
    lookup_field       = "id"
    lookup_value_regex = r"[0-9a-f-]+"
    http_method_names  = ["get", "post", "head", "options"]

    def get_permissions(self):
        # Status polling AND detail read are public so the editor page can
        # surface bone_mapping / rig_log without 404'ing on rigs that were
        # created via the anonymous demo-profile fallback in `create()`.
        if self.action in ("status_action", "retrieve", "landmarks"):
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_authenticators(self):
        # AllowAny is not enough on its own: DRF runs authentication first,
        # and JWTAuthentication raises 401 on a stale/invalid token *before*
        # the permission check. That breaks the editor's status polling for
        # any visitor whose localStorage holds a token for a deleted user
        # (e.g. after a DB wipe). Skip authentication entirely on public
        # actions so a bad header is treated like no header.
        # NOTE: self.action isn't set yet at this point (it's assigned by
        # initialize_request *after* this runs), so we resolve via action_map.
        method = self.request.method.lower() if getattr(self, "request", None) else None
        action = (getattr(self, "action_map", None) or {}).get(method)
        if action in ("status_action", "retrieve", "landmarks"):
            return []
        return super().get_authenticators()

    def get_throttles(self):
        """
        Per-action throttle selection:
          list / retrieve  → RigListThrottle   (read rate)
          create           → AnonUploadThrottle + RigUploadThrottle (upload rate)
          rerig / rerig-landmarks → RigUploadThrottle (same as create — triggers Blender)
          status polling   → no throttle (lightweight DB read)
        """
        if self.action == "create":
            return [AnonUploadThrottle(), RigUploadThrottle()]
        if self.action in ("rerig", "rerig_landmarks"):
            return [RigUploadThrottle()]
        if self.action == "status_action":
            return []
        return [RigListThrottle()]

    def get_queryset(self):
        qs = super().get_queryset()
        # Public actions skip the per-user filter so demo-profile rigs and
        # rigs uploaded under a different auth state remain readable.
        if self.action in ("status_action", "retrieve", "landmarks"):
            return qs
        if self.request.user.is_authenticated:
            return qs.filter(user=_profile_for(self.request.user))
        return qs.none()

    @extend_schema(
        summary="Upload a 3D model for auto-rigging",
        description=(
            "Upload FBX / GLB / OBJ / GLTF. Blender runs synchronously and "
            "returns the rigged GLB.\n\n"
            "**Throttle:** authenticated users only, max **10 uploads / hour**.\n"
            "Anonymous users receive 429 immediately."
        ),
        responses={
            201: RiggedModelSerializer,
            400: OpenApiResponse(description="Missing file or unsupported format"),
            401: OpenApiResponse(description="Authentication required"),
            429: OpenApiResponse(description="Upload limit reached (10/hour)"),
        },
        tags=["Rigging"],
    )
    def create(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        name = request.data.get("name", "Untitled")
        if not file:
            return Response({"error": "Missing 'file'."}, status=status.HTTP_400_BAD_REQUEST)
        ext = (file.name or "").split(".")[-1].lower()
        if ext not in {"fbx", "glb", "gltf", "obj"}:
            return Response({"error": f"Unsupported format: .{ext}."}, status=status.HTTP_400_BAD_REQUEST)
        if file.size and file.size > MAX_RIG_UPLOAD_BYTES:
            mb = file.size / (1024 * 1024)
            return Response(
                {"error": f"File too large ({mb:.1f} MB). Maximum is {MAX_RIG_UPLOAD_MB} MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Manual preview-space Euler rotation in degrees. Form fields arrive
        # as strings; tolerate junk (default 0).
        def parse_rotation(name):
            try:
                return float(request.data.get(name, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        rotation_x = parse_rotation("rotation_x")
        rotation_y = parse_rotation("rotation_y")
        rotation_z = parse_rotation("rotation_z")
        rotation_qx = parse_rotation("rotation_qx")
        rotation_qy = parse_rotation("rotation_qy")
        rotation_qz = parse_rotation("rotation_qz")
        rotation_qw = parse_rotation("rotation_qw")

        if self.request.user.is_authenticated:
            profile = _profile_for(self.request.user)
        else:
            profile = _get_or_create_demo_profile()

        rig = RiggedModel.objects.create(
            user=profile, name=name[:255],
            original_file=file, original_format=ext,
            file_size_mb=round(file.size / (1024 * 1024), 2),
            status=RiggedModel.STATUS_PENDING,
        )
        extra = None
        if any(abs(v) > 0.5 for v in (rotation_x, rotation_y, rotation_z)):
            extra = [
                "--initial-rotation-x", str(rotation_x),
                "--initial-rotation-y", str(rotation_y),
                "--initial-rotation-z", str(rotation_z),
            ]
            if abs(rotation_qw) > 1e-6 or any(abs(v) > 1e-6 for v in (rotation_qx, rotation_qy, rotation_qz)):
                extra.extend([
                    "--initial-rotation-qx", str(rotation_qx),
                    "--initial-rotation-qy", str(rotation_qy),
                    "--initial-rotation-qz", str(rotation_qz),
                    "--initial-rotation-qw", str(rotation_qw),
                ])
        auto_rig_model.delay(str(rig.id), extra_args=extra)
        return Response(self.get_serializer(rig).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Poll rig processing status",
        description="Lightweight status check — not throttled.",
        responses={200: RigStatusSerializer},
        tags=["Rigging"],
    )
    @action(detail=True, methods=["get"], url_path="status")
    def status_action(self, request, id=None):
        try:
            rig = RiggedModel.objects.get(id=id)
        except RiggedModel.DoesNotExist:
            return Response({"error": "Rig not found."}, status=status.HTTP_404_NOT_FOUND)

        progress = {"step": "Processing...", "pct": 50}
        if rig.status == RiggedModel.STATUS_PENDING:
            progress = {"step": "Waiting in queue...", "pct": 5}
        elif rig.status == RiggedModel.STATUS_PROCESSING:
            progress = {"step": "Auto-rigging with Blender...", "pct": 50}
        elif rig.status == RiggedModel.STATUS_DONE:
            progress = {"step": "Done", "pct": 100}
        elif rig.status == RiggedModel.STATUS_FAILED:
            progress = {"step": "Failed", "pct": 0}

        return Response(RigStatusSerializer({
            "rig_id":           rig.id,
            "status":           rig.status,
            "progress":         progress,
            "rigged_glb_url":   _glb_url(request, rig),
            "error_message":    rig.error_message or "",
            "detection_method": rig.detection_method or "",
        }).data)

    @extend_schema(
        summary="Re-rig a model (auto-detect)",
        description="Triggers Blender again on the original file.\n\n**Throttle:** 10/hour.",
        responses={200: RiggedModelSerializer, 429: OpenApiResponse(description="Rate limit")},
        tags=["Rigging"],
    )
    @action(detail=True, methods=["post"], url_path="rerig")
    def rerig(self, request, id=None):
        try:
            rig = RiggedModel.objects.get(id=id)
        except RiggedModel.DoesNotExist:
            return Response({"error": "Rig not found."}, status=status.HTTP_404_NOT_FOUND)

        # Don't delete the old rigged_glb up front — the pipeline saves the
        # new file with a suffixed name (Django storage auto-renames on
        # collision), so if the re-rig fails the old rig keeps serving.
        rig.status = RiggedModel.STATUS_PENDING
        rig.error_message = rig.rig_log = ""
        rig.bone_mapping = {}
        rig.processing_time_s = None
        rig.save()

        auto_rig_model.delay(str(rig.id))
        return Response(self.get_serializer(rig, context={"request": request}).data)

    @extend_schema(
        summary="Get the 14 detected landmarks for the rig editor",
        description=(
            "Returns 14 anatomical landmarks (chin, groin, L/R × shoulder, "
            "elbow, wrist, hip, knee, ankle) in three.js editor space. "
            "Populated when the rig was generated; if the rig predates the "
            "feature, returns AABB-default landmarks instead of 404."
        ),
    )
    @action(detail=True, methods=["get"], url_path="landmarks",
            permission_classes=[AllowAny], authentication_classes=[])
    def landmarks(self, request, id=None):
        rig = self.get_object()
        if rig.landmarks:
            return Response({"landmarks": rig.landmarks})
        from .legacy_landmarks import default_landmarks_for_rig
        return Response({"landmarks": default_landmarks_for_rig(rig)})

    @extend_schema(
        summary="Re-rig using landmark positions",
        description=(
            "Accepts 14 landmark world positions from the 3D editor and "
            "rebuilds the rig with precise bone placement.\n\n"
            "**Throttle:** 10/hour (same as upload — runs Blender).\n\n"
            "Returns 202 immediately; poll `/status/` for progress."
        ),
        responses={
            202: OpenApiResponse(description="Accepted — processing in background"),
            400: OpenApiResponse(description="Missing or incomplete landmarks"),
            429: OpenApiResponse(description="Rate limit"),
        },
        tags=["Rigging"],
    )
    @action(detail=True, methods=["post"], url_path="rerig-landmarks")
    def rerig_landmarks(self, request, id=None):
        try:
            rig = RiggedModel.objects.get(id=id)
        except RiggedModel.DoesNotExist:
            return Response({"error": "Rig not found."}, status=status.HTTP_404_NOT_FOUND)

        raw_landmarks = request.data.get("landmarks")
        if not raw_landmarks:
            return Response({"error": "Missing landmarks."}, status=status.HTTP_400_BAD_REQUEST)

        landmarks, validation_error = _validate_landmark_payload(raw_landmarks)
        if validation_error:
            return Response(
                {"error": validation_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Preserve the old rigged_glb — pipeline will save the new file with
        # a unique name, and if the new run fails, the viewer keeps the old
        # rig instead of getting a 404 on a dangling URL.
        rig.bone_corrections = {"landmarks": landmarks}
        rig.status = RiggedModel.STATUS_PENDING
        rig.error_message = rig.rig_log = ""
        rig.bone_mapping = {}
        rig.processing_time_s = None
        rig.save()

        auto_rig_model_with_landmarks.delay(str(rig.id), landmarks)

        return Response({"status": "pending", "rig_id": str(rig.id)}, status=status.HTTP_202_ACCEPTED)
