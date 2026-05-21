"""Tests for the landmark debug photo compositor."""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase
from PIL import Image

from apps.rigging.debug_photo import build_landmark_debug_photo


def _write_ortho(dir_path):
    """Write four 512×512 placeholder ortho PNGs."""
    for view in ("front", "back", "left", "right"):
        Image.new("RGB", (512, 512), (90, 90, 90)).save(
            Path(dir_path) / f"{view}.png")


class BuildLandmarkDebugPhotoTests(SimpleTestCase):
    def test_builds_1024_composite(self):
        with tempfile.TemporaryDirectory() as td:
            _write_ortho(td)
            out = Path(td) / "debug.png"
            views = ("front", "back", "left", "right")
            ai = {v: {"chin": [100, 50]} for v in views}
            final = {v: {"chin": [110, 60]} for v in views}
            self.assertTrue(build_landmark_debug_photo(td, ai, final, out))
            self.assertTrue(out.is_file())
            with Image.open(out) as im:
                self.assertEqual(im.size, (1024, 1024))

    def test_null_landmarks_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            _write_ortho(td)
            out = Path(td) / "debug.png"
            views = ("front", "back", "left", "right")
            ai = {v: {"chin": None, "groin": [50, 50]} for v in views}
            self.assertTrue(build_landmark_debug_photo(td, ai, {}, out))
            self.assertTrue(out.is_file())

    def test_missing_ortho_returns_false(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "debug.png"
            self.assertFalse(build_landmark_debug_photo(td, {}, {}, out))
            self.assertFalse(out.is_file())
