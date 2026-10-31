# Design — traspaso_asesor

## Precondición de contrato (leer primero)

El `acceptance` pide que `POST /cases/{id}/reply` (orquestador) marque el caso `assigned` y que
el vencimiento (handover) solo afecte a casos «sin asignar». El estado vive en handover y el
orquestador no puede leer su base (`docs/architecture.md` §3.1). Con las 8 rutas actuales
handover no se entera de la asignación, así que hace falta una ruta aditiva
`POST /cases/{id}/assign` (handover; la llama el orquestador).

Por el principio 2 («cambiar un contrato es una feature propia») **esta feature no toca
`contracts/`**. Queda condicionada a una feature previa, que el leader debe crear y completar
antes de pasar esta a `in_progress` (si no existe o no se acepta, esta feature queda `blocked`):

- `POST /cases/{id}/assign` — expone handover, llama orchestrator. Request
  `CaseAssignRequest {advisor_id: Identifier}`; `200` `CaseAssignResponse {status: "assigned",
  case_id: Identifier}`; errores `401 unauthorized`, `422 validation_error`, `404 not_found`,
  `409 case_closed`, `500 internal_error`. Incluye supuesto S11, ejemplos en
  `contracts/examples/` y tests de contrato (rechazo sin `advisor_id`).

Esta feature solo consume esos modelos desde `lazaro_contracts`.

## Archivos

### services/handover/
- `handover/config.py` — `Settings`: `service_token`, `database_url`, `telegram_gateway_url`,
  `advisor_chat_ids: str = ""` con propiedad `advisor_ids -> list[int]`,
  `handover_timeout_seconds: int = Field(300, ge=1)`, `handover_timeout_reply: str`,
  `http_timeout_seconds: float = 10`.
- `handover/domain.py` — errores, modelo `Case`, `Notification` y la lógica (con adaptadores
  inyectados, igual que `orchestrator/domain.py`).
- `handover/adapters/repository.py` — `CaseRepository` (Protocol), `FakeCaseRepository`,
  `PostgresCaseRepository` (pg8000, SQL parametrizado, conexión perezosa, `CREATE TABLE IF NOT
  EXISTS` en el primer uso).
- `handover/adapters/gateway.py` — `GatewayClient` (Protocol), `HttpGatewayClient`,
  `FakeGatewayClient` (`fail_for: set[int]` para fallar por chat).
- `handover/main.py` — `create_app(settings=None, adapters=None)`; rutas `/handover`,
  `/cases/{id}/assign`, `/cases/{id}/close`, `/cases/check-timeouts`; el resto (token, handlers,
  `/health`) ya existe.
- `requirements.txt` — añadir `httpx>=0.27,<1` y `pg8000>=1.31,<2` (las mismas versiones que
  el orquestador).
- Tests: `tests/fakes.py`, `tests/test_handover.py`, `tests/test_cases.py`,
  `tests/test_timeouts.py`, `tests/test_security.py`, `tests/test_repository.py`,
  `tests/test_config.py`.

### services/orchestrator/
- `orchestrator/config.py` — `no_advisors_reply: str`.
- `orchestrator/domain.py` — `_handover` guarda el vínculo caso↔contacto y envía
  `NO_ADVISORS_REPLY` con `no_advisors`; nueva función `reply_to_case(...)` y excepciones
  `CaseNotFound(DomainError)` (404 `not_found`) y `UpstreamError(DomainError)` (502
  `upstream_error`).
- `orchestrator/adapters/repository.py` — `Repository` suma `link_case(case_id, contact_id, at)`
  y `get_case_contact(case_id) -> Contact | None`; Fake y Postgres (tabla `case_links`).
- `orchestrator/adapters/handover.py` — `HandoverClient` suma `assign(case_id, advisor_id)`
  (lanza `ServiceUnavailable` ante error o 4xx/5xx); Fake con `assigned` y `fail_assign`.
- `orchestrator/main.py` — ruta `POST /cases/{id}/reply` (síncrona, con `CaseReplyRequest` →
  `CaseReplyResponse`).
- Tests: `tests/test_case_reply.py`; actualizar los tests de la feature 4 que asumen que con
  `no_advisors` no se envía nada al cliente, y las fakes (`tests/fakes.py`).

### Raíz
- `.env.example` — `NO_ADVISORS_REPLY`, `HANDOVER_TIMEOUT_REPLY` y, bajo `# handover`,
  `HTTP_TIMEOUT_SECONDS` si hace falta (`ADVISOR_CHAT_IDS`, `HANDOVER_TIMEOUT_SECONDS` y
  `HANDOVER_URL` ya existen).
- `docker-compose.yml` — el implementer comprueba que el servicio `handover` recibe
  `DATABASE_URL`, `TELEGRAM_GATEWAY_URL`, `ADVISOR_CHAT_IDS`, `HANDOVER_TIMEOUT_*` y que
  `orchestrator` recibe `NO_ADVISORS_REPLY`; solo si falta alguna, la añade.

## Firmas (handover)

```python
# domain.py
CaseStatus = Literal["open", "assigned", "timed_out", "closed"]

class CaseNotFound(DomainError):  code = "not_found";  status_code = 404
class CaseClosed(DomainError):    code = "case_closed"; status_code = 409

class Case(BaseModel):
    case_id: str; contact_id: str; chat_id: int; reason: str
    status: CaseStatus; advisor_id: str | None
    last_messages: list[LastMessage]
    created_at: datetime; assigned_at: datetime | None
    closed_at: datetime | None; closed_by: str | None

@dataclass
class Adapters:
    repository: CaseRepository
    gateway: GatewayClient
    clock: Callable[[], datetime]

def build_advisor_notice(case_id: str, reason: str, last_messages: list[LastMessage]) -> str
def open_case(req: HandoverRequest, settings: Settings, adapters: Adapters) -> HandoverResponse
def assign_case(case_id: str, advisor_id: str, adapters: Adapters) -> CaseAssignResponse
def close_case(case_id: str, advisor_id: str, adapters: Adapters) -> CaseCloseResponse
def check_timeouts(settings: Settings, adapters: Adapters) -> CheckTimeoutsResponse

# adapters/repository.py
class CaseRepository(Protocol):
    def find_active_case(self, contact_id: str) -> Case | None: ...      # open o assigned
    def create_case(self, case: Case) -> None: ...
    def update_case(self, case: Case) -> None: ...
    def get_case(self, case_id: str) -> Case | None: ...
    def list_open_cases(self) -> list[Case]: ...                         # status == open
    def add_notification(self, case_id: str, advisor_id: str, reason: str,
                         at: datetime, delivered: bool) -> None: ...

# adapters/gateway.py
class GatewayClient(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...                 # ServiceUnavailable si falla
```

## Flujos

`open_case` (R1-R10): buscar `find_active_case(contact_id)`; si existe, actualizar
`last_messages` (R2); si no, crear con `case_id` de la petición y `created_at = clock()` (R1).
Texto del aviso con `build_advisor_notice` (R4, R41: `Caso <id> | Motivo: <etiqueta>`, luego una línea
`[rol] texto` por mensaje, cada texto recortado a 300 caracteres y el total a 4096). Para cada
`advisor_id` de `settings.advisor_ids`: `gateway.send`; éxito → `add_notification(..., True)`;
`ServiceUnavailable` → `add_notification(..., False)` y se sigue (R5, R6). `notified` si hubo
algún éxito; si no hay asesores o ninguno recibió el aviso → `no_advisors` y, si el caso está
`open`, pasa a `timed_out` (R10). El caso `assigned` reutilizado no cambia de estado.

`assign_case` (R11-R14): `open`/`timed_out` → `assigned` con `advisor_id` y `assigned_at`;
`assigned` → sin cambios; `closed` → `CaseClosed`; inexistente → `CaseNotFound`.

`close_case` (R14-R16): cualquier estado no cerrado → `closed`; ya cerrado → sin cambios.

`check_timeouts` (R17-R22): `now = adapters.clock()`; para cada caso de `list_open_cases()` con
`(now - created_at).total_seconds() >= settings.handover_timeout_seconds`: `gateway.send(chat_id,
handover_timeout_reply)`; si funciona → `timed_out` y se añade a la lista; si falla → se deja
`open`, se registra el error (solo `case_id`, nunca el texto) y se continúa. Nunca se usa
`datetime.now()` fuera de `main.py`/`build_default_adapters`.

Registro (principio 9): handover guarda las notificaciones (caso, asesor, motivo, fecha,
entregada) y el estado de cada caso con sus fechas; los logs llevan `case_id` y códigos, no
texto de clientes.

## Flujos (orchestrator)

`_handover` tras `adapters.handover.request(...)`: `repo.link_case(response.case_id, contact.id,
clock())` (R28); con `no_advisors`: evento `handover_failed`/`no_advisors` (R29, ya existe) y
`_send(contact, settings.no_advisors_reply, adapters)` (R30). Con `ServiceUnavailable` de
handover no cambia el comportamiento actual (fuera de alcance, ver supuestos).

`reply_to_case(case_id, req, settings, adapters)` (R31-R36): `contact = repo.get_case_contact(
case_id)` → `CaseNotFound` si `None`; `gateway.send` → en `ServiceUnavailable` lanza
`UpstreamError` sin escribir nada; si ok: `add_message(contact.id, "advisor", text, clock())`,
`add_event(contact.id, "advisor_reply", f"advisor:{advisor_id}", clock())`, luego
`handover.assign(case_id, advisor_id)`; si falla, `add_event(contact.id, "assign_failed",
case_id, clock())` y se devuelve igual `CaseReplyResponse(sent=True)`.

Tablas nuevas (se crean con `CREATE TABLE IF NOT EXISTS`, como el resto):

```sql
-- handover
handover_cases (case_id TEXT PK, contact_id TEXT, chat_id BIGINT, reason TEXT, status TEXT,
  advisor_id TEXT NULL, last_messages JSONB, created_at TIMESTAMPTZ, assigned_at TIMESTAMPTZ NULL,
  closed_at TIMESTAMPTZ NULL, closed_by TEXT NULL)
handover_notifications (id BIGSERIAL PK, case_id TEXT, advisor_id TEXT, reason TEXT,
  at TIMESTAMPTZ, delivered BOOLEAN)
-- orchestrator
case_links (case_id TEXT PK, contact_id TEXT, created_at TIMESTAMPTZ)
```

`last_messages` se serializa con `json.dumps` (parámetro, no SQL interpolado).

## Excepciones

Se reutilizan `DomainError` (handover y orchestrator) y `ServiceUnavailable` (orchestrator).
Nuevas: `CaseNotFound` y `CaseClosed` en handover; `CaseNotFound` y `UpstreamError` en
orchestrator; en handover también `ServiceUnavailable` (interna, la lanza el cliente del
gateway y nunca llega al exterior). Los handlers de `DomainError` existentes ya producen
`{error, message}`.

## Alternativas descartadas

- **Sin ruta `assign`: el orquestador lleva el estado del caso y handover vence por tiempo
  puro.** Descartada: handover avisaría «sin asesores» a clientes que ya están atendidos,
  incumpliendo «sigue sin asignar» del acceptance.
- **Handover leyendo el historial del orquestador (o una base compartida) para saber si hay
  respuesta del asesor.** Descartada: viola el principio 1 (un servicio no lee la base de otro).
- **Cambiar `HandoverResponse` para devolver el estado del caso o añadir `assigned_to` a
  `/cases/{id}/reply`.** Descartada: modifica rutas existentes; una ruta nueva es aditiva y no
  rompe a nadie.
- **Reenviar al asesor con `parse_mode` Markdown.** Descartada: texto de clientes con
  Markdown/HTML sería inyección de formato; el gateway envía texto plano.

## Dependencias nuevas

En `services/handover/requirements.txt`: `httpx>=0.27,<1` (BSD-3) y `pg8000>=1.31,<2`
(BSD-3). Ambas ya están en el orquestador y en el `.venv`; el humano debe confirmar que el
`.venv` las tiene antes de implementar. Ninguna otra.

## Supuestos a confirmar

| Supuesto | Valor por defecto configurable |
|---|---|
| Espera antes de avisar «sin asesores» (duda abierta §12) | `HANDOVER_TIMEOUT_SECONDS=300` |
| Los asesores se identifican por su chat_id de Telegram | `ADVISOR_CHAT_IDS` (coma-separada, vacío = sin asesores) |
| Texto al cliente cuando no hay asesores en el momento | `NO_ADVISORS_REPLY` = «En este momento no hay asesores disponibles. Tu consulta quedó registrada y te escribiremos en cuanto haya alguien.» |
| Texto al cliente cuando vence la espera | `HANDOVER_TIMEOUT_REPLY` = «Todavía no hay un asesor disponible. Tu consulta sigue registrada y te responderemos en cuanto sea posible.» |
| Ruta `POST /cases/{id}/assign` (S11) y `409 case_closed` | — (la define la feature previa de contrato) |
| CONFIRMADO por el humano (2026-10-30): un caso con `no_advisors` pasa a `timed_out` de inmediato (R10), porque el cliente ya recibió `NO_ADVISORS_REPLY` y así `check-timeouts` no repite el aviso; un nuevo `/handover` del mismo contacto crea caso nuevo y vuelve a avisar. Alternativa descartada: dejarlo `open` y aceptar el segundo aviso | — |
| CONFIRMADO por el humano (2026-10-30): un caso `timed_out` pasa a `assigned` si un asesor responde después (R11); el acceptance 4 no excluye ese estado y `reply_to_case` ya ha enviado el texto al cliente antes de llamar a `assign`, así que rechazarlo dejaría el caso «sin asignar» con el cliente ya atendido | — |
| Reutilizar un caso abierto vuelve a avisar a todos los asesores | — |
| ACEPTADO por el humano (2026-10-31): al reutilizar un caso, `Case.reason` conserva el motivo original y el aviso y cada notificación usan el motivo de la petición nueva. Condición del humano: que ambas solicitudes queden registradas y no se pierda el historial. Se cumple en el orquestador: cada `/handover` deja un evento `handover` con su motivo y fecha (`test_messages.py::test_handover_event_saved`) y el historial de mensajes nunca se reescribe. Dentro de handover, `last_messages` se reemplaza por la instantánea más reciente y, sin asesores configurados, no se crea ninguna notificación que guarde el motivo nuevo. Si se quiere un registro por petición dentro de handover, será una feature posterior | — |
| `advisor_id` no se valida contra `ADVISOR_CHAT_IDS` (la ruta ya exige token de servicio) | — |
| Si `ServiceUnavailable` en `POST /handover` desde el orquestador, no se envía mensaje al cliente (comportamiento actual de la feature 4) | — |
| Mientras el caso está `assigned`, los mensajes del cliente siguen pasando por RAG; no se reenvían al asesor | — (fuera de alcance; propuesta de feature posterior) |
| PENDIENTE (decisión del humano, 2026-10-31: no se implementa todavía): nadie llama a `check-timeouts` de forma periódica (falta el worker o cron). Impacto: un caso `open` cuyos asesores recibieron el aviso pero no responden nunca vence; el cliente no recibe `HANDOVER_TIMEOUT_REPLY` y el caso queda `open` indefinidamente (y se reutiliza en cada `/handover` posterior del contacto). No afecta al camino sin asesores: el cliente recibe `NO_ADVISORS_REPLY` al momento (R10, R30). Mitigación manual mientras tanto: llamar a `POST /cases/check-timeouts` con `X-Service-Token` | — |
| Los asesores usan `POST /cases/{id}/reply` con herramienta interna y token hasta que exista el panel | — |
