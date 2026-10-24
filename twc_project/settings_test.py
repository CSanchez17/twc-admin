"""Test settings for the panel.

The panel normally resolves the LIVE shared database from ``config/.env``
(see ``_resolve_database_url`` — it prefers that file over the process
environment on purpose). Tests must NEVER point at the live MySQL, so this
settings module overrides DATABASES with throwaway in-memory sqlite for
both aliases after importing everything else.

Run with:
    DJANGO_SETTINGS_MODULE=twc_project.settings_test \
        python manage.py test panel.tests
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    "admin_auth": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}
