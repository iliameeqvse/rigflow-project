import uuid as _uuid

from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from .models import Animation, AnimationCategory
from .serializers import (
    AnimationSerializer,
    AnimationCategorySerializer,
    AnimationUploadSerializer,
)


def _unique_slug(name: str) -> str:
    """Generate a unique slug by appending a short UUID suffix."""
    base = slugify(name)[:240]
    suffix = str(_uuid.uuid4())[:8]
    candidate = f"{base}-{suffix}"
    # Extremely unlikely collision, but guard anyway
    while Animation.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{str(_uuid.uuid4())[:8]}"
    return candidate


class CategoryListView(APIView):
    """GET /api/v1/animations/categories/ — public list of all categories."""
    permission_classes = [AllowAny]

    def get(self, request):
        qs = AnimationCategory.objects.all()
        serializer = AnimationCategorySerializer(qs, many=True)
        return Response(serializer.data)


class AnimationViewSet(ViewSet):
    """
    GET  /api/v1/animations/          → browse approved public animations
    POST /api/v1/animations/          → upload a new animation (login required)
    GET  /api/v1/animations/mine/     → list the authenticated user's uploads
    """

    def get_permissions(self):
        if self.action == "list":
            return [AllowAny()]
        return [IsAuthenticated()]

    # ── GET /animations/ ──────────────────────────────────────────────────────
    def list(self, request):
        qs = Animation.objects.filter(
            moderation_status=Animation.MOD_APPROVED,
            is_public=True,
        ).select_related("category")

        # Optional filters
        category_slug = request.query_params.get("category__slug")
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)

        is_looping = request.query_params.get("is_looping")
        if is_looping is not None:
            qs = qs.filter(is_looping=is_looping.lower() == "true")

        # Pagination
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        page_size = 24
        start = (page - 1) * page_size
        total = qs.count()
        items = qs[start: start + page_size]

        serializer = AnimationSerializer(
            items, many=True, context={"request": request}
        )
        return Response({"count": total, "results": serializer.data})

    # ── POST /animations/ ─────────────────────────────────────────────────────
    def create(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required to upload animations."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = AnimationUploadSerializer(data={
            **request.data,
            "file": request.FILES.get("file"),
        })
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        profile = getattr(request.user, "profile", None)

        # Resolve category (optional)
        category = None
        if vd["category_slug"]:
            try:
                category = AnimationCategory.objects.get(slug=vd["category_slug"])
            except AnimationCategory.DoesNotExist:
                pass  # Leave category null rather than hard-failing

        animation = Animation.objects.create(
            name=vd["name"],
            slug=_unique_slug(vd["name"]),
            description=vd["description"],
            category=category,
            gltf_file=vd["file"],
            is_looping=vd["is_looping"],
            is_public=vd["is_public"],
            is_user_uploaded=True,
            tags=vd["tags"],
            uploaded_by=profile,
            # Always starts as pending regardless of is_public
            moderation_status=Animation.MOD_PENDING,
        )

        out = AnimationSerializer(animation, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    # ── GET /animations/mine/ ─────────────────────────────────────────────────
    @action(detail=False, methods=["get"], url_path="mine", permission_classes=[IsAuthenticated])
    def mine(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile:
            return Response({"results": [], "count": 0})

        qs = Animation.objects.filter(
            uploaded_by=profile
        ).select_related("category").order_by("-created_at")

        serializer = AnimationSerializer(qs, many=True, context={"request": request})
        return Response({"count": qs.count(), "results": serializer.data})