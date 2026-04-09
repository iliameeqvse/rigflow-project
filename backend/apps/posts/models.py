from django.db import models
from django.conf import settings


class Post(models.Model):
    author  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    title   = models.CharField(max_length=255)
    body    = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.title} — {self.author.email}"