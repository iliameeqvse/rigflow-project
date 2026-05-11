"""Geometry-only mode — skips AI entirely, returns None."""
from .base import VisionRequest, VisionResponse


class NoneProvider:
    def detect(self, request: VisionRequest) -> VisionResponse | None:
        return None
