from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import UserProfile


User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "username", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        # Belt-and-braces: the post_save signal already creates the profile,
        # but this keeps the serializer self-contained if signals are ever
        # disconnected (e.g. in a test that monkeypatches dispatch).
        UserProfile.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

