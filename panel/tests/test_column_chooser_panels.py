"""Column chooser on EVERY panel (2026-10-25).

The user rejected the sprawling checkbox strip on the posts overview and
asked for:

1. the chooser as a DROPSHOW next to the admin actions row
   ("Acciones … seleccionados"), and
2. the same capability on every mask — users, comments, reactions, ...

The chooser is generic: ``ColumnChooserMixin`` auto-derives the column
list from the model's physical fields, one shared template renders the
dropdown (``cc-toggle`` / ``cc-panel``), and the per-user selection stays
in the admin session (bookmarkable ``?columns=…`` / ``?columns_reset=1``).
"""
import uuid

from django.contrib.auth import get_user_model
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
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F402

# Every model with a changelist in the panel.
ALL_PANELS = [
    TWCUser, AnalyticsEvent, BlogPost, BlogCategory, BlogComment,
    Payment, X402Payment, MediaFile, Notification, ContactMessage,
    ChatRoom, BlogReaction, ContactEmailSend, SchancoinWallet,
    SchancoinBlock, SchancoinTransaction,
]


class ChooserOnEveryPanel(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.superuser = get_user_model().objects.create_superuser(
            username="chooserboss", password="chooser-pass-123",
            email="chooser@x.com",
        )
        now = "2026-10-25 10:00:00"
        cls.author = TWCUser.objects.create(
            id=uuid.uuid4(), email="chooser-author@x.com",
            username="chooserauthor", password_hash="argon2id-smoke",
            given_name="Cho", created_at=now, updated_at=now,
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def url(self, model, query=""):
        return reverse(
            f"admin:panel_{model._meta.model_name}_changelist"
        ) + query

    def make_comment(self, content):
        post = BlogPost.objects.create(
            id=uuid.uuid4(), author_id=self.author.id,
            title=f"chooser probe {uuid.uuid4().hex[:8]}",
            slug=f"chooser-probe-{uuid.uuid4().hex[:8]}",
            content="{}", is_published=True, visibility="public",
            created_at="2026-10-25 10:00:00",
            updated_at="2026-10-25 10:00:00",
        )
        return BlogComment.objects.create(
            id=uuid.uuid4(), post_id=post.id, author_id=self.author.id,
            content=content, is_approved=True,
            created_at="2026-10-25 10:00:00",
            updated_at="2026-10-25 10:00:00",
        )

    # ── the dropdown exists on every panel ────────────────────────────────

    def test_every_panel_renders_the_chooser_dropdown(self):
        for model in ALL_PANELS:
            resp = self.client.get(self.url(model))
            self.assertEqual(resp.status_code, 200, model)
            html = resp.content.decode()
            self.assertIn(
                "cc-toggle", html,
                f"{model.__name__}: no chooser dropdown button",
            )
            self.assertIn(
                "cc-panel", html,
                f"{model.__name__}: no chooser dropdown panel",
            )

    def test_every_panel_chooser_lists_all_physical_columns(self):
        for model in ALL_PANELS:
            html = self.client.get(self.url(model)).content.decode()
            for f in model._meta.concrete_fields:
                if f.primary_key:
                    continue
                # FK: the human column (name) must be offered; the raw id
                # column (attname) is a bonus, also offered.
                self.assertIn(
                    f'value="{f.name}"', html,
                    f"{model.__name__}.{f.name} missing from the chooser",
                )
                if f.get_internal_type() == "ForeignKey":
                    self.assertIn(
                        f'value="{f.attname}"', html,
                        f"{model.__name__}.{f.attname} missing from the chooser",
                    )

    # ── selection flow on the other panels ────────────────────────────────

    def test_comments_panel_url_selection_changes_the_columns(self):
        self.make_comment("hola")
        html = self.client.get(
            self.url(BlogComment, "?columns=created_at,post_id")
        ).content.decode()
        self.assertIn("Created at", html)
        self.assertIn("Post id", html)

    def test_selection_is_per_model_not_shared(self):
        # One row so the results table (and its headers) renders.
        self.make_comment("hola")
        # Choose username+email on the USERS panel, then open the COMMENTS
        # panel: it must keep its own default display, not the users pick.
        self.client.get(self.url(TWCUser, "?columns=username,email"))
        html = self.client.get(self.url(BlogComment)).content.decode()
        self.assertNotRegex(html, r">Username</a>")
        self.assertNotRegex(html, r">Email</a>")
        # Non-sortable headers wrap the label in a <span> inside the th.
        self.assertRegex(html, r"<span>Post</span>")

    def test_reset_restores_defaults_on_users_panel(self):
        self.client.get(self.url(TWCUser, "?columns=username"))
        html = self.client.get(
            self.url(TWCUser, "?columns_reset=1")
        ).content.decode()
        # Sortable headers wrap their label in a <a> — match the link text.
        self.assertRegex(html, r">Role</a>")
        self.assertRegex(html, r">Is active</a>")

    def test_long_text_columns_use_a_truncated_preview(self):
        blob = "A" * 400
        self.make_comment(blob)
        html = self.client.get(
            self.url(BlogComment, "?columns=author,content")
        ).content.decode()
        self.assertNotIn(blob[:300], html)
        self.assertIn("…", html)

    def test_unknown_columns_are_filtered_on_any_panel(self):
        resp = self.client.get(
            self.url(TWCUser, "?columns=username,no_such_column")
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "?e=1")

    def test_chooser_script_waits_for_dom_readiness(self):
        """The inline JS lives in <head> (parsed BEFORE the body): binding
        the listeners at script-execution time finds no .cc-toggle elements
        and the "Columnas" button silently does nothing (verified live
        2026-10-25). It must bind on DOMContentLoaded."""
        html = self.client.get(self.url(BlogPost)).content.decode()
        self.assertRegex(
            html, r'document\.addEventListener\("DOMContentLoaded"'
        )
