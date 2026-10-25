# panel/tests/test_user_actions.py
"""Delete-selected action on TWCUser (site users from the real DB).

Regression (2026-10-24): TWCUserAdmin set its own ``actions`` list with
only the mark_* helpers, which OVERRIDES Django's default set and silently
removed ``delete_selected`` — the panel had no way to delete the checked
site users.
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from panel.admin import TWCUserAdmin
from panel.models import TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401


def _make_user(username, active=True):
    now = "2026-10-24T00:00:00"
    return TWCUser(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@probe.test",
        role="user",
        is_active=active,
        is_email_confirmed=True,
        created_at=now,
        updated_at=now,
    )


class DeleteSelectedActionTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = get_user_model().objects.create_superuser(
            username="boss", password="boss-pass-123", email="boss@x.com"
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_delete_selected_is_an_available_action(self):
        """The action dropdown must offer 'delete selected'."""
        from django.contrib import admin as dj_admin

        # A non-empty changelist is required for the action form to render.
        _make_user("probe-present").save()
        request = RequestFactory().get(
            reverse("admin:panel_twcuser_changelist")
        )
        request.user = self.admin
        actions = TWCUserAdmin(TWCUser, dj_admin.site).get_actions(request)
        self.assertIn("delete_selected", actions)
        # ... and it is rendered as an option in the changelist form.
        response = self.client.get(reverse("admin:panel_twcuser_changelist"))
        self.assertContains(response, "delete_selected")

    def test_delete_selected_removes_the_checked_users(self):
        # Unique suffix per run: the shared test DB may hold committed
        # probe-* rows from an earlier (failed) run.
        suffix = uuid.uuid4().hex[:8]
        kept = _make_user(f"probe-{suffix}-kept")
        gone1 = _make_user(f"probe-{suffix}-gone1")
        gone2 = _make_user(f"probe-{suffix}-gone2")
        TWCUser.objects.bulk_create([kept, gone1, gone2])

        url = reverse("admin:panel_twcuser_changelist")
        # Select both probes and run the action; Django shows a
        # confirmation page first.
        response = self.client.post(url, {
            "action": "delete_selected",
            "_selected_action": [str(gone1.id), str(gone2.id)],
        })
        self.assertEqual(response.status_code, 200)
        # Confirm the deletion.
        self.client.post(url, {
            "action": "delete_selected",
            "_selected_action": [str(gone1.id), str(gone2.id)],
            "post": "yes",
        })
        # The shared test DB may hold committed seed rows from the app's
        # suite — assert on the probes, not on an absolute count.
        remaining = list(
            TWCUser.objects.filter(username__startswith=f"probe-{suffix}-")
            .values_list("id", flat=True)
        )
        self.assertEqual(remaining, [kept.id])
        kept.refresh_from_db()
        self.assertTrue(kept.is_active)
