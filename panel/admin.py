"""Admin for the shared twc database.

- ``TWCUserAdmin``  → create/edit users; passwords hashed with Argon2id
                      (argon2-cffi, same library the FastAPI app verifies
                      with) so a user created here logs straight into the app.
- ``VisitAdmin``    → who / when / where / which-blog page views.
- ``BlogPostAdmin`` → manage posts.
- ``BlogCommentAdmin`` → moderate comments.
- Phase 1 (2026-10-24, CRUD plan):
  - ``MediaFileAdmin``       → upload registry (full CRUD).
  - ``NotificationAdmin``    → list / mark read / delete.
  - ``ContactMessageAdmin``  → moderate contact-form submissions.
  - ``ChatRoomAdmin``        → create/edit/close chat rooms.
- Payments / x402 / contact-email ledger / reactions / schancoin →
  read-only ledgers (viewable, never writable).
"""
import re
import uuid

from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.text import slugify

from .models import (
    AnalyticsEvent,
    BlogCategory,
    BlogComment,
    BlogPost,
    BlogReaction,
    ChatRoom,
    ContactEmailSend,
    ContactMessage,
    MediaFile,
    Notification,
    Payment,
    SchancoinBlock,
    SchancoinTransaction,
    SchancoinWallet,
    TWCUser,
    X402Payment,
)
from .column_chooser import ColumnChooserMixin, ChooserChangeList
from .security import hash_password

ROLE_CHOICES = [
    ("user", "user"),
    ("moderator", "moderator"),
    ("admin", "admin"),
]


# ── Blog posts changelist: column chooser ───────────────────────────────────
# Every physical column of ``blog_posts`` is selectable in the posts
# overview: author_id through the ``author`` FK and the camelCase
# ``BlogCategoryInteger`` through its snake_case model field. The default
# keeps the historical eight-column overview; each user's selection lives
# in the admin session (per browser) and can be shared via the
# bookmarkable ``?columns=…`` query string.
ALL_POST_COLUMNS = (
    ("legacy_id", "Post ID"),
    ("title", "Title"),
    ("slug", "Slug"),
    ("author", "Author"),
    ("author_id", "Author UUID"),
    ("author_legacy_id", "Author ID (legacy)"),
    ("visibility", "Visibility"),
    ("is_published", "Published"),
    ("view_count", "Views"),
    ("published_at", "Published at"),
    ("created_at", "Created"),
    ("updated_at", "Updated"),
    ("blog_category_integer", "Category ID"),
    ("featured_image", "Featured image"),
    ("summary", "Summary"),
    ("tags", "Tags"),
    ("content", "Content"),
    ("id", "UUID"),
)
DEFAULT_POST_COLUMNS = (
    "title", "legacy_id", "slug", "author", "visibility",
    "is_published", "view_count", "created_at",
)
# Chooser keys that render through a preview method (the raw fields are
# longtext/JSON — dumping them whole into a table cell would be unusable).
POST_COLUMN_DISPLAY = {
    "summary": "summary_preview",
    "tags": "tags_preview",
    "content": "content_preview",
}


# ── Users ───────────────────────────────────────────────────────────────────


class TWCUserAdminForm(forms.ModelForm):
    password = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Hashed with Argon2id — the FastAPI app verifies it directly.",
    )

    class Meta:
        model = TWCUser
        fields = [
            "username",
            "email",
            "password",
            "role",
            "is_active",
            "is_email_confirmed",
            "given_name",
            "surname",
            "birthday",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # change form: password is an optional reset
            self.fields["password"].required = False
            self.fields["password"].help_text = (
                "Leave blank to keep the current password."
            )


@admin.register(TWCUser)
class TWCUserAdmin(ColumnChooserMixin, admin.ModelAdmin):
    form = TWCUserAdminForm
    list_display = ("username", "email", "role", "is_active", "is_email_confirmed", "created_at")
    list_filter = ("role", "is_active", "is_email_confirmed")
    search_fields = ("username", "email", "given_name", "surname")
    ordering = ("-created_at",)

    fieldsets = (
        (None, {"fields": ("username", "email", "password", "role", "is_active", "is_email_confirmed")}),
        ("Profile", {"fields": ("given_name", "surname", "birthday")}),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at", "legacy_user_id"),
        }),
    )
    readonly_fields = ("created_at", "updated_at", "legacy_user_id")

    actions = ["mark_active", "mark_inactive", "mark_confirmed"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.id = uuid.uuid4()
            now = timezone.now()
            obj.created_at = now
            obj.updated_at = now
        else:
            obj.updated_at = timezone.now()
        password = form.cleaned_data.get("password")
        if password:
            # Raw argon2id (no Django prefix) — the FastAPI app verifies it.
            obj.password_hash = hash_password(password)
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark selected users as active")
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected users as inactive")
    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Mark selected users' email as confirmed")
    def mark_confirmed(self, request, queryset):
        queryset.update(is_email_confirmed=True)


# ── Visits (analytics_events) ───────────────────────────────────────────────


@admin.register(AnalyticsEvent)
class VisitAdmin(ColumnChooserMixin, admin.ModelAdmin):
    """Page views: who (user or session), when, where (ip/country), which page."""

    list_display = (
        "created_at",
        "visitor",
        "path",
        "post_slug",
        "country",
        "ip",
        "status_code",
        "user_agent",
    )
    list_filter = ("event_type", "created_at")
    date_hierarchy = "created_at"
    search_fields = ("user__username", "user__email", "session_id")
    readonly_fields = ("id", "event_type", "user", "session_id", "extra_metadata", "created_at")
    ordering = ("-created_at",)
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def visitor(self, obj):
        if obj.user:
            return escape(obj.user.username)
        return f"anónimo {escape(obj.session_id or '')[:8]}"

    visitor.admin_order_field = "user_id"
    visitor.short_description = "Quién"

    @staticmethod
    def _meta(obj) -> dict:
        return obj.extra_metadata or {}

    def path(self, obj):
        return self._meta(obj).get("path", "")

    path.short_description = "Página"

    def post_slug(self, obj):
        return self._meta(obj).get("post_slug", "")

    post_slug.short_description = "Blog"

    def country(self, obj):
        return self._meta(obj).get("country", "")

    country.short_description = "País"

    def ip(self, obj):
        return self._meta(obj).get("ip", "")

    ip.short_description = "IP"

    def status_code(self, obj):
        return self._meta(obj).get("status", "")

    status_code.short_description = "HTTP"

    def user_agent(self, obj):
        return escape((self._meta(obj).get("user_agent") or "")[:80])

    user_agent.short_description = "User-Agent"


# ── Blog posts ──────────────────────────────────────────────────────────────


class BlogPostAdminForm(forms.ModelForm):
    """Tags are stored on the post as a JSON list, but edited here as a
    comma-separated string (what a human actually types). The slug may be
    left blank — it is generated from the title (with -2, -3… suffixes to
    stay unique) in ``BlogPostAdmin.save_model``. The category is a
    <select> over the blog_categories table (saved as the post's
    ``BlogCategoryInteger``)."""

    tags_text = forms.CharField(
        label="Tags",
        required=False,
        help_text="Comma-separated, e.g. 'python, fastapi'. Stored as a JSON list.",
        widget=forms.TextInput(attrs={"placeholder": "python, fastapi"}),
    )
    category = forms.ModelChoiceField(
        label="Category",
        queryset=BlogCategory.objects.all(),
        required=False,
        empty_label="— (no category)",
        help_text="From the Categories section; stored as the post's category id.",
    )

    class Meta:
        model = BlogPost
        fields = [
            "title", "slug", "author", "visibility", "is_published",
            "published_at", "content", "summary", "featured_image",
            "tags_text",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Leave blank to generate it from the title."
        if self.instance.pk and self.instance.tags:
            self.fields["tags_text"].initial = ", ".join(self.instance.tags)
        if self.instance.pk and self.instance.blog_category_integer:
            self.fields["category"].initial = self.instance.blog_category_integer

    def clean_visibility(self):
        """Blank stays at the model default — never save an empty level
        (the app's audience gate only knows the four canonical values)."""
        value = (self.cleaned_data.get("visibility") or "").strip().lower()
        return value or "public"

    def clean_tags_text(self):
        raw = self.cleaned_data.get("tags_text") or ""
        seen, out = set(), []
        for part in raw.split(","):
            tag = part.strip().lower()
            if tag and tag not in seen:
                seen.add(tag)
                out.append(tag)
        return out


@admin.register(BlogPost)
class BlogPostAdmin(ColumnChooserMixin, admin.ModelAdmin):
    form = BlogPostAdminForm
    # Overview: the historical eight columns. Every other DB column can be
    # switched on per user through the column chooser in the changelist
    # (curated labels in ALL_POST_COLUMNS).
    list_display = DEFAULT_POST_COLUMNS
    chooser_columns = ALL_POST_COLUMNS
    chooser_defaults = DEFAULT_POST_COLUMNS
    chooser_display = POST_COLUMN_DISPLAY
    chooser_locked = ("title",)
    list_filter = ("is_published", "visibility", "blog_category_integer")
    search_fields = ("title", "slug", "legacy_id")
    readonly_fields = (
        "id", "legacy_id", "author_id", "view_count", "created_at",
        "updated_at", "featured_image_thumb",
    )
    ordering = ("-created_at",)

    def get_queryset(self, request):
        # LEFT-join the author: this dev DB has posts whose author was deleted,
        # so a non-select_related lazy load would raise DoesNotExist mid-render.
        return super().get_queryset(request).select_related("author")

    def _excerpt(self, value, limit=120):
        """Plain-text preview of a longtext/JSON field for a table cell."""
        text = re.sub(r"<[^>]+>", " ", value or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > limit:
            text = text[:limit] + "…"
        return escape(text) or "—"

    def summary_preview(self, obj):
        return self._excerpt(obj.summary)

    summary_preview.short_description = "Summary"

    def content_preview(self, obj):
        return self._excerpt(obj.content)

    content_preview.short_description = "Content"

    def tags_preview(self, obj):
        return self._excerpt(", ".join(obj.tags or []))

    tags_preview.short_description = "Tags"

    def save_model(self, request, obj, form, change):
        now = timezone.now()
        if not change:
            obj.id = uuid.uuid4()
        obj.created_at = getattr(obj, "created_at", None) or now
        obj.updated_at = now
        obj.tags = form.cleaned_data.get("tags_text") or None
        # Category select → the post's BlogCategoryInteger (or None).
        chosen = form.cleaned_data.get("category")
        obj.blog_category_integer = chosen.id if chosen else None
        # Blank slug → derive it from the title, auto-suffixing -2, -3… to
        # stay unique. An EXPLICIT slug is kept as-is: if it collides, the
        # form's own unique validation rejects it (standard admin behavior).
        if not obj.slug:
            base = slugify(obj.title) or "post"
            candidate, n = base, 1
            while BlogPost.objects.filter(slug=candidate).exclude(pk=obj.pk).exists():
                n += 1
                candidate = f"{base}-{n}"
            obj.slug = candidate
        super().save_model(request, obj, form, change)

    def featured_image_thumb(self, obj):
        url = obj.featured_image or ""
        if url.startswith(("http://", "https://")):
            return format_html(
                '<img src="{}" style="max-width:320px;max-height:200px" alt="featured image"/>',
                escape(url),
            )
        return escape(url) or "—"

    featured_image_thumb.short_description = "Featured image"

    fieldsets = (
        (None, {
            "fields": (
                "title", "slug", "author", "legacy_id",
                "visibility", "is_published", "published_at", "category",
            ),
        }),
        ("Content", {
            "fields": ("content", "summary", "featured_image", "featured_image_thumb", "tags_text"),
        }),
        ("System", {"classes": ("collapse",), "fields": ("id", "view_count", "created_at", "updated_at")}),
    )


# ── Categories ──────────────────────────────────────────────────────────────


@admin.register(BlogCategory)
class BlogCategoryAdmin(ColumnChooserMixin, admin.ModelAdmin):
    """The blog_categories table (seeded by ``manage.py seed_categories``).

    The slug is generated from the name at creation and then frozen: it is
    the category's stable identifier, so renaming the name keeps the slug.
    Deleting a category does not touch posts — they keep their integer id,
    and the FastAPI read path falls back to the legacy name / 'General'.
    """

    list_display = ("id", "name", "name_en", "name_de", "name_es", "slug", "created_at")
    search_fields = ("name", "name_en", "name_de", "name_es", "slug")
    ordering = ("id",)

    def get_readonly_fields(self, request, obj=None):
        # The slug is auto-generated at creation and frozen afterwards; id
        # and created_at are never edited here.
        return ("id", "slug", "created_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_at = timezone.now()
            base = slugify(obj.name) or "category"
            candidate, n = base, 2
            while BlogCategory.objects.filter(slug=candidate).exists():
                candidate = f"{base}-{n}"
                n += 1
            obj.slug = candidate
        super().save_model(request, obj, form, change)


# ── Comments ────────────────────────────────────────────────────────────────


def _post_ref_cell(post_id, post=None):
    """Post column for comment/reaction changelists: the title links to the
    live post (new tab) and the /blog/<legacy_id> (or the slug for modern
    posts) is shown next to it — a bare title is not enough to tell which
    post a comment or reaction belongs to.

    ``post`` is the select_related'd parent when available — the queryset
    only runs when the FK is genuinely missing."""
    if post is None:
        post = BlogPost.objects.filter(id=post_id).first()
    if post is None:
        return escape(str(post_id))
    ref = f"/blog/{post.legacy_id}" if post.legacy_id is not None else post.slug
    return format_html(
        '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a> '
        '<span class="muted">{}</span>',
        ref, escape(post.title), escape(ref),
    )


@admin.register(BlogComment)
class BlogCommentAdmin(ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("created_at", "post_title", "author", "is_approved", "excerpt")
    list_filter = ("is_approved",)
    search_fields = ("content", "post__title", "author__username")
    readonly_fields = ("id", "post_id", "author_id", "created_at", "updated_at")
    ordering = ("-created_at",)
    actions = ["approve_comments", "reject_comments"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("post", "author")

    def save_model(self, request, obj, form, change):
        now = timezone.now()
        if not change:
            obj.id = uuid.uuid4()
            obj.created_at = now
            obj.updated_at = now
        else:
            obj.updated_at = now
        super().save_model(request, obj, form, change)

    def post_title(self, obj):
        return _post_ref_cell(obj.post_id, obj.post)

    post_title.short_description = "Post"

    def excerpt(self, obj):
        plain = re.sub(r"<[^>]+>", "", obj.content or "")
        return escape(plain[:100])

    excerpt.short_description = "Comentario"

    @admin.action(description="Approve selected comments")
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)

    @admin.action(description="Reject selected comments")
    def reject_comments(self, request, queryset):
        queryset.update(is_approved=False)


# ── Payments (read-only ledgers) ────────────────────────────────────────────


@admin.register(Payment)
class PaymentAdmin(ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("created_at", "user", "amount", "currency", "provider", "status")
    list_filter = ("provider", "status", "currency")
    search_fields = ("user__username", "user__email", "provider_ref")
    readonly_fields = [f.name for f in Payment._meta.fields]
    ordering = ("-created_at",)
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


@admin.register(X402Payment)
class X402PaymentAdmin(ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("created_at", "short_tx", "payer", "amount", "network", "endpoint")
    list_filter = ("network", "x402_version")
    search_fields = ("tx_hash", "payer", "endpoint")
    readonly_fields = [f.name for f in X402Payment._meta.fields]
    ordering = ("-created_at",)
    actions = None

    def short_tx(self, obj):
        return f"0x{obj.tx_hash[:10]}…"

    short_tx.short_description = "Tx"


# ── Phase 1 (2026-10-24): content & ops CRUD ────────────────────────────────


def _stamp(obj, change: bool, with_updated: bool = False) -> None:
    """Fill the ids/timestamps the FastAPI app would have server-defaulted."""
    now = timezone.now()
    if not change:
        obj.id = uuid.uuid4()
        obj.created_at = now
    if with_updated:
        obj.updated_at = now


@admin.register(MediaFile)
class MediaFileAdmin(ColumnChooserMixin, admin.ModelAdmin):
    """Upload registry — the bytes live in the uploads volume, this is the
    DB record (name, mime, size, checksum, category)."""

    list_display = (
        "original_name", "stored_name", "category", "mime_type", "size",
        "uploader", "created_at",
    )
    list_filter = ("category", "mime_type")
    search_fields = ("original_name", "stored_name", "checksum", "uploader__username")
    readonly_fields = ("id", "checksum", "created_at")
    actions = None
    ordering = ("-created_at",)
    fieldsets = (
        (None, {
            "fields": (
                "original_name", "stored_name", "mime_type", "size",
                "category", "uploader",
            ),
        }),
        ("System", {
            "classes": ("collapse",),
            "fields": ("id", "checksum", "created_at"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("uploader")

    def save_model(self, request, obj, form, change):
        _stamp(obj, change)
        super().save_model(request, obj, form, change)


@admin.register(Notification)
class NotificationAdmin(ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("created_at", "user", "type", "title", "is_read", "expires_at")
    list_filter = ("type", "is_read")
    search_fields = ("title", "message", "user__username", "user__email")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)
    actions = ["mark_read", "mark_unread"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def save_model(self, request, obj, form, change):
        _stamp(obj, change)
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark selected notifications as read")
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)

    @admin.action(description="Mark selected notifications as unread")
    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)


@admin.register(ContactMessage)
class ContactMessageAdmin(ColumnChooserMixin, admin.ModelAdmin):
    """Contact-form submissions — moderate: resolve / reopen / delete."""

    list_display = ("created_at", "name", "email", "subject", "is_resolved")
    list_filter = ("is_resolved",)
    search_fields = ("name", "email", "subject", "message")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)
    actions = ["resolve_messages", "reopen_messages"]

    def save_model(self, request, obj, form, change):
        _stamp(obj, change)
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark selected messages as resolved")
    def resolve_messages(self, request, queryset):
        queryset.update(is_resolved=True)

    @admin.action(description="Reopen selected messages")
    def reopen_messages(self, request, queryset):
        queryset.update(is_resolved=False)


@admin.register(ChatRoom)
class ChatRoomAdmin(ColumnChooserMixin, admin.ModelAdmin):
    """Durable chat rooms. The daily job clears non-default rooms; deleting
    one here just removes the record (messages are ephemeral)."""

    list_display = ("name", "is_default", "created_by", "created_at", "refreshed_at")
    list_filter = ("is_default",)
    search_fields = ("name",)
    readonly_fields = ("id", "created_by", "created_at", "refreshed_at")
    ordering = ("-created_at",)
    actions = None

    def save_model(self, request, obj, form, change):
        if not change:
            _stamp(obj, change)
            obj.refreshed_at = obj.created_at
        super().save_model(request, obj, form, change)


# ── Phase 1 read-only ledgers ───────────────────────────────────────────────


class _ReadOnlyMixin:
    """Viewable in the admin, never writable — even for superusers.

    (has_*_permission are METHODS on ModelAdmin — a bool attribute would
    shadow them and crash with "'bool' object is not callable".)"""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BlogReaction)
class BlogReactionAdmin(_ReadOnlyMixin, ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("created_at", "post_title", "user", "reaction_type")
    list_filter = ("reaction_type",)
    search_fields = ("post__title", "user__username")
    readonly_fields = [f.name for f in BlogReaction._meta.fields]
    ordering = ("-created_at",)
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("post", "user")

    def post_title(self, obj):
        return _post_ref_cell(obj.post_id, obj.post)

    post_title.short_description = "Post"


@admin.register(ContactEmailSend)
class ContactEmailSendAdmin(_ReadOnlyMixin, ColumnChooserMixin, admin.ModelAdmin):
    """Rate-limit ledger (1 contact email per IP per 30 days) — append-only
    by design, so the admin is view-only."""

    list_display = ("created_at", "ip", "sender_email")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    search_fields = ("ip", "sender_email")
    readonly_fields = [f.name for f in ContactEmailSend._meta.fields]
    ordering = ("-created_at",)
    actions = None


@admin.register(SchancoinWallet)
class SchancoinWalletAdmin(_ReadOnlyMixin, ColumnChooserMixin, admin.ModelAdmin):
    """Wallet/key metadata — balances are derived by the coin service and
    must never be edited from the panel."""

    list_display = ("address", "balance", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("address",)
    readonly_fields = [f.name for f in SchancoinWallet._meta.fields]
    ordering = ("-created_at",)
    actions = None


@admin.register(SchancoinBlock)
class SchancoinBlockAdmin(_ReadOnlyMixin, ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("index", "short_hash", "previous_hash", "nonce", "difficulty",
                    "timestamp", "is_valid")
    list_filter = ("is_valid",)
    search_fields = ("hash", "previous_hash")
    readonly_fields = [f.name for f in SchancoinBlock._meta.fields]
    ordering = ("-index",)
    actions = None

    def short_hash(self, obj):
        return f"0x{obj.hash[:12]}…"

    short_hash.short_description = "Hash"


@admin.register(SchancoinTransaction)
class SchancoinTransactionAdmin(_ReadOnlyMixin, ColumnChooserMixin, admin.ModelAdmin):
    list_display = ("created_at", "short_tx", "sender", "receiver", "amount",
                    "status", "is_coinbase")
    list_filter = ("status", "is_coinbase")
    search_fields = ("tx_hash", "sender", "receiver")
    readonly_fields = [f.name for f in SchancoinTransaction._meta.fields]
    ordering = ("-created_at",)
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("block")

    def short_tx(self, obj):
        return f"0x{obj.tx_hash[:12]}…"

    short_tx.short_description = "Tx"
