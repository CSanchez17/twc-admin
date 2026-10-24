#!/usr/bin/env python
"""Django admin panel for the shared twc database.

Run from this directory (twc_admin/):
    python manage.py migrate        # once (panel auth db only — shared DB is untouched)
    python manage.py createsuperuser  # panel login (stored in .admin_auth.sqlite3)
    python manage.py runserver
"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "twc_project.settings")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
