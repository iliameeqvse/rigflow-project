from django.contrib import admin

from .models import Animation, AnimationCategory


@admin.register(AnimationCategory)
class AnimationCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order",)


@admin.register(Animation)
class AnimationAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "is_user_uploaded",
        "moderation_status", "download_count", "created_at",
    )
    list_filter = ("moderation_status", "is_user_uploaded", "category")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("-created_at",)
