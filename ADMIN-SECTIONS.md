# Secciones del panel — qué es cada una

El panel (http://localhost:8805) es la interfaz de administración sobre la
**base de datos compartida** de la app FastAPI (`TheWhiteCode`): en prod es el
MySQL compartido (`twc/config/.env`), en tests el `test_db.sqlite` local que
comparten ambas apps. Todos los modelos son *mirrors* `managed=False`
(`panel/models.py`) — Django **no migra** ese esquema, la app FastAPI es el
*system of record*. Regla: un cambio de esquema se hace en la app, nunca en el
panel.

> ⚠️ "Usuarios del sitio" (esta página) son las cuentas de la app compartida
> (tabla `users`). "Usuarios" (la otra entrada del índice) es el auth del
> propio panel (sqlite local `.admin_auth/`), nada que ver con el sitio.

Cada sección: qué almacena, **quién la escribe** (feature de la app) y qué
puedes hacer con ella en el panel.

## Usuarios del sitio — `users`

Cuentas reales del sitio: registro/verificación, roles, perfil público
(foto, frase, redes, skills, portafolio JSON), contraseña (argon2id o hash
legacy sha256 sin migrar — esas no pueden iniciar sesión).

- **La escribe**: registro, login, verificación de email, perfil público.
- **En el panel**: editar perfil/rol; acciones en masa `marcar activo` /
  `marcar inactivo` / `marcar confirmado`; borrar seleccionados (Django
  default). `created_at`/`updated_at`/`legacy_user_id` son solo lectura.

## Posts del blog — `blog_posts`

Posts EditorJS: contenido (JSON), slug, autor, publicado, fecha, vistas,
imagen destacada, tags, categoría.

- **La escribe**: el editor de posts del sitio (y la migración legacy).
- **En el panel**: CRUD completo; slug autogenerado del título (único:
  `-2`, `-3`…), tags como lista separada por comas, categoría en `<select>`
  desde `blog_categories`, thumbnail de la imagen destacada en el form.

## Categorías del blog — `blog_categories`

Categorías 1..23 (seed) + las que se añadan; la app **solo las lee**
(`blog_category_integer` en el post), así que el panel es el único
administrador.

- **La escribe**: el panel (y `python manage.py seed_categories`).
- **En el panel**: crear (slug autogenerado, único con sufijo automático),
  renombrar (el slug **no** cambia), borrar.

## Comentarios — `blog_comments`

Comentarios EditorJS sobre posts, con respuestas (`parent_id`), aprobados o
no. Un comentario nuevo notifica al autor del post.

- **La escribe**: el formulario de comentarios de la página del post
  (`POST /blog/comment`, EditorJS).
- **En el panel**: moderar — editar contenido, acciones en masa
  `aprobar` / `rechazar`; post/autor/fechas solo lectura.

## Reacciones — `blog_reactions`

`Like` / `Love` / `Surprised` / `Dislike` sobre posts. Una por (post,
usuario, tipo) — constraint única en el esquema compartido: clicar el mismo
tipo la quita, otro tipo la reemplaza.

- **La escribe**: los 4 botones de la página del post (`POST /blog/reaction`).
- **En el panel**: **solo lectura** (ledger).

## Salas de chat — `chat_rooms`

Salas persistentes del chat en tiempo real; las no-default se limpian con un
job diario.

- **La escribe**: el chat (crear sala) + el job diario de limpieza.
- **En el panel**: administrar salas (renombrar, default sí/no, borrar).

## Contact email sends — `contact_email_sends`

Ledger de rate-limit del formulario de contacto: una fila por envío SMTP
exitoso (**1 envío por IP cada 30 días**). Append-only.

- **La escribe**: la ruta de contacto, al entregar el email.
- **En el panel**: **solo lectura** (ni borrar: es el contador del límite).

## Contact messages — `contact_messages`

Mensajes del formulario de contacto (nombre, email, asunto, texto).

- **La escribe**: el formulario de contacto del sitio.
- **En el panel**: leer, responder por email, acciones en masa
  `resolver` / `reabrir`.

## Media files — `media_files`

Registro de archivos subidos (nombre original/almacenado, MIME, tamaño,
checksum SHA, categoría). **Los bytes viven en el volume de uploads, no en
la DB** — borrar la fila no borra el archivo.

- **La escribe**: los endpoints de upload (imagen de perfil, imagen del
  post, por URL…).
- **En el panel**: listar/ver, editar metadatos (p. ej. `category`);
  `id`/`checksum`/`created_at` solo lectura.

## Notifications — `notifications`

Notificaciones in-app por usuario: "new comment on X", mensajes, etc.
(`data` JSON lleva post/comment/slug para el enlace).

- **La escribe**: la app al comentar, al enviar mensajes, etc.
- **En el panel**: leer, editar, acciones en masa `marcar leída` /
  `marcar no leída`; `id`/`created_at` solo lectura.

## Payments — `payments`

Pagos de la app (monto en céntimos, moneda, estado, proveedor, referencia
del proveedor).

- **La escribe**: el flujo de pagos de la app.
- **En el panel**: **solo lectura** (ledger financiero).

## Schancoin: wallets / blocks / transactions — `schancoin_*`

Ledger de la cripto SCH: metadatos de wallets (el balance lo deriva el
servicio coin, no se edita aquí), bloques (hash, nonce, dificultad,
merkle) y transacciones (envío, firma, coinbase, estado).

- **La escribe**: el servicio Schancoin (mining/consenso) en su contenedor.
- **En el panel**: **solo lectura** (los tres).

## X402 payments — `x402_payments`

Ledger append-only de micropagos x402 (USDC) liquidados: tx hash único,
pagador, endpoint cobrado, importe en micro-USDC, red.

- **La escribe**: el middleware x402 de la app al liquidar un pago.
- **En el panel**: **solo lectura**.

## Analytics events (Visitas) — `analytics_events`

Eventos de analítica: `page_view` = visita a página; path, IP, referrer,
user-agent, post, país van en `extra_metadata` (JSON).

- **La escribe**: el tracking de la app en cada vista de página.
- **En el panel**: **solo lectura**, con jerarquía por fecha, filtro por
  tipo de evento y búsqueda por usuario/sesión — es el panel de métricas.

---

### Resumen: ¿dónde se puede escribir?

| Sección | Editable | Acciones en masa |
|---|---|---|
| Usuarios del sitio | ✅ (perfil/rol) | activo / inactivo / confirmado / **borrar** |
| Posts del blog | ✅ completo | — |
| Categorías del blog | ✅ (nombre) | — |
| Comentarios | ✅ (moderación) | aprobar / rechazar |
| Salas de chat | ✅ | — |
| Media files | ⚠️ metadatos | — |
| Notifications | ⚠️ (texto/estado) | leer / no leer |
| Contact messages | ⚠️ (estado) | resolver / reabrir |
| Reacciones, Payments, X402, Contact email sends, Schancoin, Analytics | ❌ read-only | — |
