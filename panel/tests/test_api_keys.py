"""API keys in the panel — issuance, one-time display, rotation.

The panel (this repo) is the UI that ISSUES api_keys rows; the FastAPI
app owns the schema and verifies the keys (X-API-Key). Security contract
under test:

- A new key's plaintext is shown EXACTLY ONCE (the issuance page right
  after creation / rotation). It never appears in the list, the change
  form, or anywhere re-fetchable: only the SHA-256 digest is stored.
- Rotation produces a brand-new secret; the old one stops working the
  moment the row's hash changes.
"""
import hashlib
import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from panel.models import APIKey, TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401


def _make_owner(username: str) -> TWCUser:
    now = "2026-10-25T00:00:00"
    return TWCUser(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@keys.test",
        role="user",
        is_active=True,
        is_email_confirmed=True,
        created_at=now,
        updated_at=now,
    )


class APIKeyModelTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    def test_issue_returns_plaintext_and_row(self):
        owner = _make_owner("issuer1")
        owner.save()
        key, plaintext = APIKey.issue(owner, name="ci-key", scope="write")

        assert plaintext.startswith("twc_")
        assert len(plaintext) == 4 + 40  # twc_ + token_hex(20)
        assert key.key_hash == hashlib.sha256(plaintext.encode()).hexdigest()
        assert key.key_prefix == plaintext[:12]
        assert key.scope == "write"
        assert key.is_active is True
        assert key.created_at is not None
        # The plaintext itself is nowhere on the row.
        for field in ("name", "key_prefix", "key_hash"):
            assert plaintext not in str(getattr(key, field))

    def test_issue_keys_are_unique(self):
        owner = _make_owner("issuer2")
        owner.save()
        _, p1 = APIKey.issue(owner, name="a")
        _, p2 = APIKey.issue(owner, name="b")
        assert p1 != p2


class APIKeyAdminTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = get_user_model().objects.create_superuser(
            username="keyboss", password="key-pass-123", email="keyboss@x.com"
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.owner = _make_owner("keyowner")
        self.owner.save()

    def _add_post(self, **extra):
        data = {
            "name": extra.get("name", "integration"),
            "owner": str(self.owner.id),
            "scope": extra.get("scope", "read"),
            "expires_at": "",
        }
        data.update(extra)
        return self.client.post(
            reverse("admin:panel_apikey_add"), data, follow=True
        )

    def test_add_view_issues_key_and_shows_plaintext_once(self):
        resp = self._add_post()
        assert resp.status_code == 200
        body = resp.content.decode()
        issued = APIKey.objects.filter(name="integration").latest("created_at")
        # The one-time issuance page shows the full plaintext...
        import re

        shown = re.search(r"twc_[0-9a-f]{40}", body)
        assert shown is not None
        plaintext = shown.group(0)
        # ...and the DB holds only the digest, never the secret.
        assert issued.key_hash == hashlib.sha256(plaintext.encode()).hexdigest()
        assert issued.key_prefix == plaintext[:12]
        row_text = str(APIKey.objects.get(pk=issued.pk))
        assert plaintext not in row_text

    def test_revisiting_add_result_never_shows_secret_again(self):
        """The issuance page is one-shot: the change form has no secret."""
        self._add_post(name="oneshot")
        issued = APIKey.objects.filter(name="oneshot").latest("created_at")
        import re

        change = self.client.get(
            reverse("admin:panel_apikey_change", args=[issued.pk])
        ).content.decode()
        secret = re.search(r"twc_[0-9a-f]{40}", change)
        assert secret is None

    def test_change_form_never_shows_plaintext(self):
        key, plaintext = APIKey.issue(self.owner, name="reusable")
        resp = self.client.get(reverse("admin:panel_apikey_change", args=[key.pk]))
        body = resp.content.decode()
        assert plaintext not in body
        assert key.key_prefix in body

    def test_changelist_never_shows_secrets(self):
        key, plaintext = APIKey.issue(self.owner, name="in-list")
        resp = self.client.get(reverse("admin:panel_apikey_changelist"))
        body = resp.content.decode()
        assert "in-list" in body
        assert key.key_prefix in body
        assert plaintext not in body
        assert key.key_hash not in body

    def test_rotate_action_reissues_secret(self):
        key, old_plaintext = APIKey.issue(self.owner, name="rotating")
        old_hash = key.key_hash
        resp = self.client.post(
            reverse("admin:panel_apikey_changelist"),
            {"action": "rotate_key", "_selected_action": [str(key.pk)]},
            follow=True,
        )
        assert resp.status_code == 200
        key.refresh_from_db()
        assert key.key_hash != old_hash
        body = resp.content.decode()
        assert old_plaintext not in body
        import re

        shown = re.search(r"twc_[0-9a-f]{40}", body)
        assert shown is not None
        assert shown.group(0) != old_plaintext
        assert key.key_hash == hashlib.sha256(shown.group(0).encode()).hexdigest()

    def test_rotate_requires_exactly_one_key(self):
        k1, _ = APIKey.issue(self.owner, name="r1")
        k2, _ = APIKey.issue(self.owner, name="r2")
        h1, h2 = k1.key_hash, k2.key_hash

        # Two selected: rejected, nothing rotates.
        resp = self.client.post(
            reverse("admin:panel_apikey_changelist"),
            {"action": "rotate_key", "_selected_action": [str(k1.pk), str(k2.pk)]},
            follow=True,
        )
        k1.refresh_from_db()
        k2.refresh_from_db()
        assert k1.key_hash == h1 and k2.key_hash == h2

        # Zero selected: rejected.
        resp = self.client.post(
            reverse("admin:panel_apikey_changelist"),
            {"action": "rotate_key", "_selected_action": []},
            follow=True,
        )
        assert resp.status_code == 200

    def test_deactivate_action(self):
        key, _ = APIKey.issue(self.owner, name="deact")
        assert key.is_active is True
        self.client.post(
            reverse("admin:panel_apikey_changelist"),
            {"action": "deactivate_keys", "_selected_action": [str(key.pk)]},
            follow=True,
        )
        key.refresh_from_db()
        assert key.is_active is False

    def test_key_owner_gone_does_not_break_changelist(self):
        """Deleting a site user must not 500 the key list (FK cascade)."""
        key, _ = APIKey.issue(self.owner, name="orphan")
        TWCUser.objects.filter(pk=self.owner.pk).delete()
        resp = self.client.get(reverse("admin:panel_apikey_changelist"))
        assert resp.status_code == 200
        assert not APIKey.objects.filter(pk=key.pk).exists()
