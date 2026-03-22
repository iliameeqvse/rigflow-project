import json
from django.contrib.auth import get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import RiggedModel
from .serializers import RiggedModelSerializer, RigStatusSerializer
from .tasks import _run_rig_pipeline

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


@method_decorator(csrf_exempt, name="dispatch")
class RiggedModelViewSet(ModelViewSet):
    queryset = RiggedModel.objects.all()
    serializer_class = RiggedModelSerializer
    permission_classes = [AllowAny]
    lookup_field = "id"
    lookup_value_regex = r"[0-9a-f-]+"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_authenticated and hasattr(self.request.user, "profile"):
            return qs.filter(user=self.request.user.profile)
        return qs.none()

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
        # Run synchronously in local dev (CELERY_TASK_ALWAYS_EAGER=True)
        _run_rig_pipeline(str(rig.id))
        rig.refresh_from_db()
        return Response(self.get_serializer(rig).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="status")
    def status_action(self, request, id=None):
        try:
            rig = RiggedModel.objects.get(id=id)
        except RiggedModel.DoesNotExist:
            return Response({"error": "Rig not found."}, status=status.HTTP_404_NOT_FOUND)

        progress = {"step": "Processing...", "pct": 50}
        if rig.status == RiggedModel.STATUS_PENDING:
            progress = {"step": "Waiting in queue...", "pct": 0}
        elif rig.status == RiggedModel.STATUS_PROCESSING:
            progress = {"step": "Auto-rigging with Blender...", "pct": 50}
        elif rig.status == RiggedModel.STATUS_DONE:
            progress = {"step": "Done", "pct": 100}
        elif rig.status == RiggedModel.STATUS_FAILED:
            progress = {"step": "Failed", "pct": 0}

        rigged_glb_url = None
        if rig.rigged_glb:
            rigged_glb_url = request.build_absolute_uri(rig.rigged_glb.url)

        return Response(RigStatusSerializer({
            "rig_id": rig.id, "status": rig.status,
            "progress": progress, "rigged_glb_url": rigged_glb_url,
        }).data)

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
        rig.error_message = ""
        rig.rig_log = ""
        rig.bone_mapping = {}
        rig.processing_time_s = None
        rig.save()

        _run_rig_pipeline(str(rig.id))
        rig.refresh_from_db()
        return Response(self.get_serializer(rig, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="rerig-landmarks")
    def rerig_landmarks(self, request, id=None):
        """
        Save landmarks onto the rig and reset status to pending.
        Returns 202 immediately — the frontend polls /status/ for completion.
        The actual Blender work happens in a background thread so the HTTP
        request returns instantly and the spinner is replaced by the progress bar.
        """
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

        # Clear previous rigged output
        if rig.rigged_glb:
            try: rig.rigged_glb.delete(save=False)
            except Exception: pass

        # Store landmarks in bone_corrections so the background task can read them
        rig.bone_corrections = {"landmarks": landmarks}
        rig.status = RiggedModel.STATUS_PENDING
        rig.error_message = ""
        rig.rig_log = ""
        rig.bone_mapping = {}
        rig.processing_time_s = None
        rig.save()

        # Run in a background thread so HTTP response returns immediately
        import threading
        t = threading.Thread(
            target=_run_rig_pipeline,
            args=(str(rig.id),),
            kwargs={"extra_args": ["--landmarks", json.dumps(landmarks)]},
            daemon=True,
        )
        t.start()

        return Response({"status": "pending", "rig_id": str(rig.id)}, status=status.HTTP_202_ACCEPTED)