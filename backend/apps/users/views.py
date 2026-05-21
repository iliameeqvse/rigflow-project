from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from .serializers import RegisterSerializer, LoginSerializer


def _token_response(user) -> dict:
    """Generate a JWT access + refresh pair for the given user."""
    refresh = RefreshToken.for_user(user)
    return {
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id":       user.id,
            "email":    user.email,
            "username": user.username,
        },
    }


# ── Register ──────────────────────────────────────────────────────────────────
@extend_schema(
    summary="Register a new user",
    description=(
        "Create a new account. Returns a JWT access + refresh pair plus the "
        "user record so the frontend can sign the user in immediately."
    ),
    request=RegisterSerializer,
    responses={
        201: OpenApiResponse(description="User created and signed in"),
        400: OpenApiResponse(description="Validation error"),
    },
    examples=[
        OpenApiExample(
            "Example request",
            value={"email": "user@example.com", "username": "myname", "password": "securepass123"},
            request_only=True,
        ),
        OpenApiExample(
            "Example response",
            value={
                "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "user": {"id": 1, "email": "user@example.com", "username": "myname"},
            },
            response_only=True,
        ),
    ],
    tags=["Auth"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user = serializer.save()
    return Response(_token_response(user), status=status.HTTP_201_CREATED)


# ── Login ─────────────────────────────────────────────────────────────────────
@extend_schema(
    summary="Login — get JWT tokens",
    description=(
        "Authenticate with email + password. "
        "Copy the **access** token, click **Authorize** at the top of this page, "
        "and enter:  `Bearer <access_token>`"
    ),
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(description="JWT access + refresh tokens"),
        400: OpenApiResponse(description="Invalid credentials"),
    },
    examples=[
        OpenApiExample(
            "Example request",
            value={"email": "user@example.com", "password": "securepass123"},
            request_only=True,
        ),
        OpenApiExample(
            "Example response",
            value={
                "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "user": {"id": 1, "email": "user@example.com", "username": "myname"},
            },
            response_only=True,
        ),
    ],
    tags=["Auth"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email    = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    user     = authenticate(request, email=email, password=password)

    if user is None:
        return Response(
            {"detail": "Invalid email or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(_token_response(user))


# ── Me (current user) ─────────────────────────────────────────────────────────
@extend_schema(
    summary="Get current user",
    description="Returns the authenticated user's profile. Requires a valid Bearer token.",
    responses={
        200: OpenApiResponse(description="Current user info"),
        401: OpenApiResponse(description="Not authenticated"),
    },
    tags=["Auth"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    user = request.user
    return Response({
        "id":       user.id,
        "email":    user.email,
        "username": user.username,
        "plan":     getattr(getattr(user, "profile", None), "plan", "free"),
    })