"""Test harness for the shared-schema mirror.

The panel shares the app's local test DB (``test_db.sqlite`` at the app
repo root — the same file the app's pytest suite owns; see
``twc_project/settings_test.py``). The mirror models are managed=False:
the FastAPI app owns the schema, so there is NO hand-maintained table list
here. Normal path: the app's suite already created the tables and
``setUpModule`` is a no-op. If the panel's suite runs against a fresh or
empty shared file, the schema is initialized once — from the app's own
SQLAlchemy models (the single source of truth).

Run the panel's tests with ``--keepdb`` so Django treats the shared file
as opaque (never creates, migrates or deletes it).
"""
import os
import sys

from django.db import connection
from django.test import TestCase

from twc_project.settings import REPO_ROOT


def ensure_shared_test_schema() -> None:
    """No-op when the app's schema is already in the shared test DB.

    Otherwise create it from the app's own models (``modern_twc``). This
    runs at module-import time, OUTSIDE TestCase's transaction — the SQLite
    schema editor cannot run inside an active transaction, so a class-level
    setUpClass would fail with NotSupportedError.
    """
    if "users" in set(connection.introspection.table_names()):
        return
    app_dir = str(REPO_ROOT / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    # Mirror the app's own test bootstrap (tests/conftest.py): the models
    # read env vars at import time, so pin the test environment first.
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_db.sqlite")
    from modern_twc.db.base import Base  # noqa: E402
    import modern_twc.models  # noqa: E402,F401  (registers all ORM metadata)
    # A throwaway engine on the same file: Django's DBAPI connection is
    # not a SQLAlchemy engine, and closing it releases any held lock.
    connection.close()
    from sqlalchemy import create_engine  # noqa: E402

    from twc_project.settings_test import SHARED_TEST_DB  # noqa: E402

    engine = create_engine(f"sqlite:///{SHARED_TEST_DB}")
    Base.metadata.create_all(engine)
    engine.dispose()


def setUpModule(module=None) -> None:  # noqa: N802 (unittest protocol)
    """unittest hook — import this into each test module's namespace."""
    ensure_shared_test_schema()


class MirrorTestCase(TestCase):
    """Plain TestCase over the shared test DB.

    TestCase's transactional rollback isolates each test; committed seed
    rows left by the app's suite may exist, so tests must scope their
    assertions to the rows they create.
    """
