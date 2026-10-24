"""Round-trip probe: create a user in the SHARED db via the Django ORM
(password hashed with Argon2id by Django's make_password), then prove the
FastAPI app accepts those exact credentials.

Steps (one command):
  1. create a throwaway user in the shared ``users`` table
  2. POST /auth/login to the RUNNING app (TWc panel default: http://127.0.0.1:8888)
  3. print the outcome, then delete the throwaway user

Run with the Django venv:
    .venv/Scripts/python.exe scripts/roundtrip_probe.py [app_base_url]
"""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from datetime import datetime, timezone

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "twc_project.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from panel.models import TWCUser  # noqa: E402
from panel.security import hash_password  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8888"
tag = time.strftime("%H%M%S")
email = f"roundtrip.{tag}@example.com"
username = f"rt_{tag}"
password = f"Rt-Pass-{tag}-xY9!"
now = datetime.now(timezone.utc)

user = TWCUser(
    id=uuid.uuid4(),
    email=email,
    username=username,
    password_hash=hash_password(password),
    given_name="Round",
    surname="Trip",
    role="user",
    is_active=True,
    is_email_confirmed=True,
    created_at=now,
    updated_at=now,
)
user.save()
print(f"created user via Django ORM: {username} <{email}> (argon2id)")
print(f"  hash prefix: {user.password_hash[:30]}...")

def attempt(identity_key: str, identity_value: str) -> tuple:
    data = urllib.parse.urlencode(
        {identity_key: identity_value, "password": password}
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/auth/login",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


cred_file = os.path.join(tempfile.gettempdir(), f"twc_rt_{tag}.json")
with open(cred_file, "w", encoding="utf-8") as f:
    json.dump({"email": email, "password": password}, f)

try:
    status, text = attempt("email", email)
    if status not in (200, 201):
        alt_status, alt_text = attempt("username", username)
        if alt_status in (200, 201):
            status, text = alt_status, alt_text

    ok = status in (200, 201) and ("token" in text.lower() or "access" in text.lower())
    print(f"POST {BASE}/auth/login -> {status}")
    print(f"  body: {text[:160].replace(password, '***')}...")
    print(f"  ROUNDTRIP {'OK' if ok else 'FAILED'}: Django-created user logs into the FastAPI app")
    sys.exit(0 if ok else 1)
finally:
    try:
        os.remove(cred_file)
    except OSError:
        pass
    TWCUser.objects.filter(id=user.id).delete()
    print(f"cleaned up {username}")
