"""Anthropic Claude Haiku 4.5 vision provider for landmark detection."""
import base64
import json
import logging
import os
from pathlib import Path

import anthropic

from .base import VisionRequest, VisionResponse
from .prompts import VISION_PROMPT_TEMPLATE

log = logging.getLogger(__name__)

MODEL_ID = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2000
MAX_RETRIES = 1  # one retry on malformed JSON; then return None


class ClaudeProvider:
    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"],
        )

    def detect(self, request: VisionRequest) -> VisionResponse | None:
        mesh_object_names = (
            ", ".join(m["name"] for m in request.mesh_objects)
            if request.mesh_objects else "unknown"
        )
        prompt = VISION_PROMPT_TEMPLATE.replace(
            "{mesh_object_names}", mesh_object_names
        )
        content = [{"type": "text", "text": prompt}]
        for view_name in ("front", "back", "left", "right"):
            view = request.views.get(view_name)
            if view is None:
                log.warning("View %r missing from VisionRequest; skipping", view_name)
                continue
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _b64(view["path"]),
                },
            })

        last_err = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.client.messages.create(
                    model=MODEL_ID,
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": content}],
                )
                text = "".join(
                    block.text for block in resp.content if hasattr(block, "text")
                )
                parsed = self._parse(text)
                if parsed is not None:
                    return parsed
                last_err = "malformed JSON or schema mismatch"
                log.warning("Claude response invalid (attempt %d/%d); retrying",
                            attempt + 1, MAX_RETRIES + 1)
            except anthropic.APIError as e:
                last_err = f"APIError: {e}"
                log.warning("Anthropic call failed (attempt %d): %s", attempt + 1, e)

        log.error("ClaudeProvider giving up after %d attempts: %s",
                  MAX_RETRIES + 1, last_err)
        return None

    def _parse(self, text: str) -> VisionResponse | None:
        try:
            stripped = text.strip()
            # Strip markdown code fence if present.
            if stripped.startswith("```"):
                stripped = stripped.split("```", 2)[1]
                if stripped.lstrip().startswith("json"):
                    stripped = stripped.lstrip()[4:]
                stripped = stripped.rsplit("```", 1)[0]
            data = json.loads(stripped)
            if not all(k in data for k in ("landmarks", "mesh_objects")):
                return None
            if not all(v in data["landmarks"] for v in ("front", "back", "left", "right")):
                return None
            return VisionResponse(
                landmarks=data["landmarks"],
                mesh_object_labels=data["mesh_objects"],
                notes=data.get("notes", ""),
                raw=data,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("Claude response unparseable: %s", e)
            return None


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")
