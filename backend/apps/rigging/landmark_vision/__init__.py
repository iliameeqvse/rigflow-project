"""Provider dispatch keyed on LANDMARK_VISION_PROVIDER + ANTHROPIC_API_KEY."""
import logging
import os

from .base import VisionRequest, VisionResponse
from .none_provider import NoneProvider

log = logging.getLogger(__name__)


def get_provider():
    name = os.environ.get("LANDMARK_VISION_PROVIDER", "none").strip().lower()

    if name == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            log.warning(
                "LANDMARK_VISION_PROVIDER=claude but ANTHROPIC_API_KEY is unset; "
                "degrading to geometry-only mode."
            )
            return NoneProvider()
        from .claude_provider import ClaudeProvider  # imported lazily — Task 9 creates it
        return ClaudeProvider()

    if name not in ("none", "", "geometry"):
        log.warning("Unknown LANDMARK_VISION_PROVIDER=%r; falling back to none.", name)
    return NoneProvider()


__all__ = ["get_provider", "VisionRequest", "VisionResponse", "NoneProvider"]
