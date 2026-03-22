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
    base = slugify(name)[:240] or "animation"
    suffix = str(_uuid.uuid4())[:8]
    candidate = f"{base}-{suffix}"
    while Animation.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{str(_uuid.uuid4())[:8]}"
    return candidate


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = AnimationCategory.objects.all()
        return Response(AnimationCategorySerializer(qs, many=True).data)


class AnimationViewSet(ViewSet):

    def get_permissions(self):
        if self.action in ("list",):
            return [AllowAny()]
        return [IsAuthenticated()]

    # GET /api/v1/animations/
    def list(self, request):
        qs = Animation.objects.filter(
            moderation_status=Animation.MOD_APPROVED,
            is_public=True,
        ).select_related("category")

        if slug := request.query_params.get("category__slug"):
            qs = qs.filter(category__slug=slug)
        if search := request.query_params.get("search"):
            qs = qs.filter(name__icontains=search)
        if loop := request.query_params.get("is_looping"):
            qs = qs.filter(is_looping=loop.lower() == "true")

        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        page_size = 24
        start = (page - 1) * page_size
        total = qs.count()

        serializer = AnimationSerializer(
            qs[start: start + page_size], many=True, context={"request": request}
        )
        return Response({"count": total, "results": serializer.data})

    # POST /api/v1/animations/
    def create(self, request):
        # Build data dict — file comes from FILES, everything else from POST
        data = {
            "name": request.data.get("name", ""),
            "description": request.data.get("description", ""),
            "category_slug": request.data.get("category_slug", ""),
            "is_looping": request.data.get("is_looping", "false"),
            "tags": request.data.get("tags", ""),
            "file": request.FILES.get("file"),
        }

        serializer = AnimationUploadSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        profile = getattr(request.user, "profile", None)

        # Resolve optional category
        category = None
        cat_slug = vd.get("category_slug", "").strip()
        if cat_slug:
            try:
                category = AnimationCategory.objects.get(slug=cat_slug)
            except AnimationCategory.DoesNotExist:
                pass

        animation = Animation.objects.create(
            name=vd["name"],
            slug=_unique_slug(vd["name"]),
            description=vd.get("description", ""),
            category=category,
            gltf_file=vd["file"],
            is_looping=vd["is_looping"],
            # All user uploads are immediately public and approved
            is_public=True,
            is_user_uploaded=True,
            tags=vd["tags"],
            uploaded_by=profile,
            moderation_status=Animation.MOD_APPROVED,
        )

        out = AnimationSerializer(animation, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    # GET /api/v1/animations/mine/
    @action(detail=False, methods=["get"], url_path="mine",
            permission_classes=[IsAuthenticated])
    def mine(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile:
            return Response({"results": [], "count": 0})
        qs = Animation.objects.filter(
            uploaded_by=profile
        ).select_related("category").order_by("-created_at")
        serializer = AnimationSerializer(qs, many=True, context={"request": request})
        return Response({"count": qs.count(), "results": serializer.data})