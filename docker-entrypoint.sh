#!/bin/sh
# Entrypoint: migrate the panel-local auth DB, then exec the server.
#
# Only the `admin_auth` alias (local sqlite with the panel's own users/
# sessions/permissions) is migrated here. The `default` alias is the shared
# live MySQL of the FastAPI app — the panel only mirrors it
# (managed=False) and never migrates it.
set -e

python manage.py migrate --noinput --database admin_auth

# Serve the admin's own CSS/JS: collect into STATIC_ROOT so the
# WhiteNoiseMiddleware can answer /static/... (gunicorn never serves
# statics, and the admin catch-all would 404 them).
python manage.py collectstatic --noinput --clear

# First-boot superuser from the environment. A deployed container has no
# shell, so `manage.py createsuperuser` cannot be typed later; the env vars
# (DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL) make the account
# reproducible and rebuild-safe. --noinput reads the password from
# DJANGO_SUPERUSER_PASSWORD. An existing account is left untouched.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    if python manage.py createsuperuser --noinput \
        --username "$DJANGO_SUPERUSER_USERNAME" \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@localhost}" \
        --database admin_auth 2>/dev/null; then
        echo "superuser '$DJANGO_SUPERUSER_USERNAME' created"
    else
        echo "superuser '$DJANGO_SUPERUSER_USERNAME' already present (or creation failed) — continuing"
    fi
fi

exec "$@" 
