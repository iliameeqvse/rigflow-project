import json
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
from .tasks import _run_rig_pipeline
from apps.throttles import (
    AnonUploadThrottle,
    RigUploadThrottle,
    RigListThrottle,
)

User = get_user_model()


def _get_or_create_demo_profile():
    user, _ = User.objects.get_or_create(
        email="demo@rigflow.local",
        defaults={"username": "demo"},
    )
    if not hasattr(user, "profile"):
        from apps.users.models import UserProfile
        UserProfile.objects.create(user=user, plan=UserProfile.PLAN_FREE)
    return user.profile


def _glb_url(request, rig) -> str | None:
    if not rig.rigged_glb:
        return None
    base = request.build_absolute_uri(rig.rigged_glb.url)
    ts   = int(rig.updated_at.timestamp()) if rig.updated_at else int(time_module.time())
    return f"{base}?v={ts}"


@method_decorator(csrf_exempt, name="dispatch")
class RiggedModelViewSet(ModelViewSet):
    queryset           = RiggedModel.objects.all()
    serializer_class   = RiggedModelSerializer
    lookup_field       = "id"
    lookup_value_regex = r"[0-9a-f-]+"
    http_method_names  = ["get", "post", "head", "options"]

    def get_permissions(self):
        # Status polling is public so the frontend can check without a token
        if self.action == "status_action":
            return [AllowAny()]
        return [IsAuthenticated()]

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
        if self.request.user.is_authenticated and hasattr(self.request.user, "profile"):
            return qs.filter(user=self.request.user.profile)
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

        if self.request.user.is_authenticated and hasattr(self.request.user, "profile"):
            profile = self.request.user.profile
        else:
            profile = _get_or_create_demo_profile()

        rig = RiggedModel.objects.create(
            user=profile, name=name[:255],
            original_file=file, original_format=ext,
            file_size_mb=round(file.size / (1024 * 1024), 2),
            status=RiggedModel.STATUS_PENDING,
        )
        _run_rig_pipeline(str(rig.id))
        rig.refresh_from_db()
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
            "rig_id":         rig.id,
            "status":         rig.status,
            "progress":       progress,
            "rigged_glb_url": _glb_url(request, rig),
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

        if rig.rigged_glb:
            try: rig.rigged_glb.delete(save=False)
            except Exception: pass

        rig.status = RiggedModel.STATUS_PENDING
        rig.error_message = rig.rig_log = ""
        rig.bone_mapping = {}
        rig.processing_time_s = None
        rig.save()

        _run_rig_pipeline(str(rig.id))
        rig.refresh_from_db()
        return Response(self.get_serializer(rig, context={"request": request}).data)

    @extend_schema(
        summary="Re-rig using landmark positions",
        description=(
            "Accepts 6 landmark world positions from the 3D editor and "
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

        landmarks = request.data.get("landmarks")
        if not landmarks:
            return Response({"error": "Missing landmarks."}, status=status.HTTP_400_BAD_REQUEST)

        required = {"chin", "left_wrist", "right_wrist", "groin", "left_ankle", "right_ankle"}
        missing  = required - set(landmarks.keys())
        if missing:
            return Response(
                {"error": f"Missing landmark(s): {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if rig.rigged_glb:
            try: rig.rigged_glb.delete(save=False)
            except Exception: pass

        rig.bone_corrections = {"landmarks": landmarks}
        rig.status = RiggedModel.STATUS_PENDING
        rig.error_message = rig.rig_log = ""
        rig.bone_mapping = {}
        rig.processing_time_s = None
        rig.save()

        import threading
        threading.Thread(
            target=_run_rig_pipeline,
            args=(str(rig.id),),
            kwargs={"extra_args": ["--landmarks", json.dumps(landmarks)]},
            daemon=True,
        ).start()

        return Response({"status": "pending", "rig_id": str(rig.id)}, status=status.HTTP_202_ACCEPTED)