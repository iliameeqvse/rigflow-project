"""Regression tests for _extract_rotation_args (tasks.py).

Bug history: the ortho-render command filtered extra_args with
`startswith("--initial-rotation")`, which kept the flag names but dropped
their numeric values. argparse then failed in the render subprocess and the
AI vision phase was silently skipped for any upload with a rotation override.
"""
from django.test import SimpleTestCase

from apps.rigging.tasks import _extract_rotation_args


class ExtractRotationArgsTests(SimpleTestCase):
    def test_keeps_euler_flag_value_pairs(self):
        extra = [
            "--initial-rotation-x", "15.0",
            "--initial-rotation-y", "0.0",
            "--initial-rotation-z", "-90.0",
        ]
        self.assertEqual(_extract_rotation_args(extra), extra)

    def test_keeps_quaternion_flags_with_values(self):
        extra = [
            "--initial-rotation-x", "15.0",
            "--initial-rotation-y", "0.0",
            "--initial-rotation-z", "0.0",
            "--initial-rotation-qx", "0.1",
            "--initial-rotation-qy", "0.2",
            "--initial-rotation-qz", "0.3",
            "--initial-rotation-qw", "0.9",
        ]
        self.assertEqual(_extract_rotation_args(extra), extra)

    def test_drops_non_rotation_flags(self):
        extra = ["--landmarks", '{"chin": [0, 1, 0]}']
        self.assertEqual(_extract_rotation_args(extra), [])

    def test_none_returns_empty_list(self):
        self.assertEqual(_extract_rotation_args(None), [])

    def test_empty_returns_empty_list(self):
        self.assertEqual(_extract_rotation_args([]), [])

    def test_mixed_keeps_only_rotation_pairs(self):
        extra = [
            "--landmarks", "{}",
            "--initial-rotation-x", "30.0",
            "--initial-rotation-y", "0.0",
            "--initial-rotation-z", "0.0",
        ]
        self.assertEqual(
            _extract_rotation_args(extra),
            [
                "--initial-rotation-x", "30.0",
                "--initial-rotation-y", "0.0",
                "--initial-rotation-z", "0.0",
            ],
        )
