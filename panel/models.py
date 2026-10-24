"""managed=False mirrors of the shared twc database (FastAPI app schema).

Every field maps 1:1 to the SQLAlchemy models in
``app/modern_twc/models/`` — do NOT add fields here without adding them to
the FastAPI side (and vice versa). The panel is the admin UI over this
schema; the FastAPI app remains the system of record.
"""
from django.db import models

from .fields import HyphenatedUUIDField


class TWCUser(models.Model):
    """Mirror of ``modern_twc.models.identity.User`` (table ``users``)."""

    id = HyphenatedUUIDField(primary_key=True)
    legacy_user_id = models.IntegerField(null=True, unique=True)
    email = models.CharField(max_length=320, unique=True)
    username = models.CharField(max_length=64, unique=True)
    password_hash = models.CharField(max_length=512)
    given_name = models.CharField(max_length=128)
    surname = models.CharField(max_length=128, null=True, blank=True)
    birthday = models.DateField(null=True, blank=True)
    role = models.CharField(max_length=32, default="user")
    is_active = models.BooleanField(default=True)
    is_email_confirmed = models.BooleanField(default=False)
    profil_data = models.TextField(null=True, blank=True)
    profil_html_data = models.TextField(null=True, blank=True)
    portfolio_data = models.TextField(null=True, blank=True)  # projects JSON (own column since 2026-10-20)
    # S3 (2026-10-20): contact / profile-card fields
    phrase = models.CharField(max_length=256, null=True, blank=True)
    user_description = models.TextField(null=True, blank=True)
    facebook_link = models.CharField(max_length=512, null=True, blank=True)
    instagram_link = models.CharField(max_length=512, null=True, blank=True)
    twitter_link = models.CharField(max_length=512, null=True, blank=True)
    github_link = models.CharField(max_length=512, null=True, blank=True)
    cellphone = models.CharField(max_length=64, null=True, blank=True)
    skills = models.TextField(null=True, blank=True)
    profil_image = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} <{self.email}>"


class BlogPost(models.Model):
    """Mirror of ``modern_twc.models.content.BlogPost`` (table ``blog_posts``)."""

    id = HyphenatedUUIDField(primary_key=True)
    legacy_id = models.IntegerField(null=True, unique=True)
    author = models.ForeignKey(
        TWCUser, on_delete=models.CASCADE, db_column="author_id", related_name="posts",
        null=True, blank=True,
    )
    author_legacy_id = models.IntegerField(null=True)
    title = models.CharField(max_length=200)
    slug = models.CharField(max_length=200, unique=True)
    content = models.TextField()  # EditorJS JSON
    summary = models.TextField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    view_count = models.IntegerField(default=0)
    featured_image = models.CharField(max_length=512, null=True, blank=True)
    tags = models.JSONField(null=True, blank=True)
    # The physical column is camelCase 'BlogCategoryInteger' in the shared DB.
    # blank=True: the FastAPI app treats it as optional — and the admin form
    # (built from the fieldsets) must not require it.
    blog_category_integer = models.IntegerField(
        null=True, blank=True, db_column="BlogCategoryInteger"
    )
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "blog_posts"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class BlogComment(models.Model):
    """Mirror of ``modern_twc.models.content.BlogComment`` (table ``blog_comments``)."""

    id = HyphenatedUUIDField(primary_key=True)
    post = models.ForeignKey(
        BlogPost, on_delete=models.CASCADE, db_column="post_id", related_name="comments",
        null=True, blank=True,
    )
    author = models.ForeignKey(
        TWCUser, on_delete=models.CASCADE, db_column="author_id", related_name="comments",
        null=True, blank=True,
    )
    parent_id = HyphenatedUUIDField(null=True)
    content = models.TextField()
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "blog_comments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.id} on {self.post_id}"


class AnalyticsEvent(models.Model):
    """Mirror of ``modern_twc.models.content.AnalyticsEvent`` (table ``analytics_events``).

    Page visits are event_type='page_view'; everything interesting
    (path, ip, referrer, user_agent, post_slug, country) lives in
    ``extra_metadata`` JSON.
    """

    id = HyphenatedUUIDField(primary_key=True)
    event_type = models.CharField(max_length=64)
    user = models.ForeignKey(
        TWCUser, on_delete=models.SET_NULL, db_column="user_id", null=True, related_name="visits"
    )
    session_id = models.CharField(max_length=128, null=True, blank=True)
    extra_metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "analytics_events"
        ordering = ["-created_at"]

    def __str__(self):
        meta = self.extra_metadata or {}
        return f"{self.event_type} {meta.get('path', '')} @ {self.created_at:%Y-%m-%d %H:%M}"


class Payment(models.Model):
    """Mirror of ``modern_twc.models.content.Payment`` (table ``payments``)."""

    id = HyphenatedUUIDField(primary_key=True)
    user = models.ForeignKey(
        TWCUser, on_delete=models.CASCADE, db_column="user_id", related_name="payments",
        null=True, blank=True,
    )
    amount = models.IntegerField()  # cents
    currency = models.CharField(max_length=8, default="EUR")
    status = models.CharField(max_length=32, default="pending")
    provider = models.CharField(max_length=64)
    provider_ref = models.CharField(max_length=256, null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} {self.amount}{self.currency} ({self.status})"


class X402Payment(models.Model):
    """Mirror of ``modern_twc.models.x402.X402Payment`` (table ``x402_payments``).

    Append-only ledger of settled x402 (USDC) micro-payments.
    """

    id = HyphenatedUUIDField(primary_key=True)
    tx_hash = models.CharField(max_length=128, unique=True)
    payer = models.CharField(max_length=255, null=True, blank=True)
    endpoint = models.CharField(max_length=512)
    amount = models.CharField(max_length=32)  # micro-USDC
    network = models.CharField(max_length=64, null=True, blank=True)
    x402_version = models.IntegerField(default=2)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "x402_payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"0x{self.tx_hash[:10]}… {self.amount} µUSDC"


class BlogReaction(models.Model):
    """Mirror of ``modern_twc.models.content.BlogReaction`` (table
    ``blog_reactions``). One reaction per (post, user, type) — unique
    constraint ``uq_blog_reactions_post_user_type`` lives on the shared
    schema, not on this mirror."""

    id = HyphenatedUUIDField(primary_key=True)
    post = models.ForeignKey(
        BlogPost, on_delete=models.CASCADE, db_column="post_id", related_name="reactions"
    )
    user = models.ForeignKey(
        TWCUser, on_delete=models.CASCADE, db_column="user_id", related_name="reactions"
    )
    reaction_type = models.CharField(max_length=16)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "blog_reactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reaction_type} by {self.user_id} on {self.post_id}"


class MediaFile(models.Model):
    """Mirror of ``modern_twc.models.content.MediaFile`` (table
    ``media_files``). Uploaded media registry (the bytes live in the
    uploads volume, not the DB)."""

    id = HyphenatedUUIDField(primary_key=True)
    uploader = models.ForeignKey(
        TWCUser, on_delete=models.SET_NULL, db_column="uploader_id",
        related_name="media_files", null=True, blank=True,
    )
    original_name = models.CharField(max_length=512)
    stored_name = models.CharField(max_length=512, unique=True)
    mime_type = models.CharField(max_length=128)
    size = models.IntegerField()
    checksum = models.CharField(max_length=64)
    category = models.CharField(max_length=32)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "media_files"
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name


class Notification(models.Model):
    """Mirror of ``modern_twc.models.content.Notification`` (table
    ``notifications``)."""

    id = HyphenatedUUIDField(primary_key=True)
    user = models.ForeignKey(
        TWCUser, on_delete=models.CASCADE, db_column="user_id", related_name="notifications"
    )
    type = models.CharField(max_length=64)
    title = models.CharField(max_length=256)
    message = models.TextField()
    data = models.JSONField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type}: {self.title} → {self.user_id}"


class ContactMessage(models.Model):
    """Mirror of ``modern_twc.models.content.ContactMessage`` (table
    ``contact_messages``) — contact-form submissions."""

    id = HyphenatedUUIDField(primary_key=True)
    name = models.CharField(max_length=256)
    email = models.CharField(max_length=320)
    subject = models.CharField(max_length=512)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "contact_messages"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} — {self.name}"


class ContactEmailSend(models.Model):
    """Mirror of ``modern_twc.models.content.ContactEmailSend`` (table
    ``contact_email_sends``). Rate-limit ledger: one row per successful
    SMTP delivery (1 send per IP per 30 days). Append-only — read-only in
    the admin."""

    id = HyphenatedUUIDField(primary_key=True)
    ip = models.CharField(max_length=45)
    sender_email = models.CharField(max_length=320)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "contact_email_sends"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ip} → {self.sender_email}"


class ChatRoom(models.Model):
    """Mirror of ``modern_twc.models.chat.ChatRoom`` (table
    ``chat_rooms``). Durable rooms; the daily job clears non-default ones.
    ``created_by`` is the UUID string of the creator (VARCHAR(36) in the
    shared schema, no FK)."""

    id = HyphenatedUUIDField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    is_default = models.BooleanField(default=False)
    created_by = models.CharField(max_length=36, null=True, blank=True)
    created_at = models.DateTimeField()
    refreshed_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "chat_rooms"
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.name}{' (default)' if self.is_default else ''}"


# ── Schancoin (read-only ledgers in the admin) ──────────────────────────────


class SchancoinWallet(models.Model):
    """Mirror of ``modern_twc.models.schancoin.SchancoinWallet`` (table
    ``schancoin_wallets``). Key metadata only — balances are derived by
    the coin service; never edited from the panel."""

    id = HyphenatedUUIDField(primary_key=True)
    address = models.CharField(max_length=256, unique=True)
    public_key = models.TextField()
    balance = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "schancoin_wallets"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.address[:16]}… {self.balance} SCH"


class SchancoinBlock(models.Model):
    """Mirror of ``modern_twc.models.schancoin.SchancoinBlock`` (table
    ``schancoin_blocks``)."""

    id = HyphenatedUUIDField(primary_key=True)
    index = models.IntegerField(unique=True)
    hash = models.CharField(max_length=64, unique=True)
    previous_hash = models.CharField(max_length=64)
    nonce = models.IntegerField(default=0)
    difficulty = models.IntegerField(default=4)
    timestamp = models.DateTimeField()
    merkle_root = models.CharField(max_length=64)
    is_valid = models.BooleanField(default=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "schancoin_blocks"
        ordering = ["-index"]

    def __str__(self):
        return f"#{self.index} 0x{self.hash[:10]}…"


class SchancoinTransaction(models.Model):
    """Mirror of ``modern_twc.models.schancoin.SchancoinTransaction`` (table
    ``schancoin_transactions``)."""

    id = HyphenatedUUIDField(primary_key=True)
    tx_hash = models.CharField(max_length=64, unique=True)
    block = models.ForeignKey(
        SchancoinBlock, on_delete=models.SET_NULL, db_column="block_id",
        related_name="transactions", null=True, blank=True,
    )
    sender = models.CharField(max_length=256)
    receiver = models.CharField(max_length=256)
    amount = models.FloatField()
    signature = models.TextField()
    nonce = models.IntegerField(default=0)
    is_coinbase = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default="pending")
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "schancoin_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"0x{self.tx_hash[:10]}… {self.amount} SCH"
