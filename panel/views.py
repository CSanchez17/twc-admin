"""Standalone admin pages (outside the AdminSite).

The tag manager lives at /admin/tags/ — a full page rather than a
ModelAdmin, because tags have no table: they are JSON arrays on each
post (``blog_posts.tags``).
"""
from collections import Counter

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from .models import BlogPost


def _tag_counts() -> Counter:
    """Distinct tag → how many posts carry it (None/empty tags ignored)."""
    counts: Counter = Counter()
    rows = BlogPost.objects.exclude(tags__isnull=True).values_list("tags", flat=True)
    for tags in rows:
        counts.update(set(tags or ()))
    return counts


def _apply_to_posts(transform) -> int:
    """Run ``transform(tags) -> new_tags`` over every tagged post.

    Returns the number of posts whose tags actually changed. Only the
    ``tags`` column is written (update_fields) — nothing else is touched.
    """
    changed = 0
    for post in BlogPost.objects.exclude(tags__isnull=True).only("tags"):
        new_tags = transform(list(post.tags or ()))
        if new_tags != (post.tags or []):
            post.tags = new_tags
            post.save(update_fields=["tags"])
            changed += 1
    return changed


@staff_member_required
def tags_manager(request):
    """GET: list every distinct tag with its post count.

    POST: ``action=rename`` (old → new; merges into the target when it
    already exists, so no duplicate tags) or ``action=delete`` (removes
    the tag from every post). Tags are lowercased on the way in, matching
    how the post editor stores them.
    """
    if request.method == "POST":
        action = request.POST.get("action")
        old = (request.POST.get("old") or "").strip().lower()
        if not old:
            messages.error(request, "Tag vacío — no se hizo nada.")
            return redirect("panel-tags")

        if action == "rename":
            new = (request.POST.get("new") or "").strip().lower()
            if not new:
                messages.error(request, "El nombre nuevo no puede estar vacío.")
            elif new == old:
                messages.info(request, f"“{old}” ya se llama así.")
            else:
                def rename(tags):
                    # Only posts that actually carry the old tag change.
                    if old not in tags:
                        return tags
                    tags = [t for t in tags if t != old]
                    if new not in tags:
                        tags.append(new)
                    return tags

                n = _apply_to_posts(rename)
                messages.success(
                    request, f"“{old}” renombrado a “{new}” en {n} post(s)."
                )
        elif action == "delete":
            def drop(tags):
                return [t for t in tags if t != old]

            n = _apply_to_posts(drop)
            messages.success(request, f"“{old}” eliminado de {n} post(s).")
        else:
            messages.error(request, "Acción desconocida.")

        return redirect("panel-tags")

    counts = _tag_counts()
    return render(request, "panel/tags.html", {
        "tags": sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])),
        "total": sum(counts.values()),
    })
