"""Custom fields for the shared-schema mirror.

``HyphenatedUUIDField`` stores UUIDs in the canonical hyphenated 36-char form
(``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``), which is exactly how the FastAPI
app writes UUIDs into the shared DB. Django's stock ``UUIDField`` persists ``value.hex`` (32-char, no hyphens) on
backends without a native UUID type (our MySQL/PyMySQL), which silently breaks
cross-app lookups and foreign keys (the app generates and matches hyphenated
ids). Reading is unaffected: Django parses both forms back to a UUID.
"""
import uuid

from django.db import models


class HyphenatedUUIDField(models.UUIDField):
    """UUIDField that writes the canonical hyphenated string form."""

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = self.to_python(value)
        return str(value)  # hyphenated, 36 chars — matches the FastAPI app
