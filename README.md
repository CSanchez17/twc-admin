# twc-admin — Panel de administración (Django)

Repo **independiente** (no forma parte de `C:\Projects\twc`): panel Django 5
sobre la base de datos compartida de TheWhiteCode. El sistema de registro es
la app FastAPI (`C:\Projects\twc`); este panel la administra: usuarios,
posts, categorías, tags y el resto del esquema.

## Credenciales (desarrollo local)

| Campo | Valor |
|---|---|
| URL | `http://127.0.0.1:8805/` (Docker) · `http://127.0.0.1:8889/` (runserver dev) |
| Usuario | `twcadmin` |
| Contraseña | `TwcAdmin2026!` |
| Tags | `http://127.0.0.1:8805/tags/` |

- Resetear: `.venv\Scripts\python.exe manage.py changepassword twcadmin`
- El auth del panel vive en sqlite local (`.admin_auth.sqlite3`), separado de
  los usuarios del sitio (esos se gestionan dentro del panel, sección
  **usuarios del sitio**, grupo *Panel* — no confundir con **Usuarios** del
  grupo *Authentication and authorization*, que es la cuenta del propio panel).
- ⚠️ La contraseña está en este README porque el panel corre en desarrollo
  local (127.0.0.1). Si algún día lo expones, cambia la contraseña, setea
  `DJANGO_SECRET_KEY` fuerte y sirve con HTTPS.

## Arranque rápido

Prerrequisito: el stack Docker de `C:\Projects\twc` corriendo (el panel
lee `DATABASE_URL` desde `C:\Projects\twc\config\.env`, o sea exactamente la
DB que escribe el sitio vivo).

### Opción A — Docker (la forma canónica, puerto 8805)

```bash
cd C:\Projects\twc-admin
docker compose up -d --build
```

El contenedor se une a la red del stack de la app (`twc_default`) y habla
directo con `mysql:3306` — sin mapeo de puerto para la DB. El auth sqlite
queda bind-montado en el host (la cuenta `twcadmin` sobrevive a rebuilds).

### Opción B — runserver (desarrollo sin Docker, puerto 8889)

```bat
cd C:\Projects\twc-admin
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8889
```

Comandos útiles:

```bat
:: crear otro superuser (guarda en el sqlite local, NO en la DB del sitio)
.venv\Scripts\python.exe manage.py createsuperuser

:: crear blog_categories (si no existe) + seed 1-23 (si está vacía) — idempotente
.venv\Scripts\python.exe manage.py seed_categories
```

## Qué se puede gestionar

| Sección | Qué hace |
|---|---|
| **Blog Posts** | CRUD completo. Slug auto desde el título (colisiones → `-2`, `-3`…), tags como texto separado por comas (se guarda como JSON en el post), categoría en `<select>` (de la tabla `blog_categories`), imagen destacada con vista previa. |
| **Blog Categories** | System of record de los nombres de categoría: la app FastAPI los lee para el sitio y para el select del editor. El slug se autogenera al crear y queda congelado (renombrar mantiene el slug). Borrar una categoría no toca los posts: estos conservan su id entero y la app cae al fallback legacy / "General". |
| **Tags** → `/tags/` | Los tags son arrays JSON en cada post (no hay tabla). Lista con conteo de posts, **renombrar** (reescibe todos los posts que lo llevan; si el destino ya existe, mergea sin duplicar) y **eliminar** (lo saca de todos). |
| **usuarios del sitio** | Usuarios de la app FastAPI (la DB real de MySQL): alta con contraseña Argon2id (compatible directo con el login de la app), rol, confirmación de email, edición de perfil. |
| **Blog Comments** | Listar/moderar (aprobar, eliminar). |
| **Media Files** | CRUD de archivos subidos. |
| **Notifications** | Listar + acción *mark read*. |
| **Contact Messages** | Listar + acción *resolve*. |
| **Chat Rooms** | CRUD. |
| Read-only | Pagos, x402, reacciones, analítica, Schancoin (wallets/blocks/tx) — ledger de solo lectura. |

## Cómo se sincroniza con la app

- **Categorías**: tabla `blog_categories` (id, name, slug). El panel es el
  único que escribe; la app FastAPI solo lee (`category_map()` en
  `app/modern_twc/repositories/post.py`). Fallback: mapa legacy 1-23 si la
  tabla está vacía/falta, para que posts antiguos sigan mostrando nombre.
- **Tags**: columna `blog_posts.tags` (JSON array, minúsculas). El editor de
  posts la escribe por post; `/tags/` la edita a nivel global.
- **Esquema**: los modelos del panel son *mirrors* `managed=False` — Django
  no migra la DB compartida; el esquema lo dueña la app FastAPI (migraciones
  alembic en `C:\Projects\twc\migrations`).

## Tests

```bat
DJANGO_SETTINGS_MODULE=twc_project.settings_test .venv\Scripts\python.exe manage.py test panel --keepdb
```

La test suite corre contra la **test DB compartida** con la app FastAPI:
`test_db.sqlite` en la raíz del repo de la app (`C:\Projects\twc`) — el
mismo archivo que crea y usa la suite pytest de la app. Igual que en prod
(donde ambas comparten el MySQL), en test comparten una BD local. Con
`--keepdb` + `MIGRATE: False` el runner de Django trata ese archivo como
**opaco**: no lo crea, migra ni borra. Si el archivo no existe aún, el
harness (`panel/tests/base.py`) lo inicializa una vez **desde los modelos
SQLAlchemy de la propia app** — la única fuente de verdad del esquema; no
hay lista de tablas mantenida a mano. El auth del panel (`admin_auth`)
sigue siendo sqlite in-memory. 41 tests: mirrors/UUID, admins de contenido,
registro de admins, editor de posts, seed de categorías, CRUD de
categorías, gestor de tags, acciones de usuarios y URLs documentadas en
este README.

## Estructura

> Qué es cada sección del índice del panel (qué almacena, quién la
> escribe, qué se puede editar): [`ADMIN-SECTIONS.md`](ADMIN-SECTIONS.md)

```
twc-admin/
├── README.md
├── ADMIN-SECTIONS.md         # qué es cada sección del panel
├── manage.py
├── requirements.txt          # Django, PyMySQL, argon2-cffi, gunicorn
├── Dockerfile                # multi-stage, non-root, healthcheck
├── docker-compose.yml        # panel en 8805, red twc_default
├── docker-entrypoint.sh      # migrate (alias admin_auth) + gunicorn
├── .admin_auth.sqlite3       # auth del panel (gitignored)
├── panel/
│   ├── models.py             # mirrors managed=False del esquema compartido
│   ├── admin.py              # todos los ModelAdmin + forms custom
│   ├── views.py              # página standalone /tags/
│   ├── templates/panel/tags.html
│   ├── fields.py             # HyphenatedUUIDField (UUID con guiones)
│   ├── management/commands/seed_categories.py
│   └── tests/                # harness (BD compartida) + 41 tests
├── scripts/                  # probes de debug (FK, roundtrip de login)
└── twc_project/
    ├── settings.py           # default = MySQL compartido (twc/config/.env)
    ├── settings_test.py      # test DB compartida con la app (--keepdb)
    ├── urls.py               # /tags/ + sitio de admin (montado en /)
    └── routers.py            # auth → alias admin_auth
```
