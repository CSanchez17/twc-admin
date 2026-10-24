"""Harness smoke test: the mirror tables exist on the test DB and a user
round-trips through the ORM with the hyphenated UUID form (the exact format
the FastAPI app persists — see panel/fields.py)."""
import uuid

from panel.models import TWCUser
from panel.tests.base import MirrorTestCase, setUpModule  # noqa: F401


class SmokeTest(MirrorTestCase):
    def test_mirror_tables_are_materialized(self):
        from django.db import connection

        tables = set(connection.introspection.table_names())
        for model in (TWCUser,):
            self.assertIn(model._meta.db_table, tables)

    def test_user_roundtrip_with_hyphenated_uuid(self):
        uid = uuid.uuid4()
        now = __import__("django.utils.timezone", fromlist=["now"]).now()
        TWCUser.objects.create(
            id=uid,
            email="smoke@example.com",
            username="smoke",
            password_hash="argon2id-v19-smoke",
            given_name="Smoke",
            role="admin",
            created_at=now,
            updated_at=now,
        )
        # stored as the hyphenated 36-char string the FastAPI app writes —
        # a plain cursor returns exactly what the DB holds (no ORM cast)
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute(
                f"SELECT id FROM {TWCUser._meta.db_table} WHERE username='smoke'"
            )
            stored = cur.fetchone()[0]
        self.assertEqual(stored, str(uid))
        self.assertIsInstance(stored, str)
        self.assertEqual(len(stored), 36)
        got = TWCUser.objects.get(username="smoke")
        self.assertEqual(got.email, "smoke@example.com")
