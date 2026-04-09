
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import ScopedRateThrottle, AnonRateThrottle
from rest_framework import status

from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Post
from .serializers import PostSerializer
from .throttles import PostBurstThrottle


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/posts/
# ─────────────────────────────────────────────────────────────────────────────
@extend_schema(
    summary="List all posts",
    description=(
        "**Throttle rules (most restrictive wins):**\n\n"
        "| Rule | Limit |\n"
        "|------|-------|\n"
        "| Anon (global) | 5 / minute |\n"
        "| User (global) | 10 / minute |\n"
        "| Scoped: posts_list | **20 / minute** |\n\n"
        "Returns 429 when any limit is exceeded."
    ),
    responses={
        200: PostSerializer(many=True),
        429: OpenApiResponse(description="429 Too Many Requests — throttle limit exceeded"),
    },
    tags=["Posts"],
)
class PostListView(APIView):
    """
    🔹 2. Scoped throttle: posts_list = 20/minute
    Global throttle კლასები base.py-დან ავტომატურად ვრცელდება.
    """
    permission_classes = [AllowAny]
    throttle_classes   = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope     = "posts_list"   # ← ScopedRateThrottle იყენებს ამას

    def get(self, request):
        posts = Post.objects.select_related("author").all()
        return Response(PostSerializer(posts, many=True).data)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/posts/create/
# ─────────────────────────────────────────────────────────────────────────────
@extend_schema(
    summary="Create a post",
    description=(
        "**Throttle rules (most restrictive wins):**\n\n"
        "| Rule | Limit |\n"
        "|------|-------|\n"
        "| User (global) | 10 / minute |\n"
        "| Scoped: posts_create | **3 / minute** |\n"
        "| Custom PostBurstThrottle | **1 / 10 seconds** |\n\n"
        "მაგალითად: 2 request-ის სწრაფად გაგზავნა → მეორე დაბლოკილია 10 წამით.\n\n"
        "Requires authentication (Bearer token)."
    ),
    request=PostSerializer,
    responses={
        201: PostSerializer,
        400: OpenApiResponse(description="Validation error"),
        401: OpenApiResponse(description="Authentication required"),
        429: OpenApiResponse(description="429 Too Many Requests — throttle limit exceeded"),
    },
    tags=["Posts"],
)
class PostCreateView(APIView):
    """
    🔹 2. Scoped throttle: posts_create = 3/minute
    🔹 3. Custom throttle: PostBurstThrottle = 1 POST per 10 seconds
    """
    permission_classes = [IsAuthenticated]
    throttle_classes   = [ScopedRateThrottle, PostBurstThrottle]
    throttle_scope     = "posts_create"  # ← ScopedRateThrottle-ისთვის

    def post(self, request):
        serializer = PostSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)