"""Where does a Django TWCUser.save() actually land? Check both DBs + raw files."""
import os
import sys
import uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "twc_project.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from datetime import datetime, timezone  # noqa: E402
from django.conf import settings  # noqa: E402
from panel.models import TWCUser  # noqa: E402
from panel.security import hash_password  # noqa: E402

print("default DB ->", settings.DATABASES["default"]["ENGINE"].split(".")[-1],
      settings.DATABASES["default"].get("HOST"), settings.DATABASES["default"]["NAME"])
print("admin_auth DB ->", settings.DATABASES["admin_auth"]["NAME"])

uid = uuid.uuid4()
now = datetime.now(timezone.utc)
u = TWCUser(id=uid, email=f"where.{uid.hex[:8]}@example.com", username=f"wh_{uid.hex[:10]}",
            password_hash=hash_password("x"), given_name="W", surname="H",
            role="user", is_active=True, is_email_confirmed=True, created_at=now, updated_at=now)
u.save()
print("saved uid", uid)

# Which DB does Django think the row is in?
for db in ("default", "admin_auth"):
    try:
        n = TWCUser.objects.using(db).filter(id=uid).count()
    except Exception as e:  # noqa: BLE001
        n = f"ERR {type(e).__name__}: {str(e)[:80]}"
    print(f"  TWCUser.using('{db}').count() = {n}")

# raw: admin_auth sqlite
import sqlite3  # noqa: E402
ap = settings.DATABASES["admin_auth"]["NAME"]
if os.path.exists(ap):
    con = sqlite3.connect(ap)
    try:
        cur = con.execute("SELECT COUNT(*) FROM users WHERE id=?", (str(uid),))
        print(f"  raw sqlite '{os.path.basename(ap)}' users count for uid = {cur.fetchone()[0]}")
    except Exception as e:  # noqa: BLE001
        print("  raw sqlite users query err:", str(e)[:80])
    con.close()

# raw: default mysql
import pymysql  # noqa: E402
db = settings.DATABASES["default"]
conn = pymysql.connect(host=db["HOST"], port=int(db["PORT"]), user=db["USER"],
                       password=db["PASSWORD"], database=db["NAME"], charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM users WHERE id=%s", (str(uid),))
    print(f"  raw mysql users count for uid = {cur.fetchone()[0]}")
conn.close()

# cleanup whichever has it
try:
    TWCUser.objects.using("default").filter(id=uid).delete()
except Exception:
    pass
try:
    TWCUser.objects.using("admin_auth").filter(id=uid).delete()
except Exception:
    pass
print("cleanup attempted")
