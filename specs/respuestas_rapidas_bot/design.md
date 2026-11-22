# Design — #71 respuestas_rapidas_bot

Sigue el patrón de respuestas guardadas (#51: `admin_routes.py`, `admin.py`, `annotations.py`,
`test_saved_replies*.py`) y de #70 (`purchase_intent.py` puro + enganche en `_resolve_and_run`).
No se reutiliza código externo.

## Archivos

Crear (en `services/orchestrator/orchestrator/`):
- `quick_replies.py` — puro, sin IO: normalización (reusa `classifier.normalize_text`/`_phrase`),
  `parse_triggers`, `pick_reply`, `validate_image`, `build_blocks`.
- `quick_replies_routes.py` — router FastAPI: páginas admin y `GET /media/respuestas/{id}`.
  Se registra en `main.create_app` junto a los demás routers.

Modificar:
- `domain.py` — dataclasses `QuickReply`, `QuickReplyImage`; errores `QuickReplyInvalid`
  (`quick_reply_invalid`, 422), `QuickReplyImageInvalid` (`quick_reply_image_invalid`, 422),
  `QuickReplyNotFound` (`quick_reply_not_found`, 404); funciones CRUD `create_quick_reply`,
  `update_quick_reply`, `set_quick_reply_active`, `list_quick_replies`; gancho
  `_try_quick_reply` y `_send_blocks`; llamada en `_resolve_and_run`.
- `adapters/repository.py` — protocolo, `FakeRepository` y `PostgresRepository` (tablas en el DDL).
- `channels.py` — `ChannelPolicy.supports_images: bool = False`; `policy_from_info` lo toma de
  `info.capabilities.supports_images`; `default_policy` lo deja en `False`.
- `config.py` — `quick_reply_image_max_bytes` (`QUICK_REPLY_IMAGE_MAX_BYTES`, default 2097152,
  `ge=1024, le=5242880`).
- `admin.py` — `render_quick_replies` y entrada de menú `/admin/respuestas-rapidas`.
- `.env.example` — la variable nueva.
- `contracts/CONTRATOS.md` — nota breve: `GET /media/respuestas/{id}` es público del orquestador (no
  es ruta entre servicios; no cambia modelos).

## Esquema

```
quick_replies(id TEXT PK, name TEXT NOT NULL, triggers JSONB NOT NULL,
  blocks JSONB NOT NULL, image_id TEXT NULL, active BOOLEAN NOT NULL,
  priority INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)
quick_reply_images(id TEXT PK, content_type TEXT NOT NULL, data BYTEA NOT NULL,
  size INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL)
```
`CREATE TABLE IF NOT EXISTS`; sin inserts de contenido (R36).
`triggers` guarda la lista tal cual la escribió el admin; se normaliza al comparar.
`blocks` guarda bloques de respuesta (`text`, `options` sin ids, `link`, `image` con URL https
externa). La imagen subida no se guarda en `blocks`: se referencia por `image_id` y se construye
su URL absoluta al enviar (`{IDENTITY_PUBLIC_BASE_URL}/media/respuestas/{image_id}`), para no
fijar un dominio en BD.

## Firmas

```python
# quick_replies.py
def parse_triggers(raw: str) -> list[str]            # una por línea o coma; QuickReplyInvalid (R5, R6)
def pick_reply(text: str, replies: Sequence[QuickReply]) -> QuickReply | None   # R13-R16
def validate_image(data: bytes, max_bytes: int) -> str   # devuelve content_type; QuickReplyImageInvalid (R24, R25)
def build_blocks(reply: QuickReply, *, supports_images: bool,
                 image_url: str | None) -> list[ResponseBlock]    # R32-R35
# domain.py
def create_quick_reply(form: QuickReplyForm, image: bytes | None, settings, adapters) -> QuickReply
def update_quick_reply(reply_id: str, form: QuickReplyForm, image: bytes | None, remove_image: bool, settings, adapters) -> QuickReply
def set_quick_reply_active(reply_id: str, active: bool, adapters) -> None
def _try_quick_reply(contact, text, settings, adapters) -> bool   # True si respondió (R17-R23)
def _send_blocks(contact, history_text: str, blocks, adapters) -> bool   # como `_send` pero con bloques
```
Repositorio: `add_quick_reply`, `update_quick_reply`, `set_quick_reply_active`, `get_quick_reply`,
`list_quick_replies(only_active=False)`, `add_quick_reply_image`, `get_quick_reply_image`,
`delete_quick_reply_image`.

## Decisiones

- **Coincidencia**: se normaliza con `classifier.normalize_text` + separación de palabras y se
  comprueba que la secuencia de palabras del disparador aparezca completa y contigua en el texto
  (se rellena con espacios para evitar coincidencias dentro de una palabra: "pago" no coincide con
  "pagos"). Es distinta a la subcadena de `matches_any` a propósito: las respuestas rápidas
  disparan una respuesta final y los falsos positivos son más caros. El texto del cliente es solo
  dato: nunca se interpola en la respuesta.
- **Punto de enganche**: dentro de `_resolve_and_run`, después de la detección de intención de
  compra por frase (#70) y antes del router, solo si `state == ACTIVE`. Así supresión, traspaso a
  asesor y frustración tienen prioridad y no se pierde el aviso de compra. Tras responder se llama a
  `_create_case_after_intent`. Los estados con consentimiento o asesor nunca llegan a
  `_resolve_and_run`, y NO_ACCESS se excluye por la condición explícita (R18).
- **Fallo**: `_try_quick_reply` envuelve lectura y envío; ante excepción registra
  `logger.error("quick_reply_failed")` y devuelve `False` (R23). `_send_blocks` devuelve `False` si
  `ServiceUnavailable`, y en ese caso se continúa al flujo normal.
- **Degradación**: decide el orquestador con `channel_policy(adapters, contact.channel).supports_images`
  (sin comparar nombres de canal, regla de #65). El gateway sigue degradando como respaldo.
- **Imagen**: validación por firma binaria (PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`, WebP
  `RIFF....WEBP`); el `Content-Type` del formulario se ignora. Respuesta de media con
  `Content-Type` detectado, `X-Content-Type-Options: nosniff`, `Cache-Control: public, max-age=3600`.
  Id aleatorio `uuid4().hex`; la ruta valida `^[0-9a-f]{32}$` (R27). El archivo se lee con
  `python-multipart` (ya en `requirements.txt`, como la subida de manuales) acotando el tamaño al
  límite configurado + 1 byte antes de validar.
- **Roles y CSRF**: igual que respuestas guardadas: solo `admin`; 403 auditado; CSRF auditado.
  Acciones de auditoría: `quick_reply_created|updated|active_changed|viewed`.
- **Formulario** (HTML sin JS): nombre, disparadores (uno por línea), texto, opciones (una por
  línea, máx. 10 y 20 caracteres cada una según contrato), etiqueta y URL de enlace, imagen
  (archivo o URL https), texto alternativo (obligatorio si hay imagen), prioridad, activa. El orden
  de bloques es fijo: texto, imagen, opciones, enlace.

## Alternativa descartada

Guardar las respuestas en `settings`/variables de entorno como lista JSON (como las frases de #70).
Se descarta: las respuestas llevan bloques, imagen y prioridad por elemento, y exigen alta/baja
individual con auditoría; una lista plana en configuración no lo permite y se acercaría a escribir
contenido de negocio en el entorno. Tampoco se almacena la imagen en disco local: el despliegue en
la nube tiene sistema de archivos efímero, por eso va en BD (`BYTEA`, tope de 5 MiB).

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar (valores por defecto configurables)

- Tamaño máximo de imagen: 2 MiB (`QUICK_REPLY_IMAGE_MAX_BYTES`); WhatsApp admite hasta 5 MiB.
- La URL pública de las imágenes subidas usa `IDENTITY_PUBLIC_BASE_URL` (ya existente); no se crea
  otra variable.
- Solo estado `active`; `no_access` no recibe respuestas rápidas porque su respuesta es fija.
- Sin borrado de respuestas: se desactivan (consistente con #51).
