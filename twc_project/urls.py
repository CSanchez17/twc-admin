from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from panel.views import tags_manager


def healthz(request):
    """Liveness probe for the platform (Docker HEALTHCHECK / Easypanel).

    Deliberately free of DB, template and auth work: a slow or unreachable
    MySQL must never take the container down, it must show up as a 500 on the
    content pages instead. ``Content-Type: text/plain`` keeps it cheap.
    """
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    # The admin site is mounted at the ROOT (""), so standalone pages
    # live next to it: /tags/ (like /login/, /panel/…).
    path("tags/", tags_manager, name="panel-tags"),
    path("", admin.site.urls),
]
