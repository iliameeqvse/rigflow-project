from django.shortcuts import get_object_or_404
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


class AnimationListView(APIView):
    """
    GET  /api/v1/animations/  — public animation library.
    Throttle: AnimationListThrottle (anon 10/min, user 60/min).
    """
    permission_classes = [AllowAny]
    throttle_classes   = [AnimationListThrottle]

    @extend_schema(
        summary="Browse animation library",
        description="Returns all approved public animations.\n\n**Throttle:** 10 req/min (anon), 60 req/min (user).",
        responses={200: AnimationSerializer(many=True)},
        tags=["Animations"],
    )
    def get(self, request):
        qs = Animation.objects.filter(
            moderation_status=Animation.MOD_APPROVED,
            is_public=True,
        ).select_related("category", "uploaded_by__user")
        serializer = AnimationSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class AnimationUploadView(APIView):
    """
    POST /api/v1/animations/  — upload a custom animation.
    Throttle: authenticated only, max 10 uploads/hour.
    Anonymous → 429 immediately.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes   = [AnonUploadThrottle, AnimationUploadThrottle]

    @extend_schema(
        summary="Upload a custom animation",
        description=(
            "Upload a GLB/FBX animation file.\n\n"
            "**Throttle:** authenticated users only, max **10 uploads / hour**.\n"
            "Anonymous users receive 429 immediately."
        ),
        request=AnimationUploadSerializer,
        responses={
            201: AnimationSerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication required"),
            429: OpenApiResponse(description="Upload limit reached (10/hour)"),
        },
        tags=["Animations"],
    )
    def post(self, request):
        serializer = AnimationUploadSerializer(
            data=request.data,
            context={"request": request},
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
    throttle_classes   = [AnimationListThrottle]

    @extend_schema(
        summary="List animation categories",
        tags=["Animations"],
    )
    def get(self, request):
        cats = AnimationCategory.objects.all()
        data = [{"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in cats]
        return Response(data)