"""Blog posts changelist: every DB column available + a per-user column
chooser.

The overview used to show 8 fixed columns; the user asked for ALL columns
present in the ``blog_posts`` table to be available, with the ability to
pick which ones are visible. The selection is per-user (Django session),
applied through ``?columns=a,b,c`` (bookmarkable GET) and a reset link.
"""
import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse

from panel.admin import ALL_POST_COLUMNS, DEFAULT_POST_COLUMNS
from panel.models import BlogComment, BlogPost, TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F402


class ColumnChooserBase(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.superuser = get_user_model().objects.create_superuser(
            username="colboss", password="colboss-pass-123", email="col@x.com"
        )
        now = "2026-10-24 10:00:00"
        cls.author = TWCUser.objects.create(
            id=uuid.uuid4(), email="colauthor@x.com", username="colauthor",
            password_hash="argon2id-smoke", given_name="Col",
            created_at=now, updated_at=now,
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def make_post(self, slug, **overrides):
        data = {
            "id": uuid.uuid4(), "author_id": self.author.id, "content": "{}",
            "created_at": "2026-10-24 10:00:00",
            "updated_at": "2026-10-24 10:00:00",
            "visibility": "public", "is_published": True,
            "title": slug, "slug": slug,
        }
        data.update(overrides)
        return BlogPost.objects.create(**data)

    def effective_columns(self, resp):
        """The list_display the changelist actually rendered for this
        request — ``resp.context`` is one dict per rendered template, so
        walk the captured contexts to the changelist's own."""
        contexts = (
            resp.context
            if isinstance(resp.context, list)
            else [resp.context]
        )
        for ctx in contexts:
            if ctx is not None and "cl" in ctx:
                # "action_checkbox" is prepended by the admin when row
                # actions are enabled — it is not a user-visible column.
                return [
                    name for name in ctx["cl"].list_display
                    if name != "action_checkbox"
                ]
        raise AssertionError("changelist context ('cl') not captured")

    def changelist(self, query=""):
        return self.client.get(
            reverse("admin:panel_blogpost_changelist") + query
        )


class ColumnChooserTest(ColumnChooserBase):
    """The chooser UI and its session-backed selection."""

    def test_every_db_column_is_a_chooser_option(self):
        """All 17 physical columns of blog_posts must be selectable —
        the user asked for 'todas las columnas presentes de la db'."""
        self.make_post("col-a")
        resp = self.changelist()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="cc-wrap"')
        # Every column key must appear as a checkbox value.
        html = resp.content.decode()
        for key, _label in ALL_POST_COLUMNS:
            self.assertIn(
                f'value="{key}"', html,
                msg=f"column {key!r} missing from the chooser",
            )
        # And the chooser covers every physical table column (author_id is
        # covered through the author FK, BlogCategoryInteger through its
        # snake_case model field).
        physical = {
            "id", "author_id", "title", "slug", "content", "summary",
            "tags", "is_published", "published_at", "view_count",
            "created_at", "updated_at", "featured_image", "legacy_id",
            "author_legacy_id", "BlogCategoryInteger", "visibility",
        }
        covered = {key for key, _ in ALL_POST_COLUMNS}
        for col in physical:
            model_key = (
                "author" if col == "author_id" else
                "blog_category_integer" if col == "BlogCategoryInteger" else col
            )
            self.assertIn(model_key, covered,
                          f"physical column {col!r} not selectable")

    def test_default_view_keeps_the_default_columns(self):
        self.make_post("col-b")
        resp = self.changelist()
        self.assertEqual(
            self.effective_columns(resp),
            list(DEFAULT_POST_COLUMNS),
        )

    def test_comments_count_shows_approved_only(self):
        """The Comments column counts APPROVED comments — the number the
        public site shows (pending ones are not public yet)."""
        post = self.make_post("col-comments")
        for approved, text in ((True, "approved"), (False, "pending")):
            BlogComment.objects.create(
                id=uuid.uuid4(), post_id=post.id, author_id=self.author.id,
                content=text, is_approved=approved,
                created_at="2026-10-24 10:00:00",
                updated_at="2026-10-24 10:00:00",
            )
        html = self.changelist().content.decode()
        row = next(
            (chunk for chunk in html.split("<tr") if "col-comments" in chunk),
            None,
        )
        self.assertIsNotNone(row, "row for the probe post not found")
        self.assertRegex(row, r">\s*1\s*</td>")

    def test_apply_param_shows_only_the_selected_columns(self):
        self.make_post("col-c")
        resp = self.changelist("?columns=legacy_id,view_count")
        self.assertEqual(
            self.effective_columns(resp), ["title", "legacy_id", "view_count"],
        )

    def test_selection_persists_in_the_session(self):
        self.make_post("col-d")
        self.changelist("?columns=published_at,slug")
        # A plain navigation afterwards still shows the selection.
        resp = self.changelist()
        self.assertEqual(
            self.effective_columns(resp), ["title", "published_at", "slug"],
        )

    def test_reset_link_restores_the_default_columns(self):
        self.make_post("col-e")
        self.changelist("?columns=slug")
        resp = self.changelist("?columns_reset=1")
        self.assertEqual(
            self.effective_columns(resp),
            list(DEFAULT_POST_COLUMNS),
        )

    def test_unknown_columns_are_filtered_without_crashing(self):
        self.make_post("col-f")
        resp = self.changelist("?columns=title,bogus_column")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.effective_columns(resp), ["title"])

    def test_title_is_always_visible(self):
        """Even an explicit selection without title keeps it: the row's
        only link to the change form would vanish otherwise."""
        self.make_post("col-g")
        resp = self.changelist("?columns=view_count")
        self.assertIn("title", self.effective_columns(resp))

    def test_chooser_marks_the_current_selection(self):
        self.make_post("col-h")
        self.changelist("?columns=legacy_id")
        resp = self.changelist()
        html = resp.content.decode()
        # legacy_id is now checked, the default-only 'view_count' is not.
        self.assertRegex(
            html,
            r'value="legacy_id"\s+checked',
        )
        self.assertNotRegex(
            html,
            r'value="view_count"\s+checked',
        )
        # title is locked (always shown) → disabled checkbox.
        self.assertRegex(
            html,
            r'value="title"\s+[^>]*disabled|value="title"\s+checked\s+[^>]*disabled',
        )


class PostCommentsInlineTest(ColumnChooserBase):
    """The post CHANGE FORM must show the post's comments — 'asi como
    system': a 'Comments' section with who wrote what (author + content
    + moderation state). One join: comments.post_id = post.id."""

    def _change_form(self, post):
        return self.client.get(
            reverse("admin:panel_blogpost_change", args=[post.id])
        )

    def test_comments_section_lists_the_post_comments_with_author(self):
        post = self.make_post("inline-post-a")
        other = TWCUser.objects.create(
            id=uuid.uuid4(), email="inline-b@x.com", username="inlineb",
            password_hash="argon2id-smoke", given_name="B",
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        BlogComment.objects.create(
            id=uuid.uuid4(), post_id=post.id, author_id=other.id,
            content="muy util esta serie", is_approved=True,
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        resp = self._change_form(post)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Comments", html, "the 'Comments' section header is missing")
        self.assertIn("muy util esta serie", html)
        self.assertIn("inlineb", html, "the comment author must be shown")

    def test_only_this_posts_comments_are_shown(self):
        post = self.make_post("inline-post-b")
        stranger = self.make_post("inline-other-post")
        BlogComment.objects.create(
            id=uuid.uuid4(), post_id=stranger.id, author_id=self.author.id,
            content="COMMENT-ONLY-ON-OTHER-POST", is_approved=True,
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        html = self._change_form(post).content.decode()
        self.assertNotIn("COMMENT-ONLY-ON-OTHER-POST", html)

    def test_moderation_state_is_editable_in_the_inline(self):
        post = self.make_post("inline-post-c")
        BlogComment.objects.create(
            id=uuid.uuid4(), post_id=post.id, author_id=self.author.id,
            content="pendiente de moderar", is_approved=False,
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        html = self._change_form(post).content.decode()
        # an is_approved checkbox per comment row (moderate in place)
        self.assertRegex(html, r'name="comments-\d+-is_approved"')

    def test_post_without_comments_shows_the_empty_section(self):
        post = self.make_post("inline-post-d")
        html = self._change_form(post).content.decode()
        self.assertIn("Comments", html)
        # Django renders the empty-form placeholder row — and NO real
        # comment rows (nothing like comments-0-*) for a comment-less post.
        self.assertIn('id="comments-empty"', html)
        self.assertNotIn('name="comments-0-content"', html)
