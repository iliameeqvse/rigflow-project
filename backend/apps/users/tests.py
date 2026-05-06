from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import UserProfile


User = get_user_model()


class RegisterCreatesProfileTests(APITestCase):
    """Registration must create a UserProfile and return JWT tokens."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("register")

    def test_register_returns_access_refresh_user(self):
        resp = self.client.post(
            self.url,
            {"email": "alice@example.com", "username": "alice", "password": "supersecret"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(body["user"]["email"], "alice@example.com")
        self.assertEqual(body["user"]["username"], "alice")

    def test_register_creates_user_profile(self):
        self.client.post(
            self.url,
            {"email": "bob@example.com", "username": "bob", "password": "supersecret"},
            format="json",
        )
        user = User.objects.get(email="bob@example.com")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        # Default plan should be 'free'.
        self.assertEqual(user.profile.plan, UserProfile.PLAN_FREE)


class CreateUserViaORMAlsoCreatesProfileTests(APITestCase):
    """Users created outside the register endpoint (admin, createsuperuser,
    fixtures) must still get a profile via the post_save signal."""

    def test_orm_create_triggers_signal(self):
        user = User.objects.create_user(
            email="carol@example.com", username="carol", password="x" * 10,
        )
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
