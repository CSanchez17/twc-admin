# Panel de administración — runbook de producción

Estado **verificado** de la instalación productiva del panel Django sobre la
base de datos compartida de TheWhiteCode. Complementa a
[`EASY_PANEL_DEPLOY.md`](EASY_PANEL_DEPLOY.md) (guía paso a paso del primer
despliegue): este documento es el registro de *cómo está montado hoy* y *qué
falló y por qué*, para que nadie tenga que redescubrirlo.

| | |
|---|---|
| Fecha de la verificación | 2026-11-05 |
| Commit desplegado | `957d399` (`fix(deploy): keep the container healthy and the admin login working behind the proxy`) |
| Proyecto Easypanel | `twc_prod` |
| Servicio | `admin` |
| URL operativa | https://twc-prod-admin.58nbit.easypanel.host/login/ |
| Dominio propio | `admin.thewhitecode.com` — pendiente del registro DNS (ver §5) |
| Código | GitHub `CSanchez17/twc-admin`, rama **`main`** |
| Auth del panel | sqlite en el volumen `/data` (`ADMIN_AUTH_DB`) |
| Base de datos gestionada | MySQL del mismo proyecto, esquema `twc_prod` |

Evidencia recogida contra producción (no local):

```text
GET https://twc-prod-admin.58nbit.easypanel.host/healthz  -> 200 "ok"
GET https://twc-prod-admin.58nbit.easypanel.host/login/   -> 200
    <title>Iniciar sesión | Sitio de administración de Django</title>
t+75 s otra vez /login/                                   -> 200   (ya no muere a los ~73 s)
```

## 1. Por qué el panel vive dentro de `twc_prod`

Easypanel sólo publica los hostnames internos (`mysql`, `redis`) dentro del
mismo proyecto: son contenedores en la misma red. El panel se conecta a
`mysql:3306` directamente, sin puerto público y sin TLS de por medio.

Un proyecto aparte obligaría a exponer el MySQL en Internet y a usar su
host/puerto públicos — más superficie de ataque y otra cosa que mantener. No
lo hagas.

## 2. Servicio `admin` — configuración exacta

| Ajuste | Valor |
|---|---|
| Tipo | **App** (build desde Git) |
| Repositorio | `CSanchez17/twc-admin` |
| Rama | **`main`** (la default del repo; `master` no existe) |
| Build path | `/` |
| Dockerfile | `Dockerfile` (raíz), sin build target |
| Puerto | **8000** (nunca 80) |
| Auto-deploy | **off** — los despliegues son manuales |
| Volumen | nombre `data` → mount path **`/data`** |
| Health probe | `GET /healthz` (interno, 200 sin BD) |
| Dominios | `twc-prod-admin.58nbit.easypanel.host` y `admin.thewhitecode.com` → puerto **8000** |

El `Dockerfile` construye con Python 3.14 (multi-stage: `gcc` sólo para
compilar `argon2-cffi`), corre como usuario `django` (uid 10001) y lanza
gunicorn con 2 workers escuchando en `0.0.0.0:8000`.

## 3. Variables de entorno (las que están en producción)

```env
DATABASE_URL=mysql://USER:***@mysql:3306/twc_prod?charset=utf8mb4
TWC_PANEL_IN_DOCKER=1
ADMIN_AUTH_DB=/data/admin_auth.sqlite3
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=***
DJANGO_ALLOWED_HOSTS=twc-prod-admin.58nbit.easypanel.host,admin.thewhitecode.com
DJANGO_SUPERUSER_USERNAME=***
DJANGO_SUPERUSER_PASSWORD=***
DJANGO_SUPERUSER_EMAIL=***
```

| Variable | Por qué |
|---|---|
| `DATABASE_URL` | **El mismo valor que usa el servicio `app`** (pestaña *Environment* de `app`). Es la única fuente de credenciales del MySQL; si el MySQL las rota, hay que actualizar las dos. |
| `TWC_PANEL_IN_DOCKER` | `1` es obligatorio: sin él `settings.py` reescribe el host `mysql` → `127.0.0.1:8801` (mapeo pensado para ejecutar el panel en el host) y dentro del contenedor eso apunta al propio panel ⇒ login OK pero todas las páginas de contenido dan 500. |
| `ADMIN_AUTH_DB` | sqlite del panel (usuarios/sesiones/permisos de Django) **dentro del volumen**. Sin volumen, cada rebuild deja el panel sin cuenta. |
| `DJANGO_DEBUG` | `0`. El valor por defecto del código es `1` y filtraría trazas a Internet. |
| `DJANGO_SECRET_KEY` | ≥32 caracteres, distinto del `SECRET_KEY` de la app. `openssl rand -hex 32`. Rotarlo invalida las sesiones del panel (aceptable al principio). |
| `DJANGO_ALLOWED_HOSTS` | Lista explícita de dominios reales. Con `DEBUG=0`, un `Host` que no esté aquí devuelve **400 Bad Request** (ver §7). `127.0.0.1`/`localhost` se añaden solos para el healthcheck. |
| `DJANGO_SUPERUSER_*` | Crean la cuenta del panel en el primer arranque (`createsuperuser --noinput --database admin_auth`). Idempotente: si ya existe, no se toca. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | *Opcional.* Si no se define, se deriva `https://<host>` de `DJANGO_ALLOWED_HOSTS`. Sólo hace falta para orígenes extra. |
| `DJANGO_SECURE_COOKIES` | *Opcional.* Por defecto `1` cuando `DJANGO_DEBUG=0` (cookies `Secure`). Poner `0` sólo si se sirve por HTTP plano, o el login entra en bucle. |

**Nunca** pongas en este servicio `TWC_SEED_DUMP`, `TWC_REPAIR_USERS` ni
variables de uploads: son cosas del servicio `app`.
**Nunca** metas credenciales en el repo: van en *Environment*, no en un `.env`
versionado.

## 4. Secuencia de despliegue

1. `admin` → **Deploy** (Easypanel construye la imagen desde `main`).
2. Log esperado, en orden:
   ```text
   Apply all migrations: admin, auth, contenttypes, sessions
   ... Applying sessions.0001_initial... OK
   127 static files copied to '/app/staticfiles'.
   superuser '...' created            (o "already present")
   [INFO] Listening at: http://0.0.0.0:8000 (1)
   ```
3. El contenedor anterior recibe `Handling signal: term` **cuando arranca el
   nuevo** — normal. Lo que *no* es normal es un `term` ~70 s después de
   arrancar y sin reemplazo (§7).

## 5. DNS y TLS

Estado actual: el panel responde por el dominio automático de Easypanel. Para
`admin.thewhitecode.com` falta el registro.

**Cloudflare** (`thewhitecode.com` → DNS → Add record):

```text
Type: A
Name: admin
IPv4 address: 91.194.91.37
Proxy status: DNS only   ← nube GRIS
TTL: Auto
```

La nube gris es obligatoria la primera vez: Easypanel valida el dominio por
HTTP para emitir el certificado con Let's Encrypt, y con el proxy de Cloudflare
delante esa validación no llega al origen. Una vez emitido el certificado se
puede activar el proxy (SSL/TLS en *Full (strict)*) si se quiere.

Y en `admin → Domains`: el dominio tiene que estar listado con target port
**8000**. Easypanel emite el certificado en cuanto el DNS resuelve.

## 6. Verificación (hazla después de cada deploy)

Script incluido, sin dependencias:

```bash
python scripts/verify_deploy.py --base https://twc-prod-admin.58nbit.easypanel.host
```

Comprueba `GET /healthz` (200 + `ok`), `GET /login/` (200, formulario y token
CSRF), y que `/` sin sesión redirige a `/login/?next=/`. Sale con código ≠0 si
algo falla.

A mano, lo mínimo:

```bash
curl -s https://<dominio>/healthz                       # ok
curl -s -o /dev/null -w '%{http_code}\n' https://<dominio>/login/   # 200
```

Y el login real: entrar con el `DJANGO_SUPERUSER_USERNAME` y comprobar que
`/panel/` lista los posts de la base de datos de producción.

## 7. Fallos reales de este despliegue (síntoma → causa → arreglo)

| Síntoma | Causa raíz | Arreglo |
|---|---|---|
| **502 “Service is not reachable” ~70 s después de cada arranque**; el log muestra `Listening at: http://0.0.0.0:8000` y luego `Handling signal: term` | El `HEALTHCHECK` del `Dockerfile` pedía `/login/` con `Host: 127.0.0.1`, que Django rechaza con **400 DisallowedHost** en cuanto se fija un dominio real ⇒ contenedor *unhealthy* ⇒ la plataforma lo para | El probe apunta a `/healthz` (sin BD, sin plantilla, sin auth) y `settings.py` añade siempre `127.0.0.1`, `localhost`, `[::1]` a `ALLOWED_HOSTS` |
| **400 Bad Request** (cuerpo vacío, `Server: gunicorn`) al abrir el panel por su dominio | El dominio no está en `DJANGO_ALLOWED_HOSTS` | Añadirlo a la lista y redeploy |
| **403 CSRF al enviar el login** (“Origin checking failed — does not match any trusted origins”) | El TLS termina en el proxy: `request.is_secure()` era `False` y el `Origin: https://<dominio>` del navegador no cuadraba con nada | `SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")` + `CSRF_TRUSTED_ORIGINS` derivados de `DJANGO_ALLOWED_HOSTS` |
| `Handling signal: term` a los **~8 s** de arrancar | Es el contenedor **anterior** apagándose cuando el nuevo ya está arriba (deploy normal) | Nada que arreglar; comprobar que el nuevo sigue respondiendo |
| Aviso `You have 18 unapplied migration(s)… (admin, auth, contenttypes, sessions)` | `createsuperuser` comprueba las migraciones del alias `default` (el MySQL compartido), donde las tablas internas de Django **no existen por diseño**: viven en `admin_auth` | Ruido esperado, no es un error. Nunca ejecutes `migrate` sin `--database admin_auth` |
| `superuser '...' already present (or creation failed)` | La cuenta ya existe en el volumen `/data` | Correcto e idempotente |

Los tres primeros están cubiertos por tests:
`panel/tests/test_healthz.py`, `panel/tests/test_settings_allowed_hosts.py`,
`panel/tests/test_settings_proxy_tls.py`.

## 8. Pruebas y verificación local de la imagen

```bash
# suite del panel (BD compartida, --keepdb obligatorio)
DJANGO_SETTINGS_MODULE=twc_project.settings_test \
    .venv/Scripts/python.exe manage.py test panel --keepdb      # 92 tests

# imagen tal cual se despliega, contra la BD de desarrollo
docker build -t twc-admin:local .
docker run -d --name twc-admin-check -p 8907:8000 \
  -e DATABASE_URL='mysql://user:pass@host.docker.internal:8801/twc?charset=utf8mb4' \
  -e TWC_PANEL_IN_DOCKER=1 -e ADMIN_AUTH_DB=/data/admin_auth.sqlite3 \
  -e DJANGO_DEBUG=0 -e DJANGO_SECRET_KEY='solo-para-esta-prueba' \
  -e DJANGO_ALLOWED_HOSTS='admin.thewhitecode.com' \
  -e DJANGO_SUPERUSER_USERNAME=twcadmin -e DJANGO_SUPERUSER_PASSWORD='...' \
  twc-admin:local
docker inspect --format '{{.State.Health.Status}}' twc-admin-check   # healthy
curl -s -H 'Host: admin.thewhitecode.com' http://127.0.0.1:8907/healthz   # ok
```

Con `DJANGO_ALLOWED_HOSTS` limitado a un dominio real, el healthcheck debe
seguir en `healthy`: eso prueba de una vez la lista de hosts y el probe.

## 9. Operación del día 2

- **Cambiar la contraseña del panel**: cambia `DJANGO_SUPERUSER_PASSWORD` y
  redeploy (el primer arranque sólo crea la cuenta si no existe; para
  cambiarla sin rebuild: `docker exec -it <container> python manage.py
  changepassword <usuario> --database admin_auth`).
- **Actualizar código**: `git push` a `main` → `admin` → **Deploy**. El volumen
  `/data` y las variables sobreviven.
- **Volumen perdido** (proyecto recreado): al arrancar, el entrypoint migra
  `admin_auth` y vuelve a crear la cuenta desde `DJANGO_SUPERUSER_*`.
- **Rotar credenciales del MySQL**: actualizar `DATABASE_URL` en `app` **y** en
  `admin`, y redesplegar los dos.
- **Comprobar que está vivo** sin abrir el navegador:
  `python scripts/verify_deploy.py --base https://<dominio>`.

## 10. Límites conocidos (importante)

- **El panel no puede reescribir fechas.** `created_at`/`updated_at` de posts y
  usuarios son `readonly` en el admin: el panel sirve para editar contenido
  publicado, no para fabricar históricos. Para sembrar contenido con fechas
  pasadas se usa un script contra la BD (p. ej.
  `C:\Projects\twc\scripts\seed_german_posts.py`), nunca el panel.
- **No hay compose en producción.** Easypanel construye la imagen desde el
  `Dockerfile` y gestiona red, TLS y volumen; el `docker-compose.yml` del repo
  es sólo el gemelo de desarrollo.
- **El panel edita la BD viva.** Cada guardado es producción; no hay copia de
  staging.
- **`manage.py` jamás sin `--database admin_auth`** para comandos de Django:
  el alias `default` es el MySQL compartido y el panel sólo lo refleja
  (`managed=False`).

## 11. Checklist de aceptación

- [ ] `GET /healthz` → 200 `ok`, desde fuera y desde dentro del contenedor
- [ ] El contenedor sigue `healthy` pasados 2 minutos (sin `term` a los ~70 s)
- [ ] `GET /login/` → 200 con formulario y token CSRF
- [ ] Login correcto → `/panel/` con los posts reales (mismo número que `/blog/load/content` del sitio)
- [ ] Editar el título de un post en el panel se refleja en el sitio al recargar
- [ ] `admin.thewhitecode.com` resuelve a `91.194.91.37` y sirve HTTPS con certificado válido
- [ ] `python scripts/verify_deploy.py --base https://<dominio>` → PASS
