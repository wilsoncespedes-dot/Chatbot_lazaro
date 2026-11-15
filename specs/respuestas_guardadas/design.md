# #51 respuestas_guardadas — Design

Solo cambia el **orchestrator**. Panel HTML en servidor sin JS (como #41/#50),
misma sesión, CSRF y `panel_audit`. Cierra la parte de S8 de #41 correspondiente
a respuestas guardadas. Sin servicios ni dependencias nuevas; no se copia código
de terceros. El patrón replica las etiquetas de #50 (`/admin/etiquetas`).

## Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/annotations.py` | Añade `validate_saved_reply_title`, `validate_saved_reply_text` (R8, R9). |
| `.../domain.py` | `SavedReply`, `SavedReplyNotFound`, `SavedReplyVariablesNotAllowed`; `create_saved_reply`, `update_saved_reply`, `set_saved_reply_active`, `list_saved_replies`; `CaseView` gana `saved_replies`, `selected_reply`, `reply_notice`; `advisor_case_view(..., reply_id=None)` (R1–R4, R8–R14, R17–R20). |
| `.../adapters/repository.py` | Protocol + Fake + Postgres: tabla y métodos (R24). |
| `.../admin_routes.py`, `admin.py` | `GET/POST /admin/respuestas…`, `render_saved_replies`, enlace de navegación (R1–R7, R12, R21). |
| `.../advisor_routes.py` | `case_page` lee `respuesta` y lo pasa a `advisor_case_view` (R13, R14, R20). |
| `.../advisor_panel.py` | Selector (formulario GET) y `textarea` prellenado; sin selector con ventana cerrada (R13, R14, R17, R18, R21). `ERROR_MESSAGES` añade `saved_reply_not_found`, `saved_reply_variables_not_allowed`. |
| `.../config.py`, `.env.example`, `render.yaml` | Variables de R23. |
| `services/orchestrator/tests/test_saved_replies.py` | Nuevo: R1–R12, R21. |
| `.../tests/test_saved_replies_advisor.py` | Nuevo: R13–R20, R22. |
| `.../tests/test_saved_replies_pure.py` | Nuevo: validadores (R8, R9). |
| `.../tests/test_config.py`, `test_repository_schema.py` | R23, R24; rutas nuevas en el test de superficie `APIRoute`. |

## Modelo de datos

```sql
CREATE TABLE IF NOT EXISTS saved_replies (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
  active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL);
```

Sin `contact_id`: no es dato personal (R24).

## Firmas

```python
# annotations.py (puro)
def validate_saved_reply_title(raw: str, max_chars: int) -> str   # strip, sin control chars
def validate_saved_reply_text(raw: str, max_chars: int) -> str    # strip, permite \n; rechaza { } ${ %(

# domain.py
@dataclass(frozen=True)
class SavedReply: id: str; title: str; body: str; active: bool; updated_at: datetime
class SavedReplyNotFound(DomainError): code = "saved_reply_not_found"; status_code = 404
class SavedReplyVariablesNotAllowed(DomainError): code = "saved_reply_variables_not_allowed"; status_code = 422

def create_saved_reply(title: str, body: str, settings, adapters) -> SavedReply
def update_saved_reply(reply_id: str, title: str, body: str, settings, adapters) -> None
def set_saved_reply_active(reply_id: str, active: bool, adapters) -> None
def list_saved_replies(adapters, *, only_active: bool = False) -> list[SavedReply]
```

Los validadores puros lanzan `PanelValidationError` (422) para vacío/longitud/
control y `SavedReplyVariablesNotAllowed` para marcadores de variable. El rol
`admin` lo comprueba la ruta, con el patrón de `/admin/etiquetas`. El tope (R10)
usa `repo.count_saved_replies()` y lanza `PanelValidationError`.

`advisor_case_view` ya autoriza (`handover.authorize(..., "reply")`) y calcula
`window` antes de armar la vista; solo después: `saved_replies =
list_saved_replies(only_active=True)` si `window != "closed"`, si no `()` (R18).
`selected_reply` es la respuesta activa con `reply_id` solo si `window !=
"closed"`; si `reply_id` no existe o está inactiva queda `None` y
`reply_notice=True` (R17). Al leerse tras la autorización, R20 se cumple por
construcción (mismo error que sin `?respuesta=`).

UI sin JS: formulario `GET /asesor/cases/{id}` con `<select name="respuesta">` y
botón "Cargar"; el `textarea` de `/asesor/reply` se rellena con
`_esc(selected_reply.body)`. El envío usa el `POST /asesor/reply` existente sin
cambios: el servidor solo recibe el texto del formulario, nunca un
`saved_reply_id` (R15, R16, R19, R22). Auditoría de administración con
`_audit(actor, "saved_reply_*", resultado, adapters, target=id)` y sin texto (R5).

## Config (sección "respuestas guardadas (#51)")

| Variable | Default | Rango |
|---|---|---|
| `SAVED_REPLY_TITLE_MAX_CHARS` | `80` | 1–200 |
| `SAVED_REPLY_TEXT_MAX_CHARS` | `1000` | 1–4096 |
| `SAVED_REPLIES_MAX` | `100` | 1–500 |

## Supuestos a confirmar (defaults seguros, no bloquean)

- **S1 Variables**: se interpretan como cualquier `{`, `}`, `${` o `%(`; se rechazan
  al guardar. Más estricto que necesario, evita plantillas con datos de cliente.
- **S2 Visibilidad**: todas las respuestas activas las ven los asesores y
  supervisores con permiso sobre el caso; no hay respuestas por asesor ni por canal.
- **S3 Sin borrado**: solo se desactiva (lo pide el acceptance); sin DELETE.
- **S4 Carga no auditada**: cargar una respuesta no se audita; el envío ya queda
  auditado como `reply` (sin copiar texto).
- **S5 Retención**: no se purgan (no son datos personales).

## Alternativas descartadas

- **Selector con JavaScript que rellena el textarea**: el panel es sin JS y exigiría
  una CSP más laxa; la carga por GET con `?respuesta=` es verificable en servidor y
  mantiene el envío en el `POST /asesor/reply` existente.
- **Enviar `saved_reply_id` en `POST /asesor/reply`**: el servidor resolvería el
  texto y se perdería la edición del asesor; además crearía otra ruta de envío
  fuera de las reglas de respuesta.
- **Reutilizar los textos del flujo (`/admin/texts`)**: son claves fijas del bot,
  no una lista libre de respuestas.

## Dependencias

Ninguna nueva.
