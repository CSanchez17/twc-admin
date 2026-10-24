"""BlogPostAdmin improvements (phase 1, plan item 3):
- slug auto-generated from the title when left blank (unique: -2, -3…),
- tags edited as a comma-separated string (stored as the JSON list),
- featured image rendered as a thumbnail on the change form.
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from panel.models import BlogPost, TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401


class BlogPostAdminBase(MirrorTestCase):
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

    def add_post(self, **overrides):
        data = {
            "title": "Post Title",
            "slug": "",
            "author": str(self.author.id),
            "content": '{"blocks": []}',
            "published_at": "",
            "featured_image": "",
            "tags_text": "",
        }
        data.update(overrides)
        return self.client.post(reverse("admin:panel_blogpost_add"), data)


class SlugAutogenerationTest(BlogPostAdminBase):
    def test_slug_generated_from_title(self):
        resp = self.add_post(title="Hola Mundo")
        self.assertEqual(resp.status_code, 302)
        post = BlogPost.objects.get(title="Hola Mundo")
        self.assertEqual(post.slug, "hola-mundo")

    def test_slug_uniqueness(self):
        self.add_post(title="Same")  # auto slug "same"
        resp = self.add_post(title="Same")  # auto slug "same-2"
        self.assertEqual(resp.status_code, 302)
        # Scoped to this test's posts — the shared test DB may hold
        # committed seed posts from the app's suite.
        slugs = sorted(
            BlogPost.objects.filter(title="Same").values_list("slug", flat=True)
        )
        self.assertEqual(slugs, ["same", "same-2"])

    def test_empty_title_slug_fallback(self):
        resp = self.add_post(title="!!!")
        self.assertEqual(resp.status_code, 302)
        post = BlogPost.objects.get(title="!!!")
        self.assertTrue(post.slug)


class TagsInputTest(BlogPostAdminBase):
    def test_comma_input_stored_as_json_list(self):
        resp = self.add_post(tags_text="Python,  FastAPI ,python,")
        self.assertEqual(resp.status_code, 302)
        post = BlogPost.objects.get(slug="post-title")
        self.assertEqual(post.tags, ["python", "fastapi"])

    def test_blank_tags_store_none_or_empty(self):
        resp = self.add_post(tags_text="")
        self.assertEqual(resp.status_code, 302)
        # Scoped by title — the shared test DB may hold seed posts.
        post = BlogPost.objects.get(title="Post Title")
        self.assertFalse(post.tags)

    def test_change_form_shows_comma_list(self):
        BlogPost.objects.create(
            id=uuid.uuid4(), author_id=self.author.id, title="T",
            slug="t-1", content="{}", tags=["alpha", "beta"],
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        post = BlogPost.objects.get(slug="t-1")
        resp = self.client.get(
            reverse("admin:panel_blogpost_change", args=[post.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alpha, beta")


class FeaturedImageThumbTest(BlogPostAdminBase):
    def test_thumb_rendered_for_http_url(self):
        BlogPost.objects.create(
            id=uuid.uuid4(), author_id=self.author.id, title="T",
            slug="t-2", content="{}", featured_image="https://x.test/a.png",
            created_at="2026-10-24 10:00:00", updated_at="2026-10-24 10:00:00",
        )
        post = BlogPost.objects.get(slug="t-2")
        resp = self.client.get(
            reverse("admin:panel_blogpost_change", args=[post.pk])
        )
        self.assertContains(resp, '<img src="https://x.test/a.png"')
