"""Unit tests for landmark sanity checks. Pure-Python, no Blender deps."""
from django.test import SimpleTestCase

from apps.rigging.sanity import (
    SanityResult,
    check_landmarks,
    LANDMARK_KEYS,
)


def _good():
    """A canonical 14-key dict that should pass every check."""
    return {
        "chin":           (0.0,  1.80, 0.0),
        "groin":          (0.0,  1.00, 0.0),
        "left_shoulder":  ( 0.20, 1.60, 0.0),
        "right_shoulder": (-0.20, 1.60, 0.0),
        "left_elbow":     ( 0.45, 1.30, 0.0),
        "right_elbow":    (-0.45, 1.30, 0.0),
        "left_wrist":     ( 0.70, 1.00, 0.0),
        "right_wrist":    (-0.70, 1.00, 0.0),
        "left_hip":       ( 0.10, 1.00, 0.0),
        "right_hip":      (-0.10, 1.00, 0.0),
        "left_knee":      ( 0.10, 0.50, 0.0),
        "right_knee":     (-0.10, 0.50, 0.0),
        "left_ankle":     ( 0.10, 0.00, 0.0),
        "right_ankle":    (-0.10, 0.00, 0.0),
    }


class SanityTests(SimpleTestCase):
    def test_good_landmarks_pass(self):
        r = check_landmarks(_good(), world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertTrue(r.ok, r.failures)

    def test_inverted_groin_fails(self):
        bad = _good()
        bad["groin"] = (0.0, 1.95, 0.0)  # above chin
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("groin_above_chin", [f.code for f in r.failures])

    def test_asymmetric_wrist_fails(self):
        bad = _good()
        bad["left_wrist"]  = ( 0.70, 1.00, 0.0)
        bad["right_wrist"] = (-0.10, 1.00, 0.0)  # 7× asymmetric
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("asymmetry_wrist", [f.code for f in r.failures])

    def test_outside_aabb_fails(self):
        bad = _good()
        bad["left_wrist"] = (5.0, 1.0, 0.0)  # way outside
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("outside_aabb_left_wrist", [f.code for f in r.failures])

    def test_missing_key_fails(self):
        bad = _good()
        del bad["chin"]
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("missing_chin", [f.code for f in r.failures])

    def test_all_14_keys_present_in_constant(self):
        self.assertEqual(len(LANDMARK_KEYS), 14)
        self.assertIn("chin", LANDMARK_KEYS)
        self.assertIn("right_ankle", LANDMARK_KEYS)
