"""Test settings for the panel.

The panel shares ONE local test DB with the FastAPI app: ``test_db.sqlite``
at the app repo root — the same file the app's pytest suite creates and
owns (see ``tests/conftest.py`` in the app repo). Prod works the same way,
just with the prod DB: the panel's ``default`` alias points at whatever the
app points at.

``TEST["NAME"]`` pins the runner to that shared file and ``MIGRATE: False``
plus ``--keepdb`` keep it OPAQUE: the runner must not create, migrate or
delete it. The panel's mirror models are managed=False — the app owns the
schema; when the shared file is fresh, ``panel.tests.base`` initializes it
from the app's own SQLAlchemy models.

Run with:
    DJANGO_SETTINGS_MODULE=twc_project.settings_test \
        python manage.py test panel --keepdb
"""
from .settings import *  # noqa: F401,F403

SHARED_TEST_DB = str(REPO_ROOT / "test_db.sqlite")  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SHARED_TEST_DB,
        "TEST": {"NAME": SHARED_TEST_DB, "MIGRATE": False},
    },
    # Panel-internal auth DB (Django's own tables) — stays local to the
    # panel, in-memory under test.
    "admin_auth": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}
