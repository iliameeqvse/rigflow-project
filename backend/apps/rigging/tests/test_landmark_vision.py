"""Tests for provider dispatch. Live SDK calls are not made here."""
import os
from unittest.mock import patch
from django.test import SimpleTestCase

from apps.rigging.landmark_vision import get_provider
from apps.rigging.landmark_vision.none_provider import NoneProvider


class ProviderDispatchTests(SimpleTestCase):
    @patch.dict(os.environ, {"LANDMARK_VISION_PROVIDER": "none"}, clear=False)
    def test_explicit_none_returns_none_provider(self):
        self.assertIsInstance(get_provider(), NoneProvider)

    @patch.dict(os.environ, {"LANDMARK_VISION_PROVIDER": "claude"}, clear=True)
    def test_claude_without_api_key_degrades_to_none(self):
        # ANTHROPIC_API_KEY intentionally absent
        provider = get_provider()
        self.assertIsInstance(provider, NoneProvider)

    @patch.dict(os.environ, {}, clear=True)
    def test_unset_env_defaults_to_none(self):
        self.assertIsInstance(get_provider(), NoneProvider)

    @patch.dict(os.environ, {"LANDMARK_VISION_PROVIDER": "unknown_value"}, clear=False)
    def test_unknown_value_falls_back_to_none(self):
        self.assertIsInstance(get_provider(), NoneProvider)

    def test_none_provider_detect_returns_none(self):
        from apps.rigging.landmark_vision.base import VisionRequest
        req = VisionRequest(
            rig_id="abc",
            views={},
            mesh_objects=[],
            world_aabb=((-1, 0, -1), (1, 2, 1)),
        )
        self.assertIsNone(NoneProvider().detect(req))
