from rest_framework import serializers
from .models import Post


class PostSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)

    class Meta:
        model  = Post
        fields = ["id", "author_email", "title", "body", "created"]
        read_only_fields = ["id", "author_email", "created"]