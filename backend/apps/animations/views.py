from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Animation, AnimationCategory
from .serializers import AnimationSerializer, AnimationUploadSerializer
from apps.throttles import (
    AnonUploadThrottle,
    AnimationUploadThrottle,
    AnimationListThrottle,
)


class AnimationListOrUploadView(APIView):
    """
    GET  /api/v1/animations/  — browse animations (public library + my uploads).
    POST /api/v1/animations/  — upload a new animation (authenticated only).

    Split permission/throttle policy by method so the front-end can keep a
    single URL for both operations (the existing form POSTs here).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_throttles(self):
        if self.request.method == "POST":
            return [AnonUploadThrottle(), AnimationUploadThrottle()]
        return [AnimationListThrottle()]

    @extend_schema(
        summary="Browse animation library",
        description=(
            "Returns approved public animations plus any uploaded by the "
            "authenticated user (so the uploader always sees their own work)."
        ),
        responses={200: AnimationSerializer(many=True)},
        tags=["Animations"],
    )
    def get(self, request):
        public = Q(moderation_status=Animation.MOD_APPROVED, is_public=True)
        if request.user.is_authenticated and hasattr(request.user, "profile"):
            flt = public | Q(uploaded_by=request.user.profile)
        else:
            flt = public
        qs = (
            Animation.objects.filter(flt)
            .select_related("category", "uploaded_by__user")
            .distinct()
        )
        return Response(
            AnimationSerializer(qs, many=True, context={"request": request}).data
        )

    @extend_schema(
        summary="Upload a custom animation",
        description=(
            "Upload a GLB/GLTF/FBX animation file.\n\n"
            "**Throttle:** authenticated users only, max 15 uploads / hour.\n"
            "Anonymous users receive 429 immediately."
        ),
        request=AnimationUploadSerializer,
        responses={
            201: AnimationSerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication required"),
            429: OpenApiResponse(description="Upload limit reached"),
        },
        tags=["Animations"],
    )
    def post(self, request):
        serializer = AnimationUploadSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        animation = serializer.save()
        return Response(
            AnimationSerializer(animation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AnimationCategoryListView(APIView):
    """GET /api/v1/animations/categories/ — list all categories."""
    permission_classes = [AllowAny]
    throttle_classes = [AnimationListThrottle]

    @extend_schema(summary="List animation categories", tags=["Animations"])
    def get(self, request):
        cats = AnimationCategory.objects.all()
        return Response(
            [{"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon}
             for c in cats]
        )
