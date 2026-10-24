"""Entry-point URLs: what the README documents must be what actually serves.

Regression: the README pointed users at http://127.0.0.1:8000/admin/ but
the admin site is mounted at the ROOT (urls.py: ``path("", admin.site.urls)``)
— the documented entry 404'd. These tests pin the real entry points AND
verify every URL the README documents resolves to a 200, so docs and code
can never drift apart silently again.

Second regression (2026-10-24): TWCUserAdmin was written but never
``@admin.register``-ed, so the site's real users had NO section in the
panel. ``test_every_managed_model_is_registered`` pins that.
"""
import re
from pathlib import Path

from django.contrib import admin as dj_admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from panel.models import (
    AnalyticsEvent,
    BlogCategory,
    BlogComment,
    BlogPost,
    BlogReaction,
    ChatRoom,
    ContactEmailSend,
    ContactMessage,
    MediaFile,
    Notification,
    Payment,
    SchancoinBlock,
    SchancoinTransaction,
    SchancoinWallet,
    TWCUser,
    X402Payment,
)
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401

import uuid

README = Path(__file__).resolve().parents[2] / "README.md"


def _readme_documented_paths() -> list[str]:
    """Every `http://127.0.0.1:8805<rest>` path documented in the README."""
    text = README.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"`http://127.0.0.1:8805(/[^`]*)`", text)]


# Every shared-schema model that has a ModelAdmin in panel/admin.py MUST be
# registered — an unregistered admin is invisible in the panel (the TWCUser
# bug: site users had no section even though TWCUserAdmin existed).
MANAGED_MODELS = [
    TWCUser,
    AnalyticsEvent,
    BlogPost,
    BlogCategory,
    BlogComment,
    BlogReaction,
    ContactEmailSend,
    ContactMessage,
    ChatRoom,
    MediaFile,
    Notification,
    Payment,
    X402Payment,
    SchancoinWallet,
    SchancoinBlock,
    SchancoinTransaction,
]


class AdminRegistrationTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    def test_every_managed_model_is_registered(self):
        missing = [m.__name__ for m in MANAGED_MODELS if m not in dj_admin.site._registry]
        self.assertEqual(missing, [], f"unregistered models: {missing}")

    def test_twcuser_changelist_lists_the_site_users(self):
        user_model = get_user_model()
        user_model.objects.create_superuser(
            username="boss", password="boss-pass-123", email="boss@x.com"
        )
        now = "2026-10-24 10:00:00"
        site_users = []
        for n in ("alice", "bob"):
            site_users.append(
                TWCUser.objects.create(
                    id=uuid.uuid4(), email=f"{n}@example.com", username=n,
                    password_hash="argon2id:x", given_name=n.title(),
                    created_at=now, updated_at=now,
                )
            )
        self.client.force_login(user_model.objects.get(username="boss"))
        resp = self.client.get(reverse("admin:panel_twcuser_changelist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice@example.com")
        self.assertContains(resp, "bob@example.com")


class DocumentedUrlsTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.superuser = get_user_model().objects.create_superuser(
            username="boss", password="boss-pass-123", email="boss@x.com"
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def test_admin_index_is_served_at_root(self):
        # The admin site is mounted at "/" — NOT "/admin/".
        self.assertEqual(reverse("admin:index"), "/")
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_admin_login_is_reachable(self):
        self.assertEqual(reverse("admin:login"), "/login/")

    def test_every_documented_url_serves_200(self):
        paths = _readme_documented_paths()
        self.assertTrue(paths, "README must document at least one 127.0.0.1:8000 URL")
        for path in paths:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200, f"{path} returned {resp.status_code}")
