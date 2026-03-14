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
from .tasks import auto_rig_model

User = get_user_model()


def _get_or_create_demo_profile():
    """Create a demo user/profile for anonymous uploads."""
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
    permission_classes = [AllowAny]  # Allow upload without login for quick testing
    lookup_field = "id"
    lookup_value_regex = r"[0-9a-f-]+"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_authenticated and hasattr(self.request.user, "profile"):
            return qs.filter(user=self.request.user.profile)
        # Anonymous: show nothing for list; status endpoint uses direct lookup
        return qs.none()

    def perform_create(self, serializer):
        if self.request.user.is_authenticated and hasattr(self.request.user, "profile"):
            profile = self.request.user.profile
        else:
            profile = _get_or_create_demo_profile()
        serializer.save(user=profile)

    def create(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        name = request.data.get("name", "Untitled")
        if not file:
            return Response(
                {"error": "Missing 'file' in request."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ext = (file.name or "").split(".")[-1].lower()
        allowed = {"fbx", "glb", "gltf", "obj"}
        if ext not in allowed:
            return Response(
                {"error": f"Unsupported format: .{ext}. Use FBX, GLB, GLTF, or OBJ."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if self.request.user.is_authenticated and hasattr(self.request.user, "profile"):
            profile = self.request.user.profile
        else:
            profile = _get_or_create_demo_profile()

        rig = RiggedModel.objects.create(
            user=profile,
            name=name[:255],
            original_file=file,
            original_format=ext,
            file_size_mb=round(file.size / (1024 * 1024), 2),
            status=RiggedModel.STATUS_PENDING,
        )
        # Run rigging synchronously (no Celery/Redis needed in local dev)
        auto_rig_model(str(rig.id))
        rig.refresh_from_db()
        serializer = self.get_serializer(rig)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="status")
    def status_action(self, request, id=None):
        try:
            rig = RiggedModel.objects.get(id=id)
        except RiggedModel.DoesNotExist:
            return Response(
                {"error": "Rig not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
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

        data = RigStatusSerializer({
            "rig_id": rig.id,
            "status": rig.status,
            "progress": progress,
            "rigged_glb_url": rigged_glb_url,
        }).data
        return Response(data)
