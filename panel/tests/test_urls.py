"""Entry-point URLs: what the README documents must be what actually serves.

Regression: the README pointed users at http://127.0.0.1:8000/admin/ but
the admin site is mounted at the ROOT (urls.py: ``path("", admin.site.urls)``)
— the documented entry 404'd. These tests pin the real entry points AND
verify every URL the README documents resolves to a 200, so docs and code
can never drift apart silently again.
"""
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401

README = Path(__file__).resolve().parents[2] / "README.md"


def _readme_documented_paths() -> list[str]:
    """Every `http://127.0.0.1:8000<rest>` path documented in the README."""
    text = README.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"`http://127.0.0.1:8000(/[^`]*)`", text)]


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
