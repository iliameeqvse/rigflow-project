"""Tests for provider dispatch, response parsing, and sanity cascade."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase

from apps.rigging.landmark_vision import get_provider
from apps.rigging.landmark_vision.none_provider import NoneProvider

FIXTURES = Path(__file__).parent / "fixtures"


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

    @patch.dict(os.environ,
                {"LANDMARK_VISION_PROVIDER": "claude", "ANTHROPIC_API_KEY": "sk-test"},
                clear=True)
    def test_claude_with_api_key_returns_claude_provider(self):
        from apps.rigging.landmark_vision.claude_provider import ClaudeProvider
        self.assertIsInstance(get_provider(), ClaudeProvider)


class ClaudeProviderParseTests(SimpleTestCase):
    def _provider(self):
        from apps.rigging.landmark_vision.claude_provider import ClaudeProvider
        return ClaudeProvider.__new__(ClaudeProvider)  # skip __init__ — no key needed

    def test_parse_well_formed_fixture(self):
        text = (FIXTURES / "claude_response_johnny.json").read_text()
        result = self._provider()._parse(text)
        self.assertIsNotNone(result)
        self.assertIn("chin", result.landmarks["front"])
        self.assertEqual(result.landmarks["front"]["chin"], [256, 56])
        self.assertEqual(result.mesh_object_labels.get("Object_3"), "body")
        self.assertEqual(result.mesh_object_labels.get("Object_2"), "hat")

    def test_parse_malformed_returns_none(self):
        p = self._provider()
        self.assertIsNone(p._parse("not json"))
        self.assertIsNone(p._parse('{"landmarks": {}}'))   # missing mesh_objects
        self.assertIsNone(p._parse('{"landmarks": {"front": {}}, "mesh_objects": {}}'))  # missing back/left/right

    def test_parse_strips_markdown_fence(self):
        inner = json.dumps({
            "landmarks": {"front": {}, "back": {}, "left": {}, "right": {}},
            "mesh_objects": {},
        })
        wrapped = f"```json\n{inner}\n```"
        result = self._provider()._parse(wrapped)
        self.assertIsNotNone(result)


class SanityCascadeTests(SimpleTestCase):
    """Unit tests for the sanity.check_landmarks logic used in the cascade."""

    _AABB = ((-2.0, -0.5, -2.0), (2.0, 2.5, 2.0))

    def _good_landmarks(self):
        return json.loads((FIXTURES / "claude_response_johnny.json").read_text())

    def test_inverted_fixture_fails_sanity(self):
        from apps.rigging.sanity import check_landmarks
        # The inverted fixture has groin above chin in pixel space, which
        # maps to groin having a HIGHER Y (closer to top of image = lower
        # world position in three.js, so inverted means groin.y > chin.y).
        raw = json.loads((FIXTURES / "claude_response_inverted.json").read_text())
        # Build a minimal three.js-space landmark dict from pixel coords:
        # pixel top of image → high Y (three.js Y=0..2 bottom-to-top).
        # In the inverted fixture, chin pixel y=490 (bottom) → low world Y,
        # groin pixel y=56 (top) → high world Y → groin.y > chin.y → FAIL.
        image_size = 512
        def px_to_y(py):
            return (1.0 - py / image_size) * 2.0   # three.js Y-up, 0-2 range

        front = raw["landmarks"]["front"]
        lm = {}
        for k, v in front.items():
            if v is not None:
                lm[k] = (v[0] / image_size * 2 - 1, px_to_y(v[1]), 0.0)
        sr = check_landmarks(lm, world_aabb=self._AABB)
        self.assertFalse(sr.ok)
        codes = {f.code for f in sr.failures}
        self.assertIn("groin_above_chin", codes)

    def test_good_fixture_passes_sanity(self):
        from apps.rigging.sanity import check_landmarks
        raw = json.loads((FIXTURES / "claude_response_johnny.json").read_text())
        image_size = 512
        def px_to_y(py):
            return (1.0 - py / image_size) * 2.0
        front = raw["landmarks"]["front"]
        lm = {}
        for k, v in front.items():
            if v is not None:
                lm[k] = (v[0] / image_size * 2 - 1, px_to_y(v[1]), 0.0)
        sr = check_landmarks(lm, world_aabb=self._AABB)
        self.assertTrue(sr.ok, f"Unexpected failures: {sr.failures}")


class VisionPromptTests(SimpleTestCase):
    """The vision prompt is load-bearing — it's the only place we tell Claude
    that the orientation markers exist and how to interpret them. These tests
    pin the behavior so a careless prompt edit can't silently drop the marker
    instructions and re-introduce the viewer/character left-right swap.
    """

    def _prompt(self) -> str:
        from apps.rigging.landmark_vision.prompts import VISION_PROMPT_TEMPLATE
        return VISION_PROMPT_TEMPLATE

    def test_mentions_red_and_blue_marker_convention(self):
        prompt = self._prompt()
        self.assertIn("RED", prompt)
        self.assertIn("BLUE", prompt)
        # The convention must explicitly tie color to anatomical side.
        # We accept either "RED ... LEFT" or "LEFT ... RED" co-occurring close
        # together; the simple form below is good enough as a regression net.
        self.assertRegex(prompt, r"RED[\s\S]{0,200}LEFT")
        self.assertRegex(prompt, r"BLUE[\s\S]{0,200}RIGHT")

    def test_addresses_back_facing_case(self):
        # The viewer/character mismatch failure mode is when 'front' actually
        # shows the back of the character. The prompt must say the rule still
        # applies in that case, otherwise vision models default to viewer-left.
        prompt = self._prompt().lower()
        self.assertTrue(
            "back" in prompt and ("even" in prompt or "regardless" in prompt),
            "Prompt should call out the back-facing 'front' render explicitly",
        )

    def test_keeps_mesh_object_names_placeholder(self):
        # The provider does .replace("{mesh_object_names}", ...) — drop the
        # placeholder and the scene context disappears silently.
        self.assertIn("{mesh_object_names}", self._prompt())

    def test_keeps_all_14_landmark_keys(self):
        prompt = self._prompt()
        for key in (
            "chin", "groin",
            "left_shoulder", "right_shoulder",
            "left_elbow",    "right_elbow",
            "left_wrist",    "right_wrist",
            "left_hip",      "right_hip",
            "left_knee",     "right_knee",
            "left_ankle",    "right_ankle",
        ):
            self.assertIn(key, prompt, f"Prompt missing landmark key: {key}")
