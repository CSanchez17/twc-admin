"""Test harness for the shared-schema mirror.

The mirror models are ``managed = False`` (the FastAPI app owns the schema),
so Django's test runner — which has no migrations for them — never creates
their tables on the test database. Tables are created once per test module,
in ``setUpModule`` (module import happens OUTSIDE TestCase's transaction —
the SQLite schema editor cannot run inside an active transaction, so a
class-level setUpClass would fail with NotSupportedError). ``setUpModule``
is imported into each test module's namespace so unittest calls it.

Test DB: in-memory sqlite (see ``twc_project/settings_test.py`` — tests
never touch the live MySQL).
"""
from django.db import connection
from django.test import TestCase

from panel import models as M

# Creation order matters: parents before children (FK constraints).
MIRROR_TABLES = [
    M.TWCUser,
    M.BlogCategory,
    M.BlogPost,
    M.BlogComment,
    M.BlogReaction,
    M.MediaFile,
    M.Notification,
    M.ContactMessage,
    M.ContactEmailSend,
    M.Payment,
    M.X402Payment,
    M.AnalyticsEvent,
    M.ChatRoom,
    M.SchancoinWallet,
    M.SchancoinBlock,
    M.SchancoinTransaction,
]


def create_mirror_tables() -> None:
    """Idempotently create every mirror table on the current connection."""
    with connection.schema_editor() as editor:
        existing = set(connection.introspection.table_names())
        for model in MIRROR_TABLES:
            if model._meta.db_table not in existing:
                editor.create_model(model)


def setUpModule(module=None) -> None:  # noqa: N802 (unittest protocol)
    """unittest hook — import this into each test module's namespace."""
    create_mirror_tables()


class MirrorTestCase(TestCase):
    """Plain TestCase — the tables already exist (setUpModule created them)."""
