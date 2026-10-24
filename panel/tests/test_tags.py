"""Phase 3 — tag management (TDD).

Tags live as JSON arrays on each post (``blog_posts.tags``) — there is no
tags table. The admin panel manages them at the tag level: list every
distinct tag with its post count, rename a tag across all posts (merging
into an existing tag when the target already exists), and delete a tag
from every post.

The manager is a standalone admin page at /admin/tags/ (staff only).
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from panel.models import BlogPost, TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401

NOW = "2026-10-24 10:00:00"


class TagManagerBase(MirrorTestCase):
    databases = {"default", "admin_auth"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.superuser = get_user_model().objects.create_superuser(
            username="boss", password="boss-pass-123", email="boss@x.com"
        )
        cls.plain_user = get_user_model().objects.create_user(
            username="nobody", password="nopass-12345", email="nobody@x.com"
        )
        cls.author = TWCUser.objects.create(
            id=uuid.uuid4(), email="a@x.com", username="author",
            password_hash="argon2id-smoke", given_name="A",
            created_at=NOW, updated_at=NOW,
        )

    def seed_posts(self):
        def mk(slug, tags):
            return BlogPost.objects.create(
                id=uuid.uuid4(), author_id=self.author.id, title=slug.title(),
                slug=slug, content="{}", tags=tags,
                created_at=NOW, updated_at=NOW,
            )
        self.p1 = mk("p1", ["python", "fastapi"])
        self.p2 = mk("p2", ["python", "django"])
        self.p3 = mk("p3", ["fastapi"])
        self.p4 = mk("p4", None)
        self.p5 = mk("p5", [])

    def refresh(self, *posts):
        for p in posts:
            p.refresh_from_db()

    def _url(self):
        return reverse("panel-tags")


class TagListingTest(TagManagerBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)
        self.seed_posts()

    def test_page_lists_distinct_tags_with_counts(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        # Distinct tags only (python on p1+p2, fastapi on p1+p3, django on p2).
        self.assertContains(resp, 'value="python"')
        self.assertContains(resp, 'value="fastapi"')
        self.assertContains(resp, 'value="django"')
        # Counts: two tags on 2 posts, one tag on 1 post.
        self.assertContains(resp, '<td class="count">2</td>')
        self.assertContains(resp, '<td class="count">1</td>')


class TagRenameTest(TagManagerBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)
        self.seed_posts()

    def test_rename_updates_every_post(self):
        resp = self.client.post(self._url(), {
            "action": "rename", "old": "python", "new": "py",
        })
        self.assertEqual(resp.status_code, 302)
        self.refresh(self.p1, self.p2)
        self.assertEqual(sorted(self.p1.tags), ["fastapi", "py"])
        self.assertEqual(sorted(self.p2.tags), ["django", "py"])
        # Untouched post keeps its tags.
        self.refresh(self.p3)
        self.assertEqual(self.p3.tags, ["fastapi"])

    def test_rename_is_case_insensitive_and_normalizes(self):
        resp = self.client.post(self._url(), {
            "action": "rename", "old": "Python", "new": "Py ",
        })
        self.assertEqual(resp.status_code, 302)
        self.refresh(self.p1, self.p2)
        self.assertIn("py", self.p1.tags)
        self.assertIn("py", self.p2.tags)

    def test_rename_merges_into_existing_tag(self):
        # p2 already has both "django" and... make a post with the target:
        BlogPost.objects.create(
            id=uuid.uuid4(), author_id=self.author.id, title="p6",
            slug="p6", content="{}", tags=["py", "django"],
            created_at=NOW, updated_at=NOW,
        )
        p6 = BlogPost.objects.get(slug="p6")
        # Rename django → py: p2 had [python, django] → [python, py];
        # p6 had [py, django] → [py] (no duplicate).
        resp = self.client.post(self._url(), {
            "action": "rename", "old": "django", "new": "py",
        })
        self.assertEqual(resp.status_code, 302)
        self.refresh(self.p2, p6)
        self.assertEqual(self.p2.tags, ["python", "py"])
        self.assertEqual(p6.tags, ["py"])

    def test_rename_blank_target_fails_cleanly(self):
        resp = self.client.post(self._url(), {
            "action": "rename", "old": "python", "new": "   ",
        })
        self.assertIn(resp.status_code, (200, 302))
        self.refresh(self.p1)
        self.assertIn("python", self.p1.tags)  # unchanged


class TagDeleteTest(TagManagerBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)
        self.seed_posts()

    def test_delete_removes_tag_from_every_post(self):
        resp = self.client.post(self._url(), {
            "action": "delete", "old": "fastapi",
        })
        self.assertEqual(resp.status_code, 302)
        self.refresh(self.p1, self.p3)
        self.assertEqual(self.p1.tags, ["python"])
        self.assertEqual(self.p3.tags, [])

    def test_delete_unknown_tag_is_a_noop(self):
        resp = self.client.post(self._url(), {
            "action": "delete", "old": "rust",
        })
        self.assertEqual(resp.status_code, 302)
        self.refresh(self.p1)
        self.assertEqual(self.p1.tags, ["python", "fastapi"])


class TagManagerAccessTest(TagManagerBase):
    def setUp(self):
        super().setUp()
        self.seed_posts()

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.headers["Location"])

    def test_non_staff_is_denied(self):
        self.client.force_login(self.plain_user)
        resp = self.client.get(self._url())
        self.assertIn(resp.status_code, (302, 403))
