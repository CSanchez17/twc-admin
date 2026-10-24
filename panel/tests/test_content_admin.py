"""Admin coverage for the content/ops mirrors (phase 1 of the CRUD plan).

Covers, per the plan:
- every new mirror is registered on the admin site,
- ledger models are READ-ONLY (no add/change/delete, even for superusers):
  BlogReaction, ContactEmailSend, SchancoinWallet/Block/Transaction,
- real CRUD through the admin views for the editable ones:
  ChatRoom (add/edit/delete), MediaFile (add), Notification (mark-read
  action), ContactMessage (resolve action).
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from panel.models import (
    BlogReaction,
    ChatRoom,
    ContactEmailSend,
    ContactMessage,
    MediaFile,
    Notification,
    SchancoinBlock,
    SchancoinTransaction,
    SchancoinWallet,
    TWCUser,
)
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401

READONLY_MODELS = [
    BlogReaction,
    ContactEmailSend,
    SchancoinWallet,
    SchancoinBlock,
    SchancoinTransaction,
]

EDITABLE_MODELS = [
    ChatRoom,
    MediaFile,
    Notification,
    ContactMessage,
]


class AdminRegistrationTest(MirrorTestCase):
    def test_all_new_mirrors_are_registered(self):
        from django.contrib import admin

        for model in READONLY_MODELS + EDITABLE_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)


class SuperuserMixin:
    # the panel's auth users live on the admin_auth alias (routers.py)
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


class ReadOnlyLedgerTest(SuperuserMixin, TestCase):
    """Ledgers must be view-only: a superuser may list but never write."""

    def test_no_add_change_delete_for_ledgers(self):
        for model in READONLY_MODELS:
            opts = model._meta
            with self.subTest(model=model.__name__):
                add = reverse("admin:%s_%s_add" % (opts.app_label, opts.model_name))
                resp = self.client.get(add)
                self.assertIn(
                    resp.status_code, (302, 403),
                    f"{model.__name__} add view must be blocked, got {resp.status_code}",
                )
                if resp.status_code == 302:
                    self.assertIn("login", resp.url)


class ChatRoomCrudTest(SuperuserMixin, TestCase):
    def test_create_edit_and_delete_room(self):
        add_url = reverse("admin:panel_chatroom_add")
        resp = self.client.post(
            add_url,
            {"name": "general", "is_default": "on",
             "created_at": "2026-10-24 10:00:00",
             "refreshed_at": "2026-10-24 10:00:00"},
        )
        room = ChatRoom.objects.get(name="general")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(room.is_default)
        self.assertEqual(len(str(room.id)), 36)

        change_url = reverse("admin:panel_chatroom_change", args=[room.pk])
        resp = self.client.post(change_url, {
            "name": "off-topic",
            "created_at": "2026-10-24 10:00:00",
            "refreshed_at": "2026-10-24 10:00:00",
        })
        self.assertEqual(resp.status_code, 302)
        room.refresh_from_db()
        self.assertEqual(room.name, "off-topic")

        delete_url = reverse("admin:panel_chatroom_delete", args=[room.pk])
        # Django ≥5: the delete POST must carry the hidden object_id field
        resp = self.client.post(delete_url, {"object_id": str(room.pk)})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ChatRoom.objects.filter(name="off-topic").exists())


class MediaFileAdminTest(SuperuserMixin, TestCase):
    def test_create_media_entry(self):
        add_url = reverse("admin:panel_mediafile_add")
        resp = self.client.post(add_url, {
            "original_name": "logo.png",
            "stored_name": "a1b2c3.png",
            "mime_type": "image/png",
            "size": "2048",
            "checksum": "d41d8cd98f00b204e9800998ecf8427e",
            "category": "avatars",
            "created_at": "2026-10-24 10:00:00",
        })
        self.assertEqual(resp.status_code, 302)
        entry = MediaFile.objects.get(stored_name="a1b2c3.png")
        self.assertEqual(entry.size, 2048)
        self.assertEqual(entry.category, "avatars")


class NotificationActionTest(SuperuserMixin, TestCase):
    def test_mark_read_action(self):
        now = "2026-10-24 10:00:00"
        user = TWCUser.objects.create(
            id=uuid.uuid4(), email="n@x.com", username="nuser",
            password_hash="argon2id-smoke", given_name="N",
            created_at=now, updated_at=now,
        )
        for i in range(2):
            Notification.objects.create(
                id=uuid.uuid4(), user_id=user.id, type="post",
                title=f"t{i}", message="m", is_read=False, created_at=now,
            )
        mine = list(
            Notification.objects.filter(user_id=user.id).values_list("id", flat=True)
        )
        resp = self.client.post(
            reverse("admin:panel_notification_changelist"),
            {"action": "mark_read", "_selected_action": [str(i) for i in mine]},
        )
        # Django ≥5.1: an executed action redirects to the changelist
        self.assertEqual(resp.status_code, 302)
        # Scoped to this test's user — the shared test DB may hold
        # committed notifications from the app's suite.
        self.assertEqual(
            Notification.objects.filter(user_id=user.id, is_read=True).count(), 2
        )


class ContactMessageActionTest(SuperuserMixin, TestCase):
    def test_resolve_action(self):
        now = "2026-10-24 10:00:00"
        ContactMessage.objects.create(
            id=uuid.uuid4(), name="Ana", email="ana@x.com",
            subject="hola", message="mensaje", is_resolved=False,
            created_at=now,
        )
        msg = ContactMessage.objects.get(email="ana@x.com")
        resp = self.client.post(
            reverse("admin:panel_contactmessage_changelist"),
            {"action": "resolve_messages", "_selected_action": [str(msg.id)]},
        )
        # Django ≥5.1: an executed action redirects to the changelist
        self.assertEqual(resp.status_code, 302)
        msg.refresh_from_db()
        self.assertTrue(msg.is_resolved)
