# #40 memoria_por_cliente — Design

Todo vive en el **orchestrator**. Sin servicios, contratos ni dependencias
nuevas. La memoria se asocia al `profile_id` (= `cliente_id`) de las sesiones de
#38, nunca al chat; la conversación es la sesión de cliente (`client_sessions`).

## Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/memory.py` | **Nuevo**, puro (sin IO): `MEMORY_SUMMARY_PROMPT`, `MEMORY_CONTEXT_NOTE`, `SummaryAnswer`, `SummaryInvalid`, `session_window`, `in_window`, `is_sensitive`, `clean_memory_items`, `clean_summary`, `build_summary_prompt`, `parse_summary_answer`, `PromptContext`. |
| `services/orchestrator/orchestrator/domain.py` | `build_llm_prompt(question, chunks, context=None)`; `_memory_context`; `_summarize_session`; llamada desde `end_client_session` y `_tool_escalate`; `_handover` pasa `profile_id` a `link_case`; `advisor_client_memory`; `execute_suppression`; excepciones `SuppressionForbidden`, `SuppressionNotFound`, `SuppressionNotPending`. |
| `services/orchestrator/orchestrator/adapters/repository.py` | Tablas `client_memory`, `conversation_summaries`; columnas nuevas en `case_links` y `suppression_requests` (migración); métodos nuevos en `Repository`, `FakeRepository` y `PostgresRepository`; purga de `conversation_summaries`. |
| `services/orchestrator/orchestrator/config.py` | Variables `MEMORY_*` y `SUPPRESSION_EXECUTOR_ROLES` con validación (R52, R54). |
| `services/orchestrator/orchestrator/advisor_routes.py` | `GET /asesor/cases/{case_id}/memoria`. |
| `services/orchestrator/orchestrator/advisor_panel.py` | `render_advisor_memory(view, csrf)`; enlace "Memoria" por fila en `render_advisor_cases`. |
| `services/orchestrator/tests/test_memory.py` | Puros: ventana, filtro de sensibles, depuración, prompt y parser. |
| `services/orchestrator/tests/test_memory_flow.py` | Generación, entrega a la IA, continuidad, aislamiento, fallos. |
| `services/orchestrator/tests/test_memory_panel.py` | Ruta del asesor y permisos. |
| `services/orchestrator/tests/test_memory_suppression.py` | `execute_suppression`, retención y no regresión de herramientas. |
| `services/orchestrator/tests/test_repository_schema.py` | Afirmar tablas, columnas y migraciones nuevas (si el archivo ya valida `_SCHEMA`/`_MIGRATIONS`). |
| `.env.example`, `render.yaml` | Variables nuevas (render: `MEMORY_ENABLED=false`). |
| `docs/architecture.md` | Una línea en §4 "Datos personales mínimos" apuntando a `memory.py` y `execute_suppression`. |

## Esquema (aditivo e idempotente)

En `_SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS client_memory (
  profile_id TEXT PRIMARY KEY,
  items JSONB NOT NULL,              -- lista de textos ya depurados
  source_session_id TEXT,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_summaries (
  session_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  summary TEXT NOT NULL,
  trigger TEXT NOT NULL,             -- session_end | escalation
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
```

En `_INDEXES`: `conversation_summaries_profile ON conversation_summaries
(profile_id, updated_at)`, `conversation_summaries_updated ON
conversation_summaries (updated_at)`, `client_sessions_profile ON
client_sessions (profile_id)`.

En `_MIGRATIONS` (al final):

```sql
ALTER TABLE case_links ADD COLUMN IF NOT EXISTS profile_id TEXT;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS executed_by TEXT;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS removed_counts JSONB;
```

`status = 'executed'` libera el índice único parcial de #39
(`suppression_requests_one_pending`), así que el cliente puede volver a pedir
supresión después.

## Firmas

### `memory.py` (puro)

```python
MEMORY_SUMMARY_PROMPT: str      # R20; JSON {"resumen": str, "memoria": [str]}
MEMORY_CONTEXT_NOTE: str        # se añade al system de RAG solo con contexto

@dataclass(frozen=True)
class SummaryAnswer: resumen: str; memoria: tuple[str, ...]
class SummaryInvalid(Exception): reason: str

@dataclass(frozen=True)
class PromptContext:
    memory: tuple[str, ...]
    history: tuple[tuple[str, str], ...]   # (role, text)

def session_window(started_at: datetime, last_activity_at: datetime,
                   ended_at: datetime | None, now: datetime,
                   idle_minutes: int) -> tuple[datetime, datetime, datetime]
    # (desde_inclusivo, hasta_inclusivo, límite_idle_exclusivo)
def in_window(at: datetime, window) -> bool
def is_sensitive(text: str, keywords: Sequence[str], min_digits: int) -> bool
def clean_memory_items(items: Sequence[str], keywords, min_digits,
                       max_items: int, max_chars: int) -> tuple[str, ...]   # R16, R17
def clean_summary(text: str, keywords, min_digits, max_chars: int) -> str   # R18
def build_summary_prompt(memory: Sequence[str],
                         messages: Sequence[tuple[str, str]]) -> tuple[str, str]  # R9
def parse_summary_answer(raw: str) -> SummaryAnswer   # lanza SummaryInvalid (R11)
```

- `is_sensitive`: `normalize_text` (de `classifier.py`) + subcadena por cada
  keyword normalizada; dígitos con `re.search(r"\d(?:[\s.\-]?\d){%d,}" %
  (min_digits - 1))`; correo con `r"[^\s@]+@[^\s@]+\.[^\s@]+"`.
- `build_summary_prompt`: user =
  `<memoria_actual><item>…</item>…</memoria_actual>\n<historial><mensaje
  rol="user|bot|advisor">…</mensaje>…</historial>`; neutraliza
  `</memoria_actual`, `</historial`, `</mensaje`, `</item` (como `_neutralize`).
- `parse_summary_answer`: `json.loads`; exige `dict` con exactamente
  `{"resumen", "memoria"}`, `resumen: str`, `memoria: list[str]`; cualquier otra
  forma → `SummaryInvalid("invalid_summary")`.

### `domain.py`

```python
def build_llm_prompt(question: str, chunks: list[SearchResult],
                     context: PromptContext | None = None) -> tuple[str, str]
```

Con `context=None` devuelve exactamente lo de hoy (R26). Con contexto: system =
`LLM_SYSTEM_PROMPT + " " + MEMORY_CONTEXT_NOTE` (la nota dice que `<memoria>` e
`<historial>` son datos de contexto, no fuentes: las citas y números siguen
saliendo solo de `<fragmento>`); user = `<memoria><item>…</item></memoria>\n
<historial><mensaje rol=…>…</mensaje></historial>\n` + bloques actuales
(`<pregunta>`, `<fragmento>`). Bloques vacíos se omiten. `validate_llm_answer`
no cambia.

```python
def _memory_context(contact: Contact, current_at: datetime,
                    settings, adapters) -> PromptContext | None
```

Devuelve `None` si `MEMORY_ENABLED=false` o `active_client_id(contact.id)` es
`None` (R23). Si no: memoria del `profile_id` de esa sesión pasada otra vez por
`clean_memory_items` (defensa en profundidad) y los últimos
`MEMORY_CONTEXT_MESSAGES` mensajes de la ventana con `at < current_at` (R21,
R22, R24). `_tool_rag` lo pasa a `build_llm_prompt`. `_resolve_and_run`
(router) y `_tool_client_data` (SQL) no lo usan (R25).

```python
def _summarize_session(session: ClientSession, trigger: Literal["session_end", "escalation"],
                       settings, adapters) -> None
```

1. `MEMORY_ENABLED=false` → retorno (R7).
2. `policy = resolve_identity_policy(...)`; ventana con `session_window`;
   `repo.session_messages(contact_id, desde, hasta, limite_idle,
   MEMORY_INPUT_MAX_MESSAGES)` (los últimos N en orden cronológico).
3. Descarta mensajes con `is_sensitive` (R15). Lista vacía → retorno (R8).
4. `memory = repo.get_client_memory(profile_id)`; `llm.complete(*build_summary_prompt(...))`.
5. `ServiceUnavailable` → evento `memory_failed:llm_unavailable`; `SummaryInvalid`
   → `memory_failed:invalid_summary`; retorno sin escribir (R11, R12).
6. `summary = clean_summary(...)`; `repo.upsert_conversation_summary(...)`
   (R3–R5). Si `trigger == "session_end"`:
   `repo.set_client_memory(profile_id, clean_memory_items(...), session.id, now)`
   (R6, R16, R17, R19).
7. Toda excepción no prevista se captura, se registra `memory_failed:error` y
   no se relanza: el cierre de sesión o el traspaso nunca fallan por memoria
   (R12). Nunca envía nada al gateway (R13).

Puntos de llamada:

- `end_client_session`: tras `repository.end_client_session(...)` devuelto
  `True` y antes del `notify`, si `reason != "suppression"`:
  `_summarize_session(replace(session, ended_at=now, end_reason=reason),
  "session_end", ...)` (R1). Cubre logout, idle (también el cierre perezoso en
  `login_client` desde otro canal, que da la continuidad de R14), revocación y
  cierre por administrador.
- `_tool_escalate`: en la rama no `repeated_failure` y en `repeated_failure`,
  si `_handover` devolvió `True` y hay sesión activa
  (`repo.get_active_session_by_contact`), `_summarize_session(session,
  "escalation", ...)` (R2, R4). No toca la memoria.

`_handover`: `repo.link_case(response.case_id, contact.id, now,
profile_id=active_client_id(contact.id, adapters))` (R31).

```python
@dataclass(frozen=True)
class SummaryView: session_id: str; channel: str; summary: str; trigger: str; updated_at: datetime
@dataclass(frozen=True)
class ClientMemoryView:
    case_id: str
    authenticated: bool
    items: tuple[str, ...]
    memory_updated_at: datetime | None
    summaries: tuple[SummaryView, ...]

def advisor_client_memory(case_id: str, advisor_id: str,
                          settings, adapters) -> ClientMemoryView
```

Orden: `handover.authorize(case_id, advisor_id, "reply")` (R27) →
`AuthorizationDenied` a `_raise_authorization_error` (R28, R29, R55);
`ServiceUnavailable` → `UpstreamError` (R56) → `get_case_contact` (`None` →
`CaseNotFound`, R55) → `get_case_profile(case_id)`; `None` →
`authenticated=False`, sin leer memoria (R32) → memoria y
`list_conversation_summaries(profile_id, MEMORY_PANEL_SUMMARIES)` (R30) →
evento `memory_viewed` (R33). Funciona con `MEMORY_ENABLED` en cualquier valor
(lo ya guardado se puede consultar).

```python
@dataclass(frozen=True)
class SuppressionExecution:
    request_id: str; profile_id: str; deleted: Mapping[str, int]; executed_at: datetime

def execute_suppression(request_id: str, actor_profile_id: str,
                        settings, adapters) -> SuppressionExecution
```

1. `actor = repo.get_profile(actor_profile_id)`; `None` o rol fuera de
   `SUPPRESSION_EXECUTOR_ROLES` → `SuppressionForbidden` (R36).
2. `req = repo.get_suppression_request(request_id)`; `None` →
   `SuppressionNotFound` (R37); `status != "pending"` → `SuppressionNotPending`
   (R38).
3. `session = repo.get_active_session_by_profile(req.profile_id)`; si existe,
   `end_client_session(session, "suppression", settings, adapters,
   notify=False)` (R39; no resume por R1).
4. `deleted = repo.execute_suppression(request_id, actor_profile_id,
   policy.session_idle_minutes, now)`; `None` (otro ejecutor ganó la carrera) →
   `SuppressionNotPending` (R38).
5. `add_identity_audit(req.profile_id, None, "suppression_executed",
   f"request:{id} by:{actor}", now)` (R45).

Sin ruta HTTP en esta feature: la cola y el botón de ejecución son de #41,
que llamará a `execute_suppression` (supuesto S5). Ninguna herramienta de #39
la invoca (R46).

### `repository.py` (Protocol + Fake + Postgres)

```python
def session_messages(self, contact_id: str, since: datetime, until: datetime,
                     idle_limit: datetime, limit: int) -> list[tuple[str, str, datetime]]
def get_client_memory(self, profile_id: str) -> tuple[tuple[str, ...], datetime | None]
def set_client_memory(self, profile_id: str, items: Sequence[str],
                      source_session_id: str, now: datetime) -> None        # upsert
def upsert_conversation_summary(self, session_id: str, profile_id: str,
                      contact_id: str, channel: str, summary: str,
                      trigger: str, now: datetime) -> None                  # ON CONFLICT (session_id) DO UPDATE
def list_conversation_summaries(self, profile_id: str, limit: int) -> list[SummaryView]
def link_case(self, case_id: str, contact_id: str, at: datetime,
              profile_id: str | None = None) -> None                        # firma ampliada, compatible
def get_case_profile(self, case_id: str) -> str | None
def get_suppression_request(self, request_id: str) -> StoredSuppressionRequest | None
def execute_suppression(self, request_id: str, executed_by: str,
                        idle_minutes: int, now: datetime) -> dict[str, int] | None
```

`execute_suppression` en Postgres, una transacción:

1. `SELECT profile_id FROM suppression_requests WHERE id = %s AND status =
   'pending' FOR UPDATE` → sin fila: `ROLLBACK`, `None`.
2. `SELECT contact_id, started_at, last_activity_at, ended_at FROM
   client_sessions WHERE profile_id = %s`.
3. Por cada sesión, `DELETE FROM messages WHERE contact_id = %s AND at >= %s
   AND at <= %s AND at < %s` con la ventana de `session_window` (R42, R43).
4. `DELETE FROM conversation_summaries WHERE profile_id = %s` (R41).
5. `DELETE FROM client_memory WHERE profile_id = %s` (R40).
6. `UPDATE suppression_requests SET status = 'executed', executed_at = %s,
   executed_by = %s, removed_counts = %s WHERE id = %s` (R44).

Claves de `deleted`: `messages`, `conversation_summaries`, `client_memory`.
`FakeRepository` reproduce lo mismo bajo su lock y expone `client_memory:
dict[str, StoredClientMemory]`, `conversation_summaries: dict[str,
StoredConversationSummary]`, `case_profiles: dict[str, str | None]`.
`StoredSuppressionRequest` gana `executed_at`, `executed_by`,
`removed_counts` con default `None`.

`purge_personal_data` (#27): añade `DELETE FROM conversation_summaries WHERE
updated_at < cutoff` y la clave `conversation_summaries` (R53). No toca
`client_memory` (R47). Al borrar contactos inactivos, `case_links` se borra
como hoy (incluida la columna nueva).

### `advisor_routes.py` / `advisor_panel.py`

`GET /asesor/cases/{case_id}/memoria`: `_require_session` → `_advisor_id`
(`telegram_not_linked` 403 como hoy) → `_valid_case_id` (422) →
`advisor_client_memory` → `render_advisor_memory`. `DomainError` →
`_domain_error` (403/404/409/502). La plantilla usa `_esc` en todo texto (R34):
lista de elementos de memoria con su fecha y tabla de resúmenes (canal, fecha,
motivo, texto); si `authenticated=False`, solo el aviso "Sin cliente
autenticado" (R32). `render_advisor_cases` añade un enlace `Memoria` por caso.

## Config (`.env.example`, sección "memoria por cliente (#40)")

| Variable | Default | Rango / forma |
|---|---|---|
| `MEMORY_ENABLED` | `false` | bool |
| `MEMORY_MAX_ITEMS` | `20` | 1–100 |
| `MEMORY_ITEM_MAX_CHARS` | `300` | 50–1000 |
| `MEMORY_SUMMARY_MAX_CHARS` | `1500` | 200–4000 |
| `MEMORY_INPUT_MAX_MESSAGES` | `200` | 10–1000 |
| `MEMORY_CONTEXT_MESSAGES` | `6` | 0–20 |
| `MEMORY_PANEL_SUMMARIES` | `5` | 1–50 |
| `MEMORY_SENSITIVE_MIN_DIGITS` | `6` | 4–20 |
| `MEMORY_SENSITIVE_KEYWORDS` | `contraseña,contrasena,password,clave,pin,token,codigo de verificacion,cvv,tarjeta,cuenta bancaria,cedula,pasaporte,diagnostico,enfermedad,salud,medicamento,embarazo,discapacidad,religion,orientacion sexual,vida sexual,partido politico,afiliacion politica,sindicato,origen etnico,raza,biometric,huella` | CSV no vacía |
| `SUPPRESSION_EXECUTOR_ROLES` | `admin` | CSV no vacía ⊂ {`admin`, `asesor`} |

## Excepciones

- Nuevas en `domain.py` (subclases de `DomainError`): `SuppressionForbidden`
  (`forbidden`, 403), `SuppressionNotFound` (`not_found`, 404),
  `SuppressionNotPending` (`suppression_not_pending`, 409).
- Nueva `SummaryInvalid(Exception)` en `memory.py`, siempre capturada en
  `_summarize_session`; nunca sale a HTTP.
- Se reutilizan `ServiceUnavailable`, `AuthorizationDenied`, `CaseNotFound`,
  `CaseClosed`, `AdvisorForbidden`, `UpstreamError`.

## Dependencias

Ninguna nueva.

## Referencias de código

No se copia código de terceros; prompt, filtro y esquema son propios. T0
revisa `referencias/` solo por si hubiera algo MIT/Apache 2.0 aplicable (se
confirma archivo, commit y licencia antes de copiar); si no, se anota.

## Alternativas descartadas

- **Memoria por chat/contacto**: contradice `docs/especificacion.md` ("el
  historial y la memoria pertenecen al cliente, no al chat") y rompería la
  continuidad entre canales. Se usa `profile_id` de la sesión.
- **Añadir el resumen al `HandoverRequest` o `ClientMemory` a `contracts/`**:
  cambio de contrato con handover (feature propia, `docs/architecture.md`
  §3.2). El resumen vive en el orchestrator y el panel (que ya está en el
  orchestrator) lo lee directamente.
- **Nuevo `CaseAuthorizeAction = "view"`**: cambio de contrato. "reply" ya
  expresa "puede atender este caso", que es el permiso de caso que pide el
  acceptance.
- **Columna `session_id` en `messages`**: obligaría a cambiar todas las
  llamadas a `add_message` y el esquema caliente de #27; la ventana temporal
  por sesión (única activa por contacto, #38) delimita igual sin migración de
  datos.
- **Acumular memoria (append) en lugar de reemplazar**: crecería sin límite y
  no permite olvidar temas resueltos; el resumidor recibe la memoria actual y
  devuelve la lista completa, acotada por `MEMORY_MAX_ITEMS`.
- **Confiar el filtrado de sensibles solo al prompt**: no es verificable. El
  código filtra entrada (R15) y salida (R16–R19) con reglas deterministas.
- **Memoria activa por defecto**: la justificación y plazo de la memoria
  permanente están pendientes de validación legal (`docs/proyecto.md` §12) y
  activarla añade llamadas al LLM que cambiarían las suites de #6/#24/#38.
- **Ruta HTTP de ejecución de supresión aquí**: la cola, prioridad y fecha
  límite son de #41; duplicarla obligaría a rehacerla.

## Supuestos a confirmar (defaults seguros configurables, no bloquean)

- **S1 Apagado por defecto** (`MEMORY_ENABLED=false`) hasta que el área legal
  valide justificación y plazo de la memoria permanente (`docs/proyecto.md`
  §12). Lo ya guardado sigue visible al asesor y se borra con la supresión.
- **S2 Conversación = sesión de cliente.** Sin sesión (o con
  `IDENTITY_LOGIN_REQUIRED=false`) no hay memoria ni resumen: solo existe
  memoria del cliente autenticado.
- **S3 Disparadores**: cierre de sesión (logout, inactividad, revocación,
  cierre por admin) y escalamiento (solo resumen). Las sesiones inactivas se
  cierran de forma perezosa (#38) al siguiente mensaje o login; no se añade
  un worker de cierre.
- **S4 Datos sensibles** = lista configurable de palabras + secuencias de
  dígitos + correos. Es conservador (falsos positivos descartan el elemento) y
  se complementa con la instrucción del prompt.
- **S5 Ejecución de supresión**: `execute_suppression` con rol `admin` por
  defecto (`SUPPRESSION_EXECUTOR_ROLES`); el rol "responsable de datos", la
  cola, la notificación al cliente y la UI son #41.
- **S6 Alcance del borrado**: memoria, todos los resúmenes y los mensajes de
  las ventanas de todas las sesiones del cliente. Los mensajes previos al
  login del chat, los eventos y el contacto no se atribuyen a un cliente y
  siguen la retención de #27 (o el borrado de contacto de #41).
- **S7 Resúmenes son historial**: se purgan por retención (#27) con
  `updated_at < cutoff`; la memoria permanente no.
- **S8 Contexto a la IA**: memoria y últimos mensajes de la sesión solo en el
  prompt RAG, como contexto no citable; el router y el SQL no los reciben.
