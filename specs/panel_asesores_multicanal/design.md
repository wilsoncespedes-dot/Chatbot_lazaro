# #41 panel_asesores_multicanal — Design

El panel sigue en el **orchestrator**, renderizado en servidor y sin JS (como
#29/#33/#40). Handover solo gana la ruta de transferencia; `contracts` gana dos
modelos aditivos. No hay servicios, carpetas de primer nivel ni dependencias
nuevas.

## Archivos

| Archivo | Cambio |
|---|---|
| `contracts/lazaro_contracts/cases.py`, `__init__.py` | `CaseTransferRequest`, `CaseTransferResponse` (R26). |
| `contracts/examples/case_transfer_request.json`, `case_transfer_response.json` | Ejemplos nuevos (R26). |
| `contracts/tests/test_examples.py` | Mapear los dos ejemplos en `EXAMPLES`. |
| `contracts/CONTRATOS.md` | Sección `### POST /cases/{id}/transfer` (200/401/403/404/409/422) (R26). |
| `services/handover/handover/domain.py` | `DenialAction` añade `"transfer"`; `TransferTargetInvalid` (422); `transfer_case` (R27–R31). |
| `services/handover/handover/adapters/repository.py` | `transfer_if_assigned_to` en Protocol, Fake y Postgres. |
| `services/handover/handover/main.py` | `POST /cases/{case_id}/transfer` (R27, R74). |
| `services/handover/tests/test_transfer.py` | Nuevo (R27–R31, R74). |
| `services/handover/tests/test_security.py` | Añadir la ruta a las tablas de 401/422 existentes (R74). |
| `services/orchestrator/orchestrator/panel.py` | **Nuevo**, puro: `channel_window`, `case_wait`, `business_deadline`, `business_days_left`, `suppression_priority`, `effective_presence`, `mask_external_id`, `history_visible` (R4, R5, R34, R44, R46, R63, R64). |
| `services/orchestrator/orchestrator/domain.py` | Excepciones nuevas; `ChannelRejected`; ventana en `reply_to_case`; `advisor_send_template`; `transfer_case`; `return_case`; aviso con ventana en `close_case`; `advisor_inbox`; `advisor_case_view`; `set_advisor_presence`; `touch_advisor_presence`; `suppression_queue`; `execute_suppression_from_panel`; `record_panel_audit`. |
| `services/orchestrator/orchestrator/adapters/gateway.py` | `ChannelRejected` en `_post` para 422 (R21). |
| `services/orchestrator/orchestrator/adapters/handover.py` | `transfer` en Protocol, Http y Fake. |
| `services/orchestrator/orchestrator/adapters/repository.py` | Tablas `panel_audit`, `advisor_presence`; columnas nuevas en `suppression_requests`; métodos nuevos; `get_case_contact` Postgres completo (R13). |
| `services/orchestrator/orchestrator/config.py` | Variables de R71 con validación (R72). |
| `services/orchestrator/orchestrator/advisor_routes.py` | Rutas nuevas y filtros; `touch` de presencia; auditoría. |
| `services/orchestrator/orchestrator/advisor_panel.py` | Bandeja ampliada, vista de caso, presencia, cola de supresión (renderer compartido). |
| `services/orchestrator/orchestrator/admin_routes.py`, `admin.py` | `GET /admin/supresiones`, `POST /admin/supresiones/{id}/execute`; enlace "Supresiones" en la navegación. |
| `services/orchestrator/tests/test_panel_pure.py` | Nuevo: funciones puras. |
| `services/orchestrator/tests/test_panel_inbox.py` | Nuevo: bandeja en ambos canales, filtros, roles. |
| `services/orchestrator/tests/test_panel_reply.py` | Nuevo: texto/plantilla/ventana, ambos canales, comando Telegram. |
| `services/orchestrator/tests/test_panel_actions.py` | Nuevo: transferir, resolver, devolver, presencia. |
| `services/orchestrator/tests/test_panel_case_view.py` | Nuevo: vista, aislamiento de historial, datos permitidos, escape. |
| `services/orchestrator/tests/test_panel_audit.py` | Nuevo: auditoría de lecturas, acciones, errores y contenido. |
| `services/orchestrator/tests/test_panel_suppression.py` | Nuevo: cola, prioridad, ejecución, aviso, permisos. |
| `services/orchestrator/tests/test_config.py` | Variables nuevas; rutas nuevas en el test de superficie `APIRoute`. |
| `services/orchestrator/tests/test_repository_schema.py` | Tablas, columnas e índices nuevos idempotentes. |
| `.env.example`, `render.yaml` | Variables de R71 con sus defaults. |
| `docs/architecture.md` | Una línea en §1 bajo el orchestrator: panel de asesores multicanal y cola de supresión en `advisor_routes.py`/`panel.py`. |

## Contratos (aditivo)

```python
class CaseTransferRequest(ContractModel):
    advisor_id: Identifier          # asesor que transfiere (dueño actual)
    target_advisor_id: Identifier   # asesor registrado que recibe

class CaseTransferResponse(ContractModel):
    status: Literal["assigned"]
    case_id: Identifier
    advisor_id: Identifier          # nuevo asignado
```

`CaseListAction`, `CaseAuthorizeAction` y el resto no cambian. El panel
decide ofrecer "Transferir" cuando `status == "assigned"` (los casos `assigned`
que lista handover a un asesor son los suyos, más huérfanos solo con `close`;
para huérfanos no se ofrece transferir porque `actions` no contiene `reply`).

## Handover

```python
class TransferTargetInvalid(DomainError):  code = "validation_error"; status_code = 422

def transfer_case(case_id: str, req: CaseTransferRequest,
                  settings: Settings, adapters: Adapters) -> CaseTransferResponse
```

Orden: `advisor_id` no registrado → `_deny(..., "transfer")` (403, R28) →
`get_case` `None` → 404 → `closed` → 409 (R30) → `status != "assigned"` o
`advisor_id != case.advisor_id` → `_deny` (R28) → destino no registrado o igual
→ `TransferTargetInvalid` (R29) → `repo.transfer_if_assigned_to(case_id,
advisor_id, target, now)`; `False` → relee: `assigned` a `target` → 200; si no
→ `_deny` (R31). Postgres: `UPDATE cases SET advisor_id = %s, assigned_at = %s
WHERE case_id = %s AND status = 'assigned' AND advisor_id = %s`. No se envía
aviso Telegram al destino (lo ve en su bandeja; S6).

## Orchestrator

### `panel.py` (puro, sin IO)

```python
WindowState = Literal["open", "closed", "not_applicable"]
def channel_window(channel: str, last_user_at: datetime | None,
                   now: datetime, hours: int) -> WindowState
    # telegram → not_applicable; whatsapp → open si last_user_at y now-last < hours
def case_wait(link_created_at: datetime, last_user_at: datetime | None,
              last_advisor_at: datetime | None, now: datetime) -> timedelta | None
def business_deadline(created_at: datetime, business_days: int) -> datetime
def business_days_left(now: datetime, deadline: datetime) -> int   # hábiles completos, ≤0 si vencida
def suppression_priority(now, deadline, due_soon_days) -> Literal["vencida", "urgente", "alta"]
def effective_presence(status: str | None, last_seen_at: datetime | None,
                       now: datetime, ttl_minutes: int) -> Literal["available", "away"]
def mask_external_id(value: str) -> str          # "…" + value[-4:]; "" → "—"
def history_visible(at: datetime, foreign_windows: Sequence[tuple[datetime, datetime, datetime]]) -> bool
```

`last_user_at` / `last_advisor_at` son los últimos mensajes con `at >=
link_created_at`. `business_deadline` avanza día a día y cuenta solo
lunes–viernes (`weekday() < 5`); no hay calendario de festivos (S4).

### Excepciones nuevas (`domain.py`, subclases de `DomainError`)

- `ChannelWindowClosed` — `channel_window_closed`, 409 (R16, R21).
- `PanelValidationError` — `validation_error`, 422 (R15, R19, R20, R33, R57, R67, R8).
- `AdvisorUnavailable` — `advisor_unavailable`, 409 (R34).
- `ChannelRejected(ServiceUnavailable)` — interna; la lanza
  `HttpGatewayClient._post` con respuesta 422. Al heredar de
  `ServiceUnavailable`, todos los `except ServiceUnavailable` actuales siguen
  funcionando (`_send` la registra y devuelve `False`).
- Se reutilizan `AdvisorForbidden`, `CaseClosed`, `CaseNotFound`,
  `UpstreamError`, `SuppressionForbidden/NotFound/NotPending`.

`advisor_panel.ERROR_MESSAGES` añade `channel_window_closed`,
`advisor_unavailable`, `suppression_not_pending`.

### Respuestas

`reply_to_case` (usado por panel y `/responder`): tras `authorize` (R23) y
`get_case_contact`, si `contact.channel == "whatsapp"` y
`channel_window(...) != "open"` → `ChannelWindowClosed` (R16). El envío captura
`ChannelRejected` → `ChannelWindowClosed` (R21) antes del `ServiceUnavailable`
genérico. `_command_reply` captura `ChannelWindowClosed` →
`advisor_command_failed_reply` (R22).

```python
def advisor_send_template(case_id: str, advisor_id: str, template: str,
                          settings, adapters) -> None
```

`template ∉ settings.advisor_whatsapp_template_list` → `PanelValidationError`
sin llamar a nada (R19) → `authorize(reply)` → contacto → canal Telegram o
ventana abierta → `PanelValidationError` (R20) →
`gateway.send_channel_blocks("whatsapp", contact.external_chat_id,
[TemplateBlock(type="template", name=template)])` (R17) → `add_message(...,
"advisor", f"[plantilla:{template}]")`, evento `advisor_reply`,
`ESCALATED`, `handover.assign` (R18, igual que `reply_to_case`).

`POST /asesor/reply` acepta `case_id` + exactamente uno de `text` / `template`
(R15); no vacío cuenta como presente.

### Transferir, resolver, devolver

```python
def transfer_case(case_id: str, actor: Profile, target_profile_id: str,
                  settings, adapters) -> None        # R32–R35
def return_case(case_id: str, advisor_id: str, settings, adapters) -> None  # R37–R39
```

`transfer_case`: valida destino (R33) → `effective_presence` del destino (R34)
→ `handover.transfer(...)`; `AuthorizationDenied("forbidden"|"not_found"|
"case_closed")` → `_raise_authorization_error` (R54);
`AuthorizationDenied("validation_error")` → `PanelValidationError`;
`ServiceUnavailable` → `UpstreamError` → evento `advisor_transfer` (R35).

`HttpHandoverClient.transfer` usa el patrón de `try_assign` con
`_TRANSFER_DENIAL_CODES = {403: "forbidden", 404: "not_found", 409:
"case_closed", 422: "validation_error"}`; `FakeHandoverClient` gana
`transferred: list[tuple[str, str, str]]` y `transfer_error`, `fail_transfer`.

`close_case` y `return_case` comparten `_close_with_notice(case_id,
advisor_id, notice, event, settings, adapters)`: `authorize(close)` → `close`
→ contacto → si WhatsApp y ventana no abierta, evento `notice_skipped`
`window_closed` (R39); si no, `_send(contact, notice)` → `apply_conversation_event`
(`ADVISOR_RESOLVED` o `ADVISOR_RETURNED`). `return_case` añade el evento
`advisor_returned` (R38). `/cerrar` sigue llamando `close_case` (R73).

### Bandeja y vista

```python
@dataclass(frozen=True)
class InboxRow:
    case_id: str; status: str; created_at: datetime; actions: tuple[str, ...]
    channel: str; conversation_state: str | None; assignment: Literal["mine", "unassigned"]
    wait: timedelta | None; window: WindowState | None; client_name: str | None

def advisor_inbox(advisor_id: str, channel: str | None, assignment: str | None,
                  settings, adapters) -> list[InboxRow]          # R1–R10
```

Validar filtros antes de `list_cases` (R8). Para cada item: `get_case_link`
(contacto, `profile_id`, `created_at`); `None` → fila `desconocido` (R10).
`case_activity(contact_id, since)` da `last_user_at`, `last_advisor_at`.
Orden por `created_at` (R9).

```python
@dataclass(frozen=True)
class HistoryItem: role: str; text: str; at: datetime
@dataclass(frozen=True)
class ClientPanelData:
    channel: str; masked_external_id: str; conversation_state: str | None
    consent_result: str | None; consent_version: str | None; consent_at: datetime | None
    username: str | None; credential_status: str | None; days_remaining: int | None
    has_active_session: bool | None
@dataclass(frozen=True)
class CaseView:
    case_id: str; status_actions: tuple[str, ...]; history: tuple[HistoryItem, ...]
    client: ClientPanelData; memory: ClientMemoryView; window: WindowState
    templates: tuple[str, ...]; transfer_targets: tuple[tuple[str, str, str], ...]  # (profile_id, username, presence)

def advisor_case_view(case_id: str, actor: Profile, settings, adapters) -> CaseView  # R40–R49
```

`advisor_case_view` llama primero `advisor_client_memory` (que ya autoriza con
`reply`, registra el evento `memory_viewed` del contacto y devuelve
`authenticated=False` sin perfil; R40, R41, R45, R47); luego historial con
`repo.case_messages(contact_id, since, limit)` filtrado por `history_visible`
contra `repo.foreign_session_windows(contact_id, profile_id | None,
idle_minutes, now)` (R42, R44). Datos de cliente: `last_privacy_decision`
(nuevo) y, con perfil, `_client_status` (si `ClientNotFound`, campos `None`)
(R46, R47). Acciones de la vista: se toma el item del caso en
`handover.list_cases(advisor_id)`; `status_actions` = sus `actions` más
`transfer` y `return` si `status == "assigned"` y `reply ∈ actions`, más
`return` si `close ∈ actions`. Si el caso no aparece o handover falla en esa
llamada, `status_actions = ("reply", "close", "return")` (las acciones se
vuelven a autorizar al ejecutarse, así que esto no amplía permisos).

Plantillas (`advisor_panel.render_advisor_case`): con `window == "closed"` →
`<select name="template">` (R24); si no → `<textarea name="text">` (R25). Todo
texto pasa por `_esc` (R48). `render_advisor_cases` añade columnas y enlace
"Abrir" a `/asesor/cases/{id}` y, si `refresh > 0`, el `<meta refresh>` en
`<head>` (R12; `_page` gana `refresh: int = 0`).

### Presencia

Tabla `advisor_presence(profile_id TEXT PRIMARY KEY, status TEXT NOT NULL,
updated_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL)`.
Repositorio: `set_advisor_presence(profile_id, status, now)` (upsert, también
`last_seen_at`), `touch_advisor_presence(profile_id, now)` (upsert con
`status = 'away'` solo si no existe fila; si existe, solo `last_seen_at`),
`get_advisor_presence(profile_ids) -> dict[str, tuple[str, datetime]]`.
`_require_session` del panel de asesores llama a `touch` (R58). `logout`
llama a `set(..., "away")` antes de borrar la sesión (R59).

### Auditoría

Tabla `panel_audit(id BIGSERIAL PRIMARY KEY, actor_profile_id TEXT NOT NULL,
actor_role TEXT NOT NULL, action TEXT NOT NULL, case_id TEXT, request_id TEXT,
target TEXT, result TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)` e índice
`panel_audit_at ON panel_audit (at)`.

```python
def record_panel_audit(actor: Profile, action: str, result: str, adapters, *,
                       case_id: str | None = None, request_id: str | None = None,
                       target: str | None = None) -> None
```

Las rutas envuelven cada lectura/acción: `ok` al terminar, `exc.code` en
`DomainError` (R50–R52). `target` solo admite `profile_id` destino o nombre de
plantilla (R53). Acciones: `inbox_viewed`, `case_viewed`, `memory_viewed`,
`suppression_queue_viewed`, `reply`, `template`, `assign`, `transfer`,
`resolve`, `return`, `presence`, `suppression_execute`. `panel_audit` no
contiene datos de cliente y la purga de #27 no la toca (S7).

### Cola de supresión

Migraciones: `ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS
result_note TEXT`, `... notification_result TEXT`; índice
`suppression_requests_status_created ON suppression_requests (status,
created_at)`. `StoredSuppressionRequest` gana ambos campos (default `None`).

Repositorio: `list_suppression_requests(executed_limit) ->
list[StoredSuppressionRequest]` (todas las `pending` + últimas `executed`),
`set_suppression_outcome(request_id, note, notification_result)`.

```python
@dataclass(frozen=True)
class SuppressionRow:
    request: StoredSuppressionRequest; client_username: str | None
    executor_username: str | None; deadline: datetime; priority: str | None

def suppression_queue(actor: Profile, settings, adapters) -> list[SuppressionRow]   # R60–R65
def execute_suppression_from_panel(request_id: str, actor: Profile, note: str,
                                   settings, adapters) -> SuppressionExecution     # R66–R70
```

`suppression_queue` y `execute_suppression_from_panel` comprueban primero
`actor.role in settings.suppression_executor_role_set` →
`SuppressionForbidden` (R61). La ejecución: nota > 500 → `PanelValidationError`
(R67) → `get_suppression_request` → contacto `repo.get_contact(contact_id)` y
ventana calculada **antes** del borrado → `execute_suppression` (#40) → aviso
con `_deliver` (texto) o `send_channel_blocks` (plantilla) **sin**
`add_message` (R68) → `set_suppression_outcome` con `text` / `template` /
`failed` / `skipped` (R69). Rutas: `/admin/supresiones` usa la sesión `admin`
de `admin_routes`; `/asesor/supresiones` la del panel de asesores; ambas usan
`advisor_panel.render_suppression_queue(rows, csrf, action_prefix)`.

### Repositorio: métodos nuevos (Protocol + Fake + Postgres)

```python
@dataclass(frozen=True)
class CaseLink: case_id: str; contact: Contact; profile_id: str | None; created_at: datetime
def get_case_link(self, case_id: str) -> CaseLink | None
def case_activity(self, contact_id: str, since: datetime) -> tuple[datetime | None, datetime | None]
def last_user_message_at(self, contact_id: str) -> datetime | None
def case_messages(self, contact_id: str, since: datetime, limit: int) -> list[tuple[str, str, datetime]]
def foreign_session_windows(self, contact_id: str, profile_id: str | None,
                            idle_minutes: int, now: datetime) -> list[tuple[datetime, datetime, datetime]]
def last_privacy_decision(self, channel: str, external_user_id: str
                          ) -> tuple[str, str, datetime | None] | None   # (result, version, occurred_at)
# presencia, auditoría y supresión: ver arriba
```

`get_case_contact` (Postgres) pasa a seleccionar `c.id, c.channel,
c.external_user_id, c.external_chat_id, c.telegram_user_id, c.chat_id` (R13).
`FakeRepository.case_links` hoy guarda solo `contact_id`; se añade
`case_link_created: dict[str, datetime]` rellenado por `link_case` sin cambiar
la forma del dict existente.

## Config (`.env.example`, sección "panel de asesores multicanal (#41)")

| Variable | Default | Rango / forma |
|---|---|---|
| `WHATSAPP_WINDOW_HOURS` | `24` | 1–24 |
| `ADVISOR_WHATSAPP_TEMPLATES` | `respuesta_asesor` | CSV no vacía, cada nombre `^[a-z0-9_]{1,64}$` |
| `ADVISOR_RETURN_REPLY` | `Te devolvemos al asistente virtual. Puedes seguir escribiendo aquí.` | no vacío, ≤ 4096 |
| `ADVISOR_HISTORY_LOOKBACK_MINUTES` | `60` | 0–1440 |
| `ADVISOR_HISTORY_MAX_MESSAGES` | `100` | 10–500 |
| `ADVISOR_PRESENCE_TTL_MINUTES` | `15` | 1–240 |
| `ADVISOR_INBOX_REFRESH_SECONDS` | `30` | 0–600 |
| `SUPPRESSION_DEADLINE_BUSINESS_DAYS` | `15` | 1–60 |
| `SUPPRESSION_DUE_SOON_BUSINESS_DAYS` | `3` | 0–30 |
| `SUPPRESSION_QUEUE_EXECUTED_LIMIT` | `20` | 0–200 |
| `SUPPRESSION_DONE_REPLY` | `Tu solicitud de supresión de datos fue atendida.` | no vacío, ≤ 4096 |
| `SUPPRESSION_RESULT_TEMPLATE` | `resultado_supresion` | `^[a-z0-9_]{1,64}$` |

## Dependencias

Ninguna nueva.

## Referencias de código

No se copia código de terceros. Chatwoot es solo modelo de experiencia
(`docs/especificacion.md`); no se revisa ni copia su código.

## Alternativas descartadas

- **Transferir como "liberar + asignar"** (sin contrato nuevo): el caso quedaría
  sin dueño y cualquier asesor podría tomarlo, que no es transferir. Se añade
  una ruta aditiva en handover con escritura condicional; las rutas existentes
  no cambian. Cambiar el contrato es parte explícita del acceptance.
- **Añadir `transfer` a `CaseListAction`**: rompe el contrato de listado; el
  panel deduce la acción del estado `assigned`.
- **Calcular la ventana en el gateway y exponerla por HTTP**: el núcleo
  (orchestrator) ya guarda la hora del último mensaje del cliente
  (`docs/especificacion.md`: "se guarda la hora del último mensaje del
  cliente"); el gateway sigue siendo la segunda barrera (R21).
- **Websockets / JS para tiempo real**: el panel es HTML sin JS (#29, CSP
  estricta). Se usa `<meta refresh>` configurable (R12); el tiempo real queda
  fuera.
- **Roles nuevos `supervisor` / `responsable_datos`**: tocarían
  `admin.ROLES`, sesiones y bootstrap (#42 administra cuentas). "Responsable de
  datos" = `SUPPRESSION_EXECUTOR_ROLES` (#40); supervisor queda pendiente.
- **Cerrar el caso de handover al ejecutar la supresión**: el ejecutor por
  defecto es `admin`, que no es asesor registrado en handover; el caso se
  muestra vinculado en la cola y lo resuelve un asesor.

## Supuestos a confirmar (defaults seguros configurables, no bloquean)

- **S1 Identidad del asesor**: sigue siendo `telegram_user_id` del perfil y
  `ADVISOR_CHAT_IDS` en handover (compatibilidad temporal decidida para la
  fase 6). Retirar `/responder`, `/cerrar` y el aviso Telegram es una feature
  posterior que el leader debe registrar; #41 no los rompe (R73).
- **S2 Plantillas**: lista por variable de entorno
  (`ADVISOR_WHATSAPP_TEMPLATES`, `SUPPRESSION_RESULT_TEMPLATE`) sin variables;
  su administración y estado de aprobación pasan al panel en #42. El gateway
  sigue validando la aprobación (R21).
- **S3 Ventana 24 h**: regla del proveedor, no tiempo de producto; por eso va en
  entorno (`WHATSAPP_WINDOW_HOURS`).
- **S4 Plazo de supresión**: 15 días hábiles (Ley 1581, art. 15) sin festivos,
  configurable; pendiente de validación legal (`docs/proyecto.md` §12). #42 lo
  moverá a `app_settings` editable.
- **S5 Historial visible**: desde 60 min antes del caso, máximo 100 mensajes,
  excluyendo ventanas de sesión de otros clientes del mismo chat.
- **S6 Transferencia sin aviso Telegram al destino**; el destino debe estar
  `available` (presencia expira a los 15 min sin actividad).
- **S7 `panel_audit`** no se purga en #41 (solo ids internos); su retención se
  decide con legal.
- **S8 Notas internas, respuestas guardadas, asignación automática por carga y
  vista de supervisor** (de `docs/especificacion.md`) no están en el acceptance
  de #41; quedan fuera.
