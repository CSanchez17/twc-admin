"""Route Django's internal apps to the panel-local auth database.

The shared twc database (``default``) must only ever see the app's own
tables (users, blog_posts, analytics_events, …). Django's internal tables
(auth_user, django_session, django_content_type, …) live in ``admin_auth``
instead, so the production DB is never modified by the panel itself.
"""

INTERNAL_APPS = frozenset({"admin", "auth", "contenttypes", "sessions"})


class PanelAuthRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label in INTERNAL_APPS:
            return "admin_auth"
        return "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label in INTERNAL_APPS:
            return "admin_auth"
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label in INTERNAL_APPS or obj2._meta.app_label in INTERNAL_APPS:
            return True
        return obj1._meta.app_label == obj2._meta.app_label or True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in INTERNAL_APPS:
            return db == "admin_auth"
        if app_label == "panel":
            # All panel models are managed=False mirrors — never migrate them.
            return False
        return db == "default"
