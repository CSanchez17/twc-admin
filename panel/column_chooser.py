"""Generic per-user column chooser for every admin changelist.

2026-10-25: the user asked for the blog-posts column chooser on ALL the
panels (users, comments, reactions, ...) and as a compact dropdown next
to the admin actions row instead of a sprawling checkbox strip.

How it works
------------
- ``ColumnChooserMixin`` adds a ``column_chooser`` template context to
  every changelist. The column list is taken from ``chooser_columns``
  (curated, e.g. blog posts) or AUTO-DERIVED from the model's concrete
  fields — every physical table column, FKs offered both as their human
  column (``author``) and raw id (``author_id``).
- The selection lives in the admin SESSION (per browser) and can be
  bookmarked / shared through the GET params ``?columns=a,b,c`` and
  ``?columns_reset=1`` (the URL wins over the session).
- Long-text / JSON columns render through a truncated plain-text preview
  (auto-generated ``<field>_preview`` methods) so a table cell never
  dumps a whole document.
- Django 5.2 landmines (pinned by the tests): ``changelist_class`` is
  ignored — ``get_changelist`` is overridden; unknown GET params are
  parsed as model lookups by ``ChangeList.get_filters`` (→ 302 ``?e=1``)
  — ``ChooserChangeList`` drops the chooser's params first; the per-model
  changelist template must live at ``admin/<app>/<model>/change_list.html``.
"""
import json
import re

from django.db import models
from django.utils.html import escape
from django.contrib.admin.views.main import ChangeList

CHOOSER_PARAMS = ("columns", "columns_reset")
# Field internal types that would dump a whole document into a table cell.
LONG_TEXT_TYPES = ("TextField", "LongTextField", "JSONField")


class ChooserChangeList(ChangeList):
    """ChangeList that ignores the column-chooser query parameters.

    Every unknown ``?param`` on the changelist URL is parsed as a model
    lookup filter — and an unknown one raises
    ``IncorrectLookupParameters`` (the infamous redirect to ``?e=1``).
    The chooser's ``columns`` / ``columns_reset`` params are UI state,
    not filters, so they are dropped before the lookup parsing.
    """

    def get_filters_params(self, params=None):
        params = super().get_filters_params(params)
        for key in CHOOSER_PARAMS:
            params.pop(key, None)
        return params


def _excerpt(value, limit=120):
    """Escaped plain-text preview of a long-text / JSON field value."""
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)):
        text = ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return escape(text) or "—"


class ColumnChooserMixin:
    """Column-chooser capability for a ModelAdmin.

    Mixin ordering: ``class XAdmin(ColumnChooserMixin, admin.ModelAdmin)``.

    Class attributes:
    - ``chooser_columns``: curated ``[(key, label), …]``. ``None`` →
      auto-derived from the model's concrete fields.
    - ``chooser_defaults``: the keys shown until the user picks. ``None``
      → the current ``list_display`` entries that are real chooser keys
      (custom method columns keep showing in the default view but are not
      selectable — the chooser is about DB columns).
    - ``chooser_display``: ``{key: method_name}`` for columns that render
      through a preview method instead of the raw field.
    - ``chooser_locked``: keys always visible (e.g. the post ``title``,
      which carries the row's only link to the change form).
    """

    chooser_columns = None
    chooser_defaults = None
    chooser_display = {}
    chooser_locked = ()

    # ── column catalogue ──────────────────────────────────────────────────

    def _chooser_columns(self):
        if self.chooser_columns:
            return tuple(self.chooser_columns)
        cols = []
        for field in self.model._meta.concrete_fields:
            if field.primary_key:
                continue
            label = str(field.verbose_name) or field.name
            if field.get_internal_type() == "ForeignKey":
                cols.append((field.name, label.title() or field.name))
                cols.append((field.attname, f"{label} ID".title()))
            else:
                cols.append((field.name, label.title() or field.name))
        return tuple(cols)

    def _chooser_keys(self):
        return {key for key, _label in self._chooser_columns()}

    def _chooser_default_keys(self):
        if self.chooser_defaults:
            return list(self.chooser_defaults)
        display = list(self.list_display) if self.list_display else []
        picked = [k for k in display if k in self._chooser_keys()]
        if not picked:  # list_display is all custom methods
            picked = [key for key, _label in self._chooser_columns()[:8]]
        return picked

    # ── session / URL state ───────────────────────────────────────────────

    def _chooser_session_key(self):
        return f"panel_{self.model._meta.label_lower}_columns"

    def _chooser_apply_params(self, request):
        key = self._chooser_session_key()
        if "columns_reset" in request.GET:
            request.session[key] = self._chooser_default_keys()
        elif "columns" in request.GET:
            valid = self._chooser_keys()
            picked = [
                k.strip() for k in request.GET["columns"].split(",")
                if k.strip() in valid
            ]
            for locked in self.chooser_locked:
                if locked not in picked:
                    picked.insert(0, locked)
            request.session[key] = picked or self._chooser_default_keys()

    # ── rendering ─────────────────────────────────────────────────────────

    def _display_name(self, key):
        """The name the changelist resolves for a chosen column: the
        preview method when one is registered, the raw field otherwise
        (FK attnames like ``author_id`` resolve fine in Django)."""
        if key in self.chooser_display:
            return self.chooser_display[key]
        try:
            field = self.model._meta.get_field(key)
        except Exception:
            return key
        if field.get_internal_type() in LONG_TEXT_TYPES:
            return f"{key}_preview"
        return key

    def _ensure_preview_methods(self):
        """Attach a truncated-preview callable to every long-text/JSON
        column that has no registered preview (idempotent)."""
        for key, label in self._chooser_columns():
            if key in self.chooser_display or hasattr(self, f"{key}_preview"):
                continue
            try:
                field = self.model._meta.get_field(key)
            except Exception:
                continue
            if field.get_internal_type() not in LONG_TEXT_TYPES:
                continue

            def preview(obj, _key=key):
                return _excerpt(getattr(obj, _key, None))

            preview.__name__ = f"{key}_preview"
            preview.short_description = label
            setattr(self, f"{key}_preview", preview)

    def get_changelist(self, request, **kwargs):
        """Django 5.2 hardcodes the stock ChangeList in ModelAdmin —
        the documented ``changelist_class`` attr is not consulted."""
        return ChooserChangeList

    def get_list_display(self, request):
        selected = request.session.get(self._chooser_session_key())
        if not selected:
            return self.list_display
        kept = [key for key in selected if key in self._chooser_keys()]
        for locked in self.chooser_locked:
            if locked not in kept:
                kept.insert(0, locked)
        if not kept:
            return self.list_display
        return tuple(self._display_name(key) for key in kept)

    def changelist_view(self, request, extra_context=None):
        self._ensure_preview_methods()
        self._chooser_apply_params(request)
        if extra_context is None:
            extra_context = {}
        selected = (
            request.session.get(self._chooser_session_key())
            or self._chooser_default_keys()
        )
        extra_context["column_chooser"] = {
            "items": [
                (key, label, key in selected, key in self.chooser_locked)
                for key, label in self._chooser_columns()
            ],
            "selected": len(selected),
            "total": len(self._chooser_columns()),
        }
        return super().changelist_view(request, extra_context)
