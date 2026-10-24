"""Phase 2 — blog_categories in the admin panel (TDD).

- ``seed_categories`` management command: creates the table (if missing)
  and seeds the legacy 1-23 defaults (if empty) — idempotent.
- BlogCategoryAdmin: create (slug auto from name, unique), rename
  (slug stays), delete.
- BlogPost form: the category is a <select> backed by the table, saved
  into the post's blog_category_integer.
"""
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from panel.models import BlogCategory, BlogPost, TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401


class SeedCategoriesTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    def test_seeds_23_defaults_when_empty(self):
        # Fresh table (drop rows first — a previous test class may have seeded).
        BlogCategory.objects.all().delete()
        call_command("seed_categories")
        self.assertEqual(BlogCategory.objects.count(), 23)
        self.assertEqual(BlogCategory.objects.get(id=1).name, "General")
        self.assertEqual(BlogCategory.objects.get(id=23).name, "Crypto")
        cat = BlogCategory.objects.get(id=5)
        self.assertEqual(cat.slug, "python")

    def test_seed_is_idempotent(self):
        BlogCategory.objects.all().delete()
        call_command("seed_categories")
        call_command("seed_categories")
        self.assertEqual(BlogCategory.objects.count(), 23)

    def test_seed_skips_when_table_not_empty(self):
        BlogCategory.objects.all().delete()
        BlogCategory.objects.create(
            id=99, name="Custom", slug="custom", created_at="2026-10-24 10:00:00"
        )
        call_command("seed_categories")
        self.assertEqual(BlogCategory.objects.count(), 1)
        self.assertEqual(BlogCategory.objects.get().name, "Custom")


class CategoryAdminTest(MirrorTestCase):
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
        BlogCategory.objects.all().delete()
        call_command("seed_categories")

    def _add(self, name):
        return self.client.post(
            reverse("admin:panel_blogcategory_add"),
            {"name": name},
        )

    def test_create_generates_slug(self):
        resp = self._add("New Category")
        self.assertEqual(resp.status_code, 302)
        cat = BlogCategory.objects.get(name="New Category")
        self.assertEqual(cat.slug, "new-category")

    def test_create_slug_uniqueness(self):
        # slugify("Vue JS") and slugify("Vue-JS") both reduce to "vue-js"
        # → the second creation must be auto-suffixed.
        self._add("Vue JS")
        resp = self._add("Vue-JS")
        self.assertEqual(resp.status_code, 302)
        slugs = sorted(BlogCategory.objects.filter(name__in=["Vue JS", "Vue-JS"])
                       .values_list("slug", flat=True))
        self.assertEqual(slugs, ["vue-js", "vue-js-2"])

    def test_rename_keeps_slug(self):
        cat = BlogCategory.objects.get(id=1)
        url = reverse("admin:panel_blogcategory_change", args=[cat.pk])
        resp = self.client.post(url, {"name": "General & News", "slug": "general"})
        self.assertEqual(resp.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name, "General & News")
        self.assertEqual(cat.slug, "general")  # unchanged by the rename

    def test_delete_category(self):
        cat = BlogCategory.objects.create(
            id=98, name="Doomed", slug="doomed", created_at="2026-10-24 10:00:00"
        )
        url = reverse("admin:panel_blogcategory_delete", args=[cat.pk])
        resp = self.client.post(url, {"object_id": str(cat.pk)})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(BlogCategory.objects.filter(id=98).exists())


class CategoryI18nTest(MirrorTestCase):
    """Per-language display names (name_en/name_de/name_es): the admin form
    edits them and the values round-trip to the shared table the FastAPI app
    reads for localized category labels."""

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
        BlogCategory.objects.all().delete()
        call_command("seed_categories")

    def test_change_form_exposes_language_fields(self):
        cat = BlogCategory.objects.get(id=22)
        resp = self.client.get(
            reverse("admin:panel_blogcategory_change", args=[cat.pk])
        )
        self.assertEqual(resp.status_code, 200)
        for field in ("name_en", "name_de", "name_es"):
            self.assertContains(resp, f'name="{field}"')

    def test_save_language_names_roundtrip(self):
        cat = BlogCategory.objects.get(id=22)
        url = reverse("admin:panel_blogcategory_change", args=[cat.pk])
        resp = self.client.post(
            url,
            {"name": "KI", "slug": "ki",
             "name_en": "AI", "name_de": "KI", "name_es": "IA"},
        )
        self.assertEqual(resp.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name_en, "AI")
        self.assertEqual(cat.name_de, "KI")
        self.assertEqual(cat.name_es, "IA")

    def test_language_names_optional(self):
        # Leaving the language fields empty stores NULL (the app falls back
        # to the base name) — they must not block saving.
        cat = BlogCategory.objects.get(id=1)
        url = reverse("admin:panel_blogcategory_change", args=[cat.pk])
        resp = self.client.post(url, {"name": "General", "slug": "general"})
        self.assertEqual(resp.status_code, 302)
        cat.refresh_from_db()
        self.assertIsNone(cat.name_en)
        self.assertIsNone(cat.name_de)
        self.assertIsNone(cat.name_es)


class PostCategorySelectTest(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.superuser = get_user_model().objects.create_superuser(
            username="boss", password="boss-pass-123", email="boss@x.com"
        )
        now = "2026-10-24 10:00:00"
        cls.author = TWCUser.objects.create(
            id=uuid.uuid4(), email="a@x.com", username="author",
            password_hash="argon2id-smoke", given_name="A",
            created_at=now, updated_at=now,
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)
        BlogCategory.objects.all().delete()
        call_command("seed_categories")

    def test_add_form_has_category_select_and_saves_id(self):
        data = {
            "title": "Cat Post", "slug": "", "author": str(self.author.id),
            "content": "{}", "published_at": "", "featured_image": "",
            "tags_text": "", "category": "5",
        }
        resp = self.client.post(reverse("admin:panel_blogpost_add"), data)
        self.assertEqual(resp.status_code, 302)
        post = BlogPost.objects.get(title="Cat Post")
        self.assertEqual(post.blog_category_integer, 5)

    def test_blank_category_saves_none(self):
        data = {
            "title": "No Cat", "slug": "", "author": str(self.author.id),
            "content": "{}", "published_at": "", "featured_image": "",
            "tags_text": "", "category": "",
        }
        resp = self.client.post(reverse("admin:panel_blogpost_add"), data)
        self.assertEqual(resp.status_code, 302)
        post = BlogPost.objects.get(title="No Cat")
        self.assertIsNone(post.blog_category_integer)

    def test_change_form_selects_current_category(self):
        BlogPost.objects.create(
            id=uuid.uuid4(), author_id=self.author.id, title="T",
            slug="t-cat", content="{}", blog_category_integer=6,
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        post = BlogPost.objects.get(slug="t-cat")
        resp = self.client.get(
            reverse("admin:panel_blogpost_change", args=[post.pk])
        )
        self.assertEqual(resp.status_code, 200)
        # The category <select> must list the table options and mark 6
        # (JavaScript) as selected for this post.
        self.assertContains(resp, '<option value="6" selected>JavaScript</option>')
        self.assertContains(resp, '<option value="1">General</option>')
