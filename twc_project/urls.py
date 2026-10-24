from django.contrib import admin
from django.urls import path

from panel.views import tags_manager

urlpatterns = [
    # BEFORE the admin catch-all: the admin site would swallow
    # "admin/<anything>" (including /admin/tags/) otherwise.
    path("admin/tags/", tags_manager, name="panel-tags"),
    path("", admin.site.urls),
]
