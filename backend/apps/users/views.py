from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, LoginSerializer


def _token_response(user):
    """Return access + refresh JWT pair for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user = serializer.save()
    # Auto-login after registration — return tokens straight away
    return Response(_token_response(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]
    user = authenticate(request, email=email, password=password)
    if user is None:
        return Response(
            {"detail": "Invalid email or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(_token_response(user))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Return the currently authenticated user's info."""
    user = request.user
    profile = getattr(user, "profile", None)
    return Response({
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "plan": profile.plan if profile else "free",
        "avatar": (
            request.build_absolute_uri(profile.avatar.url)
            if profile and profile.avatar
            else None
        ),
    })