"""Regression test for per-action throttle selection on RiggedModelViewSet.

Bug history: get_throttles() only special-cased create / rerig /
rerig_landmarks / status_action, so the public `landmarks` action fell
through to RigListThrottle (30/min). The editor fetches /landmarks/ on
every load and could be throttled on a "public" endpoint.
"""
from django.test import SimpleTestCase

from apps.rigging.views import RiggedModelViewSet
from apps.throttles import AnonUploadThrottle, RigListThrottle, RigUploadThrottle


def _throttles_for(action):
    view = RiggedModelViewSet()
    view.action = action
    return view.get_throttles()


class ThrottleSelectionTests(SimpleTestCase):
    def test_landmarks_action_is_unthrottled(self):
        self.assertEqual(_throttles_for("landmarks"), [])

    def test_status_action_remains_unthrottled(self):
        self.assertEqual(_throttles_for("status_action"), [])

    def test_retrieve_still_uses_rig_list_throttle(self):
        throttles = _throttles_for("retrieve")
        self.assertEqual(len(throttles), 1)
        self.assertIsInstance(throttles[0], RigListThrottle)

    def test_list_still_uses_rig_list_throttle(self):
        throttles = _throttles_for("list")
        self.assertEqual(len(throttles), 1)
        self.assertIsInstance(throttles[0], RigListThrottle)

    def test_create_uses_both_upload_throttles(self):
        throttles = _throttles_for("create")
        self.assertEqual(len(throttles), 2)
        self.assertIsInstance(throttles[0], AnonUploadThrottle)
        self.assertIsInstance(throttles[1], RigUploadThrottle)

    def test_rerig_landmarks_uses_upload_throttle(self):
        throttles = _throttles_for("rerig_landmarks")
        self.assertEqual(len(throttles), 1)
        self.assertIsInstance(throttles[0], RigUploadThrottle)
