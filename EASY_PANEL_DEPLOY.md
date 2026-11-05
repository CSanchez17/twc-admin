# Deploying the twc admin panel on Easypanel

> The **as-deployed** state (variables, DNS, failure modes, verification)
> lives in [`PROD-RUNBOOK.md`](PROD-RUNBOOK.md). This file stays the
> first-time step-by-step guide.

The panel (`C:/Projects/twc-admin`, GitHub `CSanchez17/twc-admin`) is a
**single-service** Django app: gunicorn behind Easypanel's proxy, editing
the **same live MySQL** the FastAPI app writes to (all content models are
`managed=False` mirrors), with a tiny local SQLite that holds ONLY the
panel's own superusers/sessions/permissions (`admin_auth` alias).

There is no compose in prod. Everything below is the sequence the local
stack already proves (`docker-compose.yml` in this repo is the dev twin of
this deployment).

## 0. Final architecture

| Piece | Where | Notes |
|---|---|---|
| Panel (Django, gunicorn) | Easypanel project **`twc_prod`**, service `admin` | built from the repo-root `Dockerfile`, listens on **8000** |
| MySQL | the app project's **existing** `mysql` service | the panel reuses it — same project ⇒ same docker network ⇒ the internal hostname `mysql` resolves natively |
| Panel auth (SQLite) | named volume of service `admin` | mounted at `/data` — holds the superuser, sessions, permissions |
| Source | GitHub `CSanchez17/twc-admin`, branch **`main`** | `autoDeploy: false` — deploys are manual |
| Health probe | `GET /healthz` (container-internal, no DB) | the Docker `HEALTHCHECK` uses it; a failing probe stops the container → 502 |

Put the panel **inside the existing `twc_prod` project** (not a new
project): Easypanel services only see each other's internal hostnames when
they share a project network. A separate project would need a manual
network join for the same result.

## 1. Add the service

1. In project `twc_prod`: **Add service → Git**.
   - Repository: `CSanchez17/twc-admin`, branch **`main`** (the default branch).
2. Service settings:
   - **Dockerfile**: the one at the repo root (multi-stage; the last stage
     is the runtime — Gunicorn worker pool). No `--target` needed.
   - **Port**: `8000`.
   - **autoDeploy: false**.
3. **Domain**: a domain for this service pointing at container port
   **8000** (never 80). E.g. `panel.thewhitecode.com`.
4. **Volume**: add a volume to the service, mounted at **`/data`**.
   Without it a rebuild recreates the container with an empty
   `admin_auth` database and the superuser account is gone.

## 2. Environment variables (service `admin` → Environment)

| Var | Value |
|---|---|
| `DATABASE_URL` | **exactly the same value the app service uses** (`mysql://user:***@<internal-host>:<port>/twc_prod?charset=utf8mb4` — copy from the MySQL **Credentials** tab). The `+aiomysql`/driver suffix is fine: the panel parses the `mysql` scheme prefix and drives the connection with PyMySQL. |
| `TWC_PANEL_IN_DOCKER` | `1` — **required**. Tells settings.py to skip the host-side rewrite that turns `mysql:3306` into `127.0.0.1:8801` (a rewrite that only makes sense for a panel running on the dev host; inside the container it points at the panel itself ⇒ every content page 500s). |
| `ADMIN_AUTH_DB` | `/data/admin_auth.sqlite3` — where the panel-local auth SQLite lives (inside the mounted volume). |
| `DJANGO_SECRET_KEY` | random ≥ 32 chars (separate from the app's `SECRET_KEY`). Rotating it later invalidates panel sessions — fine at first deploy. |
| `DJANGO_SUPERUSER_USERNAME` | the panel login to create on first boot, e.g. `twcadmin` |
| `DJANGO_SUPERUSER_PASSWORD` | its password (≥ 8 chars). Read by `createsuperuser --noinput`; the entrypoint never echoes it. |
| `DJANGO_SUPERUSER_EMAIL` | optional, defaults to `admin@localhost` |
| `DJANGO_DEBUG` | `0` — **required**: the code default is `1`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | optional. Default derives `https://<host>` from `DJANGO_ALLOWED_HOSTS`; set it explicitly only for extra origins (e.g. a second domain). Without a matching origin the admin login POST fails with “CSRF verification failed / Origin checking failed”. |
| `DJANGO_SECURE_COOKIES` | optional. Default `1` when `DJANGO_DEBUG=0` (session + CSRF cookies `Secure`). Set `0` only if the panel is served over plain HTTP — otherwise the login loop never ends. |
| `DJANGO_ALLOWED_HOSTS` | the panel's real domains, comma-separated — include the Easypanel auto-domain and any custom domain, e.g. `twc-prod-admin.58nbit.easypanel.host,admin.thewhitecode.com`. Loopback (`127.0.0.1`, `localhost`) is always added automatically for the health probe. Omit to fall back to `["*"]`. |
| `DJANGO_TZ` | optional, default `Europe/Madrid`. |

**Never set** `TWC_SEED_DUMP`, `TWC_REPAIR_USERS` or any uploads vars —
those are app-service concerns. The panel never seeds, repairs or
uploads; it only reads/edits the live tables.

## 3. First deploy

1. Deploy the service from the panel. On boot the entrypoint runs:
   - `migrate --database admin_auth` (panel-local tables only — it NEVER
     migrates the shared MySQL, whose schema the FastAPI app owns), then
   - `collectstatic` (WhiteNoise serves `/static/` — gunicorn would 404
     it otherwise), then starts gunicorn on 8000.
2. Check the logs: no traceback, gunicorn booted with 2 workers.
   The Dockerfile ships a healthcheck probing `GET /login/` — Easypanel
   can use the same path for its probe.

## 4. Create the superuser (automated — no shell needed)

A deployed container has no shell, so the account is created from
environment variables on first boot. The entrypoint runs, right before
gunicorn:

```sh
python manage.py createsuperuser --noinput --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "${DJANGO_SUPERUSER_EMAIL:-admin@localhost}" --database admin_auth
```

`--noinput` takes the password from `DJANGO_SUPERUSER_PASSWORD`. The step is
idempotent: an existing account is left untouched, so rebuilds never reset the
password and a fresh `/data` volume re-creates the account.

Check the deploy logs for `superuser 'twcadmin' created`.

Fallback (only if the env vars were omitted): exec into the container —

```bash
docker ps --format '{{.ID}} {{.Names}}' | grep -i admin
docker exec -it <container-id> python manage.py createsuperuser --database admin_auth
```

The router puts the account in `admin_auth`, never in the shared MySQL.

## 5. Production verification

- [ ] `GET /login/` → 200, fully styled (WhiteNoise statics load)
- [ ] login with `twcadmin` works
- [ ] content changelist (blog posts) lists the **live** rows — same
      numbers as `GET <app-domain>/blog/load/content`
- [ ] editing a post's title in the panel → shows on the live site
      immediately (this is the point: it IS the live database)
- [ ] `GET /health/...` style probes: the panel has no `/health` route —
      use `/login/`
- [ ] logs: no `OperationalError` (would mean a wrong DATABASE_URL or a
      missing `TWC_PANEL_IN_DOCKER`), no `disallowed host` (wrong
      `DJANGO_ALLOWED_HOSTS`)

## 6. Day-2 operations

- **Ship a change**: `git push` to `master`, then **Re-deploy** the admin
  service (autoDeploy off). Env vars and the `/data` volume survive; the
  superuser is kept.
- **MySQL credentials rotated** on the app side → update the panel's
  `DATABASE_URL` too and re-deploy.
- **Fresh volume** (project rebuilt): re-run step 4. The shared MySQL is
  untouched by any of this.
- **The panel edits LIVE content** — every save/delete in it is the
  production site. There is no staging copy.

## 6b. Troubleshooting: the two failures that hit every fresh deploy

| Symptom | Cause | Fix |
|---|---|---|
| `502` / “Service is not reachable” **~70 s after every boot**, logs show `Listening at: http://0.0.0.0:8000` and then `Handling signal: term` | The Docker `HEALTHCHECK` failed, so the platform stopped the container: it probed `/healthz` with `Host: 127.0.0.1`, which Django rejects with `400 DisallowedHost` unless loopback is in `ALLOWED_HOSTS`. | Already handled: settings always append `127.0.0.1`/`localhost`/`[::1]`, and the probe hits `/healthz` (no DB, no template). Verify with `docker inspect --format '{{.State.Health.Status}}' <container>`. |
| Login page loads, the POST answers **403 “CSRF verification failed — Origin checking failed”** | The proxy terminates TLS, so `request.is_secure()` is False and the browser's `Origin: https://<domain>` matches nothing. | Already handled: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` and `CSRF_TRUSTED_ORIGINS` derived from `DJANGO_ALLOWED_HOSTS`. If the domain is missing from `DJANGO_ALLOWED_HOSTS` you also get `400 Bad Request (DisallowedHost)`. |

Both are covered by tests (`panel/tests/test_healthz.py`,
`test_settings_allowed_hosts.py`, `test_settings_proxy_tls.py`).

## 7. Gotchas (learned the hard way, do not rediscover them)

1. **`DJANGO_DEBUG` defaults to `1`** — a deployed panel must set `0`,
   else error pages leak stack traces to visitors.
2. **`TWC_PANEL_IN_DOCKER=1` is load-bearing.** Without it, settings
   rewrite the DB host `mysql` → `127.0.0.1:8801` (the dev-host mapping);
   inside the container that is the panel itself ⇒ login works (panel-
   local auth) but every content page 500s. Symptom: "the panel opens but
   shows nothing".
3. **The `/data` volume is the superuser.** No volume ⇒ rebuild ⇒ empty
   `admin_auth` ⇒ the panel is locked (no account) and you have to
   exec into the container to recreate it.
4. **Never run `migrate` without `--database admin_auth`.** The
   `default` alias is the shared live MySQL with `managed=False`
   mirrors — a bare `migrate` would try to create Django's internal
   tables (auth, sessions, contenttypes) INSIDE the production database.
   The entrypoint already does this right.
5. **Port 8000 for the domain** — the proxy routes to the container
   port; `80` is not listening.
6. **`DJANGO_SECRET_KEY` must not stay the dev default** (it is a
   hardcoded insecure string in settings for dev convenience).
7. **Password hashes interoperate**: the panel hashes with Argon2id —
   the same algorithm as the FastAPI app. An account created in the panel
   can log into the site, and vice versa, when usernames match.
8. **Easypanel DNS from the dev machine is flaky** (this host loses
   `github.com`/`api.github.com` resolution intermittently): pushes and
   API calls need a retry loop, not a single attempt.
