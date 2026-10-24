#!/bin/sh
# Entrypoint: migrate the panel-local auth DB, then exec the server.
#
# Only the `admin_auth` alias (local sqlite with the panel's own users/
# sessions/permissions) is migrated here. The `default` alias is the shared
# live MySQL of the FastAPI app — the panel only mirrors it
# (managed=False) and never migrates it.
set -e

python manage.py migrate --noinput --database admin_auth

exec "$@"
