# #50 notas_internas_y_etiquetas — Design

Solo cambia el **orchestrator**. Panel HTML en servidor sin JS (como #41), misma
sesión, CSRF y `panel_audit`. Cierra la parte de S8 de #41 correspondiente a
notas y etiquetas (respuestas guardadas = #51). Sin servicios ni dependencias
nuevas; no se copia código de terceros.

## Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/annotations.py` | **Nuevo**, puro: `validate_note_text`, `validate_tag_name`, `normalize_tag_key` (R5, R17, R18). |
| `.../domain.py` | Dataclasses `CaseNote`, `CaseTag`; excepciones `TagNameTaken`, `TagNotFound`, `NoteNotFound`; `CaseView` gana `notes`, `tags`, `assignable_tags`; `InboxRow` gana `tags`; `advisor_inbox`/`advisor_all_cases` ganan `tag`; funciones de notas y etiquetas (abajo) (R1–R9, R14–R28, R32–R35). |
| `.../adapters/repository.py` | Protocol + Fake + Postgres: tablas, métodos, y borrados en `execute_suppression`, `purge_personal_data`, `delete_contact_content` (R10, R35–R39). |
| `.../advisor_routes.py` | Rutas de notas/etiquetas del asesor; `tag` en bandeja; auditoría (R1, R7, R20, R21, R26, R30–R34). |
| `.../advisor_panel.py` | Secciones de notas y etiquetas en `render_advisor_case`; columna y selector en `render_advisor_cases` (R2, R25, R28, R29). `ERROR_MESSAGES` añade `tag_name_taken`, `note_not_found`, `tag_not_found`. |
| `.../admin_routes.py`, `admin.py` | `GET/POST /admin/etiquetas…`; `render_tags`; enlace "Etiquetas" en la navegación (R14–R19). |
| `.../config.py`, `.env.example`, `render.yaml` | Variables de R40. |
| `docs/architecture.md` | Una línea: notas/etiquetas en tablas propias del orchestrator, nunca en `messages`. |
| `services/orchestrator/tests/test_notes.py` | Nuevo: R1–R9, R29–R32, R34. |
| `.../tests/test_notes_isolation.py` | Nuevo: R10–R13 (seguridad). |
| `.../tests/test_tags.py` | Nuevo: R14–R28, R33. |
| `.../tests/test_notes_privacy.py` | Nuevo: R35–R38. |
| `.../tests/test_annotations_pure.py` | Nuevo: validadores. |
| `.../tests/test_config.py`, `test_repository_schema.py` | R39, R40; rutas nuevas en el test de superficie `APIRoute`. |

## Modelo de datos

```sql
CREATE TABLE IF NOT EXISTS case_notes (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, contact_id TEXT NOT NULL,
  author_profile_id TEXT NOT NULL, body TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS case_notes_case ON case_notes (case_id, created_at);
CREATE INDEX IF NOT EXISTS case_notes_contact ON case_notes (contact_id);
CREATE TABLE IF NOT EXISTS case_tags (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
  active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS case_tag_assignments (
  case_id TEXT NOT NULL, tag_id TEXT NOT NULL, contact_id TEXT NOT NULL,
  assigned_by TEXT NOT NULL, assigned_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (case_id, tag_id));
CREATE INDEX IF NOT EXISTS case_tag_assignments_tag ON case_tag_assignments (tag_id);
CREATE INDEX IF NOT EXISTS case_tag_assignments_contact ON case_tag_assignments (contact_id);
```

`contact_id` se guarda desnormalizado (resuelto con `get_case_link` al crear)
para que supresión, retención y rechazo de privacidad borren sin depender de
`case_links`, que se elimina antes en esos flujos. `name_key = name.casefold()`
con espacios colapsados (R18). El cuerpo de la nota vive solo en `case_notes`
(R10): ningún lector de `messages`, `events`, `tool_calls`, memoria ni
resúmenes la consulta, y el prompt de la IA se construye únicamente desde esas
fuentes.

## Firmas

```python
# annotations.py (puro)
def validate_note_text(raw: str, max_chars: int) -> str          # strip; PanelValidationError
def validate_tag_name(raw: str, max_chars: int) -> str           # strip, colapsa espacios, sin control chars
def normalize_tag_key(name: str) -> str

# domain.py
@dataclass(frozen=True)
class CaseNote: id: str; case_id: str; author_profile_id: str; author_username: str | None; body: str; created_at: datetime
@dataclass(frozen=True)
class CaseTag: id: str; name: str; active: bool

class TagNameTaken(DomainError):  code = "tag_name_taken"; status_code = 409
class TagNotFound(DomainError):   code = "tag_not_found"; status_code = 404
class NoteNotFound(DomainError):  code = "note_not_found"; status_code = 404

def add_case_note(case_id: str, actor: Profile, text: str, settings, adapters) -> CaseNote
def delete_case_note(case_id: str, note_id: str, actor: Profile, settings, adapters) -> None
def create_case_tag(name: str, settings, adapters) -> CaseTag
def rename_case_tag(tag_id: str, name: str, settings, adapters) -> None
def set_case_tag_active(tag_id: str, active: bool, adapters) -> None
def list_case_tags(adapters, *, only_active: bool = False) -> list[CaseTag]
def assign_case_tag(case_id: str, tag_id: str, actor: Profile, settings, adapters) -> None
def remove_case_tag(case_id: str, tag_id: str, actor: Profile, settings, adapters) -> None
```

`_authorize_case_annotation(case_id, actor, adapters)` reutiliza el bloque de
`advisor_client_memory`: `ensure_roster_ready` → `handover.authorize(case_id,
id, "reply")` → `AuthorizationDenied` → `_raise_authorization_error`;
`ServiceUnavailable` → `UpstreamError`; contacto del caso vía
`repo.get_case_contact` (`None` → `CaseNotFound`). `add_case_note` valida
texto (R5), cuenta (R6), guarda con `adapters.new_id()`/`clock()` y **no
llama** a gateway ni a `add_message`/`add_event` (R11, R13). `delete_case_note`:
`get_case_note(note_id)` ausente o `case_id` distinto → `NoteNotFound` (R9);
`author_profile_id != actor.id` → `AdvisorForbidden` (R8).
`assign_case_tag`: etiqueta ausente o inactiva → `PanelValidationError` (R22);
tope (R23); `INSERT … ON CONFLICT DO NOTHING` (R20). `remove_case_tag` no exige
etiqueta activa (R21). Orden de autorización siempre antes de validar datos.

`advisor_case_view` añade al final: `notes = repo.list_case_notes(case_id)`,
`tags` (asignadas, con `active`), `assignable_tags` (activas no asignadas).
Las notas se leen solo después de `advisor_client_memory` (que ya autoriza),
por lo que R3/R4 se cumplen por construcción. Filtro: `advisor_inbox(...,
tag: str | None = None)` valida `tag` antes de `list_cases` (R27); tras
`handover.list_cases` obtiene `repo.case_tag_map(case_ids)` y descarta lo que
no lo tenga (el filtro se aplica junto a canal/asignación, también en
`scope="all"`). Filas: `tags` = nombres de etiquetas activas (R28).

Rutas del asesor (todas con `_require_session`, `_require_csrf`, `_valid_case_id`,
auditoría con `_audit`/`_audit_error`, redirección 303 a
`/asesor/cases/{id}`): `POST …/notes`, `POST …/notes/{note_id}/delete`,
`POST …/tags` (campo `tag_id`), `POST …/tags/{tag_id}/remove`. Admin:
`GET /admin/etiquetas`, `POST /admin/etiquetas`, `POST /admin/etiquetas/{id}`,
`POST /admin/etiquetas/{id}/activa`, con la sesión `admin` y patrón de
`/admin/categories`; el actor de la auditoría es el perfil admin. Acciones de
auditoría y `target` según R32–R34; el texto nunca se pasa a `record_panel_audit`.

Repositorio (Protocol + Fake + Postgres): `add_case_note`, `list_case_notes`,
`get_case_note`, `delete_case_note`, `count_case_notes`, `create_case_tag`
(devuelve `False` si `name_key` existe), `rename_case_tag` (idem),
`set_case_tag_active`, `get_case_tag`, `list_case_tags`, `add_case_tag`,
`remove_case_tag`, `count_case_tags`, `case_tag_map(case_ids) -> dict[str, tuple[str,...]]`.
Borrados: `execute_suppression` borra, dentro de su transacción y antes del
`UPDATE` de estado, `case_notes` y `case_tag_assignments` cuyo `contact_id` esté
entre los de `client_sessions` del perfil y suma `case_notes` a `counts`
(R35, R36); `purge_personal_data` borra `case_notes` con `created_at < cutoff`
y notas/asignaciones con `contact_id` en `inactive_ids`, y añade `case_notes`
al dict (R37); `delete_contact_content` borra ambas por `contact_id` (R38).
La instrucción SQL de supresión se hace con `contact_id = ANY(%s)`; el Fake
replica con filtros de lista.

## Config (sección "notas y etiquetas (#50)")

| Variable | Default | Rango |
|---|---|---|
| `CASE_NOTE_MAX_CHARS` | `1000` | 1–4000 |
| `CASE_NOTES_MAX_PER_CASE` | `50` | 1–500 |
| `CASE_TAG_NAME_MAX_CHARS` | `40` | 1–100 |
| `CASE_TAGS_MAX_PER_CASE` | `10` | 1–50 |

## Supuestos a confirmar (defaults seguros, no bloquean)

- **N1 Quién borra notas**: solo el autor. Un supervisor no borra notas ajenas
  (se pueden añadir excepciones en otra feature).
- **N2 Quién ve notas**: cualquiera con `authorize(reply)` sobre el caso (el
  supervisor las ve en su vista global solo si handover le autoriza `reply`).
- **N3 Etiquetas desactivadas**: se conservan en los casos y se pueden quitar;
  no se ofrecen para asignar ni filtrar; no se muestran en las filas.
- **N4 Retención**: las notas siguen el corte de `messages` (mismos días de
  retención); sin ajuste propio. Las etiquetas (definición) no son datos
  personales y no se purgan; `panel_audit` sigue sin purgarse (S7).
- **N5 Notas sin edición**: solo crear/borrar; editar queda fuera.

## Alternativas descartadas

- **Guardar notas como filas de `messages` con `role="note"`**: toda lectura de
  historial, resumen, memoria y prompt tendría que filtrar el rol; un olvido
  filtraría la nota al cliente o a la IA. Una tabla propia hace R10–R13
  verdaderas por construcción.
- **Etiquetas en handover**: handover no necesita saber de ellas y exigiría
  contrato nuevo; la bandeja ya une datos del orchestrator por `case_id`.
- **Etiquetas como texto libre por caso**: no permite que el administrador
  renombre/desactive ni filtrar de forma consistente.

## Dependencias

Ninguna nueva.
