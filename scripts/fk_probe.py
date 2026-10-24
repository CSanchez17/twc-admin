"""Isolate the refresh_tokens FK failure: create a TWCUser via the Django ORM,
close that connection, then with a FRESH raw connection (like the app's own
pool) check the row is visible and whether an insert into refresh_tokens
referencing it satisfies the FK.
"""
import os
import sys
import uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "twc_project.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from datetime import datetime, timedelta, timezone  # noqa: E402

import pymysql  # noqa: E402
from django.conf import settings  # noqa: E402
from django.db import connection as dj_conn  # noqa: E402
from panel.models import TWCUser  # noqa: E402
from panel.security import hash_password  # noqa: E402

uid = uuid.uuid4()
now = datetime.now(timezone.utc)
u = TWCUser(
    id=uid, email=f"fktest.{uid.hex[:8]}@example.com", username=f"fk_{uid.hex[:10]}",
    password_hash=hash_password("x"), given_name="FK", surname="Test",
    role="user", is_active=True, is_email_confirmed=True, created_at=now, updated_at=now,
)
u.save()
dj_conn.close()  # force commit + close, like a fresh request
print(f"created {u.username} id={uid}")

db = settings.DATABASES["default"]
conn = pymysql.connect(host=db["HOST"], port=int(db["PORT"]), user=db["USER"],
                       password=db["PASSWORD"], database=db["NAME"], charset="utf8mb4")
try:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users WHERE id=%s", (str(uid),))
        visible = cur.fetchone()[0]
        print(f"users row visible to fresh connection: {visible}")
        try:
            cur.execute(
                "INSERT INTO refresh_tokens (id,user_id,token_key,token_hash,expires_at,revoked_at,replaced_by_id) "
                "VALUES (%s,%s,%s,%s,%s,NULL,NULL)",
                (str(uuid.uuid4()), str(uid), "k" * 64, "$argon2id$probe",
                 now + timedelta(days=1)),
            )
            conn.commit()
            print("refresh_tokens FK insert: OK")
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            print("refresh_tokens FK insert FAILED:", type(e).__name__, str(e)[:160])
finally:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM refresh_tokens WHERE user_id=%s", (str(uid),))
        cur.execute("DELETE FROM users WHERE id=%s", (str(uid),))
    conn.commit()
    conn.close()
    print("cleaned up")
