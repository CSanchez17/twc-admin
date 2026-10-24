"""One-shot: create ``blog_categories`` (if missing) + seed legacy 1-23.

The FastAPI app reads this table for category names (Django admin is the
system of record). Idempotent: the table is only created when absent and
the seed only runs when the table is empty, so re-running never clobbers
admin-curated categories.

Usage:
    manage.py seed_categories
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from panel.models import BlogCategory

# Same ids/names as the FastAPI app's LEGACY_CATEGORY_MAP fallback
# (app/modern_twc/repositories/post.py) — pre-existing posts reference
# these ids and must keep displaying their names after the first seed.
LEGACY_CATEGORIES = {
    1: "General", 2: "C", 3: "C++", 4: "C# (.Net)", 5: "Python",
    6: "JavaScript", 7: "NodeJS", 8: "Vue.js", 9: "JQuery",
    10: "Bootstrap", 11: "Angular", 12: "ReactJs", 13: "Django",
    14: "TypeScript", 15: "Java", 16: "SQL", 17: "PHP",
    18: "VisualBasic", 19: "HTML-CSS", 20: "Unity", 21: "UnrealEngine",
    22: "KI", 23: "Crypto",
}


def slugify_name(name: str) -> str:
    """URL-ish slug for a category name (stable identifier — kept on rename)."""
    s = name.lower().replace(" ", "-").replace("#", "")
    for ch in ("(", ")", "."):
        s = s.replace(ch, "")
    return s or "category"


class Command(BaseCommand):
    help = "Create blog_categories (if missing) and seed the legacy 1-23 (if empty)."

    def handle(self, *args, **options):
        existing = set(connection.introspection.table_names())
        if "blog_categories" not in existing:
            with connection.schema_editor() as editor:
                editor.create_model(BlogCategory)
            self.stdout.write("created table blog_categories")
        else:
            self.stdout.write("table blog_categories already exists")

        if BlogCategory.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"seed skipped — table already has "
                    f"{BlogCategory.objects.count()} rows"
                )
            )
            return

        now = timezone.now()
        created = []
        for cat_id, name in LEGACY_CATEGORIES.items():
            created.append(
                BlogCategory(id=cat_id, name=name,
                             slug=slugify_name(name), created_at=now)
            )
        BlogCategory.objects.bulk_create(created)
        self.stdout.write(
            self.style.SUCCESS(f"seeded {len(created)} categories")
        )
