"""Claude Haiku 4.5 vision provider — STUB (Task 9).

Placeholder so the lazy import in get_provider() resolves correctly when
LANDMARK_VISION_PROVIDER=claude + ANTHROPIC_API_KEY are set.
Returns None (geometry-only fallback) until the real SDK call is wired up.

TODO (Task 9):
  1. Build the prompt from VisionRequest.views (base64-encode each PNG).
  2. Call anthropic.Anthropic().messages.create(model="claude-haiku-4-5", ...)
  3. Parse the JSON response into VisionResponse.
  4. On two consecutive JSON-parse failures raise RuntimeError so tasks.py
     can set detection_method="failed" and notify the frontend.
"""
import logging

from .base import VisionRequest, VisionResponse

log = logging.getLogger(__name__)


class ClaudeProvider:
    def detect(self, request: VisionRequest) -> VisionResponse | None:
        log.info(
            "ClaudeProvider.detect called for rig_id=%s — "
            "stub returns None (geometry fallback) until Task 9 is wired up.",
            request.rig_id,
        )
        return None
