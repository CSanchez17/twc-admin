"""Django settings for the twc admin panel.

Database layout:
- ``default``    → the shared twc database (the FastAPI app's DATABASE_URL,
                   read from the repo root .env). All panel content models
                   are ``managed=False`` mirrors of it.
- ``admin_auth`` → a small local SQLite db holding ONLY the panel's own
                   Django internals (admin superusers, sessions, perms), so
                   the shared production DB is never touched by Django's
                   internal tables.

Password compatibility: the panel hashes with Argon2id (argon2-cffi, the
same library the FastAPI app uses) — a user created here logs into the
FastAPI app directly and vice versa.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

# PyMySQL as the MySQL driver (pure-python; mysqlclient is not available on
# the target Windows runtime). Must happen BEFORE Django's mysql backend
# imports MySQLdb.
try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:  # pragma: no cover — sqlite-only dev setups
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
# This is its OWN repo (C:\Projects\twc-admin). The FastAPI app it manages
# lives in a sibling repo (C:\Projects\twc) — the .env/config paths below
# resolve against the APP repo root, overridable via TWC_APP_ROOT.
REPO_ROOT = Path(os.environ.get("TWC_APP_ROOT", BASE_DIR.parent / "twc")).resolve()


# Captured BEFORE any .env file is merged in, so we can tell an explicit
# operator-supplied DATABASE_URL apart from a .env-derived one.
_EXPLICIT_DB_URL = os.environ.get("DATABASE_URL")


def _read_env_file(path: Path) -> dict:
    """Parse a KEY=VALUE .env file into a dict (no execution, no quoting magic)."""
    values: dict = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_repo_env() -> None:
    """Merge the repo root .env into os.environ (for SECRET_KEY & friends).

    DATABASE_URL is deliberately resolved separately (see
    ``_resolve_database_url``) so the panel can prefer the live app's config.
    """
    for key, value in _read_env_file(REPO_ROOT / ".env").items():
        os.environ.setdefault(key, value)


_load_repo_env()


def _normalize_for_host_access(url: str) -> str:
    """The panel runs on the HOST; the live app's config points at the
    docker-internal hostname ``mysql``. Rewrite that to 127.0.0.1 (the
    published 3306) so the same database is reachable from the host."""
    parsed = urlparse(url)
    netloc = parsed.netloc
    if not netloc:
        return url
    userinfo, _, hostport = netloc.rpartition("@")
    host, _, port = hostport.partition(":")
    if host in ("", "mysql"):
        host = "127.0.0.1"
        new_hostport = f"{host}{(':' + port) if port else ''}"
        new_netloc = (userinfo + "@" if userinfo else "") + new_hostport
        return urlunparse(parsed._replace(netloc=new_netloc))
    return url


def _resolve_database_url() -> str:
    """Pick the shared database URL.

    The panel's contract is to manage the LIVE app's database. ``config/.env``
    is the config of the docker app that is actually running, so it is by
    definition the same database the live site writes to — prefer it FIRST,
    above any ``DATABASE_URL`` in the process environment (which may be a
    stale dev value, e.g. from the repo-root ``.env``, that no longer
    authenticates). Falls back to the explicit env var, then the repo-root
    ``.env``, then a local sqlite, in case ``config/.env`` is absent (dev
    setups that don't run the docker stack). Whatever is chosen is normalized
    for host-side access.
    """
    cfg = _read_env_file(REPO_ROOT / "config" / ".env")
    url = cfg.get("DATABASE_URL")
    if not url:
        url = (
            _EXPLICIT_DB_URL
            or _read_env_file(REPO_ROOT / ".env").get("DATABASE_URL")
            or "sqlite:///./twc_dev.sqlite"
        )
    return _normalize_for_host_access(url)


def _db_config(url: str) -> dict:
    parsed = urlparse(url)
    scheme = parsed.scheme
    if scheme.startswith("sqlite"):
        path = parsed.path or (parsed.netloc or "")
        if not path:
            path = "./twc_dev.sqlite"
        full = Path(path)
        if not full.is_absolute():
            full = REPO_ROOT / str(full).lstrip("./")
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": str(full)}
    if scheme.startswith("mysql"):
        return {
            "ENGINE": "django.db.backends.mysql",
            "NAME": unquote(parsed.path.lstrip("/") or "twc"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "127.0.0.1",
            "PORT": str(parsed.port or 3306),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme!r}")


DATABASES = {
    "default": _db_config(_resolve_database_url()),
    "admin_auth": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / ".admin_auth.sqlite3"),
    },
}

DATABASE_ROUTERS = ["twc_project.routers.PanelAuthRouter"]

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-set-DJANGO_SECRET_KEY-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = ["*"]  # dev tool; put a real host list in production

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "twc_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "twc_project.wsgi.application"

LANGUAGE_CODE = "es-es"
TIME_ZONE = os.environ.get("DJANGO_TZ", "Europe/Madrid")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Argon2id FIRST — hashes interoperate with the FastAPI app's argon2-cffi
# PasswordHasher both ways. PBKDF2 stays as a fallback for Django internals.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
