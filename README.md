# twc-admin — Panel de administración (Django)

Repo **independiente** (no forma parte de `C:\Projects\twc`): panel Django 5
sobre la base de datos compartida de TheWhiteCode. El sistema de registro es
la app FastAPI (`C:\Projects\twc`); este panel la administra: usuarios,
posts, categorías, tags y el resto del esquema.

## Credenciales (desarrollo local)

| Campo | Valor |
|---|---|
| URL | `http://127.0.0.1:8000/admin/` |
| Usuario | `twcadmin` |
| Contraseña | `TwcAdmin2026!` |

- Resetear: `.venv\Scripts\python.exe manage.py changepassword twcadmin`
- El auth del panel vive en sqlite local (`.admin_auth.sqlite3`), separado de
  los usuarios del sitio (esos se gestionan dentro del panel, sección
  **Users**).
- ⚠️ La contraseña está en este README porque el panel corre en desarrollo
  local (127.0.0.1). Si algún día lo expones, cambia la contraseña, setea
  `DJANGO_SECRET_KEY` fuerte y sirve con HTTPS.

## Arranque rápido

Prerrequisito: el stack Docker de `C:\Projects\twc` corriendo (el panel
lee `DATABASE_URL` desde `C:\Projects\twc\config\.env`, o sea exactamente la
DB que escribe el sitio vivo).

```bat
cd C:\Projects\twc-admin
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py runserver
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
| **Tags** → `/admin/tags/` | Los tags son arrays JSON en cada post (no hay tabla). Lista con conteo de posts, **renombrar** (reescibe todos los posts que lo llevan; si el destino ya existe, mergea sin duplicar) y **eliminar** (lo saca de todos). |
| **Users** | Usuarios de la app FastAPI: alta con contraseña Argon2id (compatible directo con el login de la app), rol, confirmación de email, edición de perfil. |
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
  posts la escribe por post; `/admin/tags/` la edita a nivel global.
- **Esquema**: los modelos del panel son *mirrors* `managed=False` — Django
  no migra la DB compartida; el esquema lo dueña la app FastAPI (migraciones
  alembic en `C:\Projects\twc\migrations`).

## Tests

```bat
DJANGO_SETTINGS_MODULE=twc_project.settings_test .venv\Scripts\python.exe manage.py test panel
```

La test suite corre contra sqlite **in-memory** (ver `twc_project/settings_test.py`):
jamás toca el MySQL vivo. 34 tests: mirrors/UUID, admins de contenido,
editor de posts, seed de categorías, CRUD de categorías y gestor de tags.

## Estructura

```
twc-admin/
├── manage.py
├── requirements.txt          # Django, PyMySQL, argon2-cffi
├── .admin_auth.sqlite3       # auth del panel (gitignored)
├── panel/
│   ├── models.py             # mirrors managed=False del esquema compartido
│   ├── admin.py              # todos los ModelAdmin + forms custom
│   ├── views.py              # página standalone /admin/tags/
│   ├── templates/panel/tags.html
│   ├── fields.py             # HyphenatedUUIDField (UUID con guiones)
│   ├── management/commands/seed_categories.py
│   └── tests/                # harness (tablas en setUpModule) + 34 tests
├── scripts/                  # probes de debug (FK, roundtrip de login)
└── twc_project/
    ├── settings.py           # default = MySQL compartido (twc/config/.env)
    ├── settings_test.py      # in-memory sqlite para tests
    ├── urls.py               # /admin/tags/ + sitio de admin
    └── routers.py            # auth → alias admin_auth
```
