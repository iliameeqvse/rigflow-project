from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.users.models import UserProfile

from .models import RiggedModel


User = get_user_model()


def _glb_bytes(size: int = 64) -> bytes:
    """Tiny stand-in payload — the actual file is never read in these tests
    because we mock the Celery dispatch out."""
    return b"\x00" * size


def _landmarks():
    return {
        "chin": [0.0, 1.84, 0.0],
        "groin": [0.0, 1.0, 0.0],
        "left_shoulder": [0.2, 1.64, 0.0],
        "right_shoulder": [-0.2, 1.64, 0.0],
        "left_elbow": [0.5, 1.64, 0.05],
        "right_elbow": [-0.5, 1.64, 0.05],
        "left_wrist": [0.8, 1.64, 0.0],
        "right_wrist": [-0.8, 1.64, 0.0],
        "left_hip": [0.1, 1.0, 0.0],
        "right_hip": [-0.1, 1.0, 0.0],
        "left_knee": [0.1, 0.5, 0.0],
        "right_knee": [-0.1, 0.5, 0.0],
        "left_ankle": [0.1, 0.0, 0.0],
        "right_ankle": [-0.1, 0.0, 0.0],
        "left_heel": [0.1, 0.0, -0.1],
        "right_heel": [-0.1, 0.0, -0.1],
    }


class AuthenticatedUploadAttachesToOwnProfileTests(APITestCase):
    """Authenticated rig uploads must attach to the user's own profile,
    not the shared demo@rigflow.local fallback."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", username="owner", password="x" * 10,
        )
        # Signal should have populated this; assert as part of the contract.
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse("rig-list")

    @mock.patch("apps.rigging.views.auto_rig_model")
    def test_upload_attaches_to_own_profile(self, mock_task):
        upload = SimpleUploadedFile("model.glb", _glb_bytes(), content_type="model/gltf-binary")

        resp = self.client.post(self.url, {"file": upload, "name": "Mine"}, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.content)

        rig = RiggedModel.objects.get(name="Mine")
        self.assertEqual(rig.user.user, self.user)
        self.assertNotEqual(rig.user.user.email, "demo@rigflow.local")
        mock_task.delay.assert_called_once()

    @mock.patch("apps.rigging.views.auto_rig_model")
    def test_upload_creates_profile_for_legacy_user(self, mock_task):
        """Legacy users that pre-date the post_save signal still upload to
        their own profile — the view get_or_creates one on the fly."""
        UserProfile.objects.filter(user=self.user).delete()
        upload = SimpleUploadedFile("model.glb", _glb_bytes(), content_type="model/gltf-binary")

        resp = self.client.post(self.url, {"file": upload, "name": "Legacy"}, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.content)

        rig = RiggedModel.objects.get(name="Legacy")
        self.assertEqual(rig.user.user, self.user)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())
        mock_task.delay.assert_called_once()


class RigUploadSizeCapTests(APITestCase):
    """The backend must reject uploads bigger than MAX_RIG_UPLOAD_MB before
    creating the RiggedModel row, so oversize files don't leak into media/."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="big@example.com", username="big", password="x" * 10,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse("rig-list")

    @mock.patch("apps.rigging.views.auto_rig_model")
    def test_oversize_upload_rejected_with_400(self, mock_task):
        # Just over the 100 MB cap — SimpleUploadedFile keeps it in memory,
        # but it's only a few hundred bytes of `bytes()` repetition for the
        # Content-Length header during the test.
        from apps.rigging.views import MAX_RIG_UPLOAD_BYTES
        oversized = SimpleUploadedFile(
            "huge.glb",
            b"\x00" * (MAX_RIG_UPLOAD_BYTES + 1),
            content_type="model/gltf-binary",
        )
        resp = self.client.post(self.url, {"file": oversized, "name": "Huge"}, format="multipart")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("too large", resp.json()["error"])
        self.assertFalse(RiggedModel.objects.filter(name="Huge").exists())
        mock_task.delay.assert_not_called()


class LandmarkRerigValidationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="landmarks@example.com", username="landmarks", password="x" * 10,
        )
        self.profile = UserProfile.objects.get(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.rig = RiggedModel.objects.create(
            user=self.profile,
            name="Rig",
            original_file=SimpleUploadedFile("model.glb", _glb_bytes(), content_type="model/gltf-binary"),
            original_format="glb",
            status=RiggedModel.STATUS_DONE,
        )
        self.url = reverse("rig-rerig-landmarks", kwargs={"id": self.rig.id})

    @mock.patch("apps.rigging.views.auto_rig_model_with_landmarks")
    def test_rerig_landmarks_requires_full_14_key_payload(self, mock_task):
        landmarks = _landmarks()
        del landmarks["left_elbow"]

        resp = self.client.post(self.url, {"landmarks": landmarks}, format="json")

        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("left_elbow", resp.json()["error"])
        self.rig.refresh_from_db()
        self.assertEqual(self.rig.status, RiggedModel.STATUS_DONE)
        mock_task.delay.assert_not_called()

    @mock.patch("apps.rigging.views.auto_rig_model_with_landmarks")
    def test_rerig_landmarks_rejects_non_numeric_coordinates(self, mock_task):
        landmarks = _landmarks()
        landmarks["chin"] = [0, "bad", 0]

        resp = self.client.post(self.url, {"landmarks": landmarks}, format="json")

        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("non-numeric", resp.json()["error"])
        self.rig.refresh_from_db()
        self.assertEqual(self.rig.status, RiggedModel.STATUS_DONE)
        mock_task.delay.assert_not_called()
