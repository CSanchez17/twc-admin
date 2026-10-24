from django.contrib import admin
from django.urls import path

from panel.views import tags_manager

urlpatterns = [
    # The admin site is mounted at the ROOT (""), so standalone pages
    # live next to it: /tags/ (like /login/, /panel/…).
    path("tags/", tags_manager, name="panel-tags"),
    path("", admin.site.urls),
]
