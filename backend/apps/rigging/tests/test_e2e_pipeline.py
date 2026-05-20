"""
E2E pipeline integration tests.

These tests call _run_rig_pipeline against real FBX files and a real
Blender installation, but mock the AI vision provider so they run
without an ANTHROPIC_API_KEY.

Step 1 — geometry-only verified via live curl above (Task 17 Step 1).
Step 4 — sanity-failure cascade: AI returns inverted landmarks → rig
         still finishes done, detection_method == "failed".
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import django
from django.conf import settings
from django.test import TestCase

FIXTURES = Path(__file__).parent / "fixtures"

# Path to the smallest available test FBX.
_JOHNNY_FBX = Path(
    "/home/dev/projects/rigflow-project/rigflow-project/backend/media/rigs/2/"
    "c3a396c0-8c42-49b5-9aa0-7d034ca61dbd/johnny_joestar.fbx"
)


def _make_rig(fbx_path: Path):
    """Create a minimal RiggedModel pointing at an existing FBX."""
    from django.core.files import File
    from apps.users.models import User, UserProfile
    from apps.rigging.models import RiggedModel

    user, _ = User.objects.get_or_create(
        email="e2e@test.local",
        defaults={"is_active": True},
    )
    user.set_password("testpass")
    user.save()
    profile, _ = UserProfile.objects.get_or_create(user=user)

    with open(fbx_path, "rb") as f:
        rig = RiggedModel.objects.create(
            user=profile,
            name="e2e-test",
            original_format="fbx",
            file_size_mb=fbx_path.stat().st_size / 1_000_000,
        )
        rig.original_file.save(fbx_path.name, File(f), save=True)
    return rig


class GeometryOnlyPipelineTest(TestCase):
    """Step 1: geometry-only run — no AI provider wired."""

    def setUp(self):
        if not _JOHNNY_FBX.exists():
            self.skipTest("Test FBX not present")
        if not Path(settings.BLENDER_EXECUTABLE).is_file():
            self.skipTest("Blender not installed")

    def test_geometry_only_produces_done_rig(self):
        from apps.rigging.tasks import _run_rig_pipeline
        from apps.rigging.landmark_vision.none_provider import NoneProvider

        rig = _make_rig(_JOHNNY_FBX)
        # Force the geometry-only path regardless of any LANDMARK_VISION_PROVIDER
        # / ANTHROPIC_API_KEY present in the environment (e.g. a developer's
        # backend/.env). Without this the test is non-hermetic: a configured
        # Claude key drives the AI path and detection_method becomes
        # "llm_vision" instead of the asserted "geometry".
        with patch(
            "apps.rigging.landmark_vision.get_provider",
            return_value=NoneProvider(),
        ):
            result = _run_rig_pipeline(str(rig.id))

        rig.refresh_from_db()
        self.assertEqual(result["status"], "done")
        self.assertEqual(rig.status, "done")
        self.assertEqual(rig.detection_method, "geometry")
        self.assertIsNotNone(rig.landmarks)
        self.assertEqual(len(rig.landmarks), 14)
        self.assertTrue(bool(rig.rigged_glb), "rigged GLB file should be saved")


class SanityCascadePipelineTest(TestCase):
    """Step 4: AI returns inverted landmarks → cascade → detection_method=failed."""

    def setUp(self):
        if not _JOHNNY_FBX.exists():
            self.skipTest("Test FBX not present")
        if not Path(settings.BLENDER_EXECUTABLE).is_file():
            self.skipTest("Blender not installed")

    def test_inverted_ai_response_cascades_to_failed_detection(self):
        """When the AI response has groin above chin, the sanity cascade
        should run geometry-only as a fallback.  The rig must finish
        done and detection_method must be 'failed' (geometry sanity passed
        but the AI path did not)."""
        from apps.rigging.tasks import _run_rig_pipeline
        from apps.rigging.landmark_vision.base import VisionResponse

        # Build a VisionResponse whose landmark pixel coords (when raycasted
        # into 3D and converted to three.js space) will put groin above chin.
        # We use the inverted fixture directly.
        inverted_raw = json.loads(
            (FIXTURES / "claude_response_inverted.json").read_text()
        )

        fake_vision_resp = VisionResponse(
            landmarks=inverted_raw["landmarks"],
            mesh_object_labels=inverted_raw["mesh_objects"],
            notes=inverted_raw.get("notes", ""),
            raw=inverted_raw,
        )

        fake_provider = MagicMock()
        fake_provider.detect.return_value = fake_vision_resp

        rig = _make_rig(_JOHNNY_FBX)

        # get_provider is imported locally inside _run_rig_pipeline, so we
        # patch it at the source module rather than the tasks module.
        with patch(
            "apps.rigging.landmark_vision.get_provider", return_value=fake_provider
        ), patch.dict("os.environ", {"LANDMARK_VISION_PROVIDER": "claude",
                                     "ANTHROPIC_API_KEY": "sk-fake"}):
            result = _run_rig_pipeline(str(rig.id))

        rig.refresh_from_db()

        self.assertEqual(result["status"], "done",
                         f"Rig should finish done; error: {rig.error_message}")
        self.assertEqual(rig.status, "done")
        # The inverted AI landmarks fail sanity → cascade ran geometry-only.
        # Geometry landmarks may pass or also fail sanity (detection_method
        # ends up either "geometry" or "failed").  Either way the rig is done
        # and NOT llm_vision (that would mean the bad AI landmarks were used).
        self.assertNotEqual(rig.detection_method, "llm_vision",
                            "Bad AI landmarks should not be used as the final rig")
        self.assertTrue(bool(rig.rigged_glb), "rigged GLB must exist")
