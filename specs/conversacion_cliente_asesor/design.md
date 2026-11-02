# Design — conversacion_cliente_asesor (feature #16)

> Cómo se construye lo pedido en `requirements.md`. Fuentes: acceptance de la #16 (criterios
> «Decidido por el humano (2026-10-31)»), `progress/propuesta_etapa2.md` §4 y §6, los specs de la
> #15 (`specs/contrato_conversacion_caso/`, S13), la #13 (`specs/contrato_autorizacion_asesores/`,
> S12), la #14 (`specs/autorizacion_asesores/`, D1-D9), la #10
> (`specs/validacion_config_asesores/`) y la #7 (`specs/traspaso_asesor/`). Apoyado en
> `docs/architecture.md` §3 (principios 1, 3, 4, 5, 9) y §4, y en `docs/conventions.md`.

## 1. Alcance y dependencias de orden

- Toca `services/orchestrator/`, `services/handover/` y `.env.example`. **No** toca
  `contracts/`, `services/telegram_gateway/`, `eval/`, `scripts/`, `docker-compose.yml` ni
  `.github/`. Sin dependencias nuevas.
- **Requiere implementadas (`done`; todas lo están a 2026-11-01)**:
  - #15: `lazaro_contracts` exporta `CaseClientMessageRequest` y `CaseClientMessageResponse`.
  - #13: exporta `CaseAuthorizeRequest`, `CaseAuthorizeResponse`, `CaseAuthorizeAction`;
    `CONTRATOS.md` publica C5 (`reply` sobre `closed` → `409 case_closed`) y la línea `Llama` de
    `authorize` con el comando `/cerrar`.
  - #14: existen en el orquestador `HandoverClient.authorize`, `AuthorizationDenied`,
    `AdvisorForbidden` (`403`), `CaseClosed` (`409 case_closed`), `AUTHORIZE_DENIAL_CODES` y
    `reply_to_case` con autorización previa; y en handover las reglas de
    `authorize`/`close`/`assign`, la asignación y el cierre condicionales y `is_orphan_case`.
  - #17: S12 con el cierre de casos huérfanos.
  - #18: `threading.Lock` en `PostgresRepository` del orquestador.
  Si falta alguna, el implementer para con `blocked` (T0).
- **Conviene la #10 antes**: con ella `ADVISOR_CHAT_IDS` llega validada. Esta feature no lee esa
  lista en ningún servicio: el orquestador nunca (R46) y handover solo a través de las reglas de
  la #14.
- `POST /messages` no cambia (S13, R33 de la #15). Los comandos llegan por esa ruta con el
  `telegram_user_id` que el gateway extrae de `message.from.id` de un update ya validado con
  `TELEGRAM_WEBHOOK_SECRET` (#5).

### Qué reutilizo de la #14 (sin modificarlo)

| Pieza de la #14 | Uso en esta feature |
|---|---|
| `reply_to_case(case_id, CaseReplyRequest, settings, adapters)` | `/responder` la llama tal cual (R12): autoriza primero, falla cerrado, envía, guarda el mensaje `advisor` y el evento `advisor_reply`, y asigna. «Mismos efectos que `POST /cases/{id}/reply`» por construcción |
| Excepciones que lanza hoy `reply_to_case` (código actual, `services/orchestrator/orchestrator/domain.py`): `AdvisorForbidden` (`authorize` → `403`), `CaseClosed` (`authorize` → `409 case_closed`), `CaseNotFound` (`authorize` → `404` o caso sin vínculo local), `UpstreamError` (`authorize` caído o fallo de `POST /send`) | se capturan en el manejador de comandos y se traducen a textos fijos (R14, R60, R15) |
| D5 de la #14 (C5 de la #13): `409 case_closed` → `CaseClosed`, **sin** `advisor_forbidden` | base de R60-R62: un caso cerrado no es una denegación |
| `_record_forbidden` (evento `case:<id> advisor:<id> code:forbidden` en el contacto del caso, o solo log sin vínculo; R29/R30 de la #14) | solo se ejecuta dentro de `reply_to_case` con `403`; esta feature añade además el evento del remitente (R24, D6) |
| `HandoverClient.authorize`, `AuthorizationDenied`, `ServiceUnavailable` | `/cerrar` autoriza con `action="close"` (R16) |
| `FakeHandoverClient(authorize_error=..., fail_authorize=...)`, `.authorized` | tests de comandos |
| Reglas de handover (D1: no registrado → `403` antes que `404`) | un no asesor nunca sabe si un caso existe: siempre recibe el texto de no autorizado |

No se cambia ninguna firma, comportamiento ni test de la #14. La única edición sobre código de
la #14 es **aditiva** en `FakeHandoverClient.authorize` (parámetro opcional
`authorized_advisors`, §3.6), con valor por defecto que conserva su comportamiento.

### Coordinación con la #11 y la #12

- Esta feature **no toca el repositorio de handover** (`adapters/repository.py`): la ruta nueva
  solo usa `get_case`, ya existente. No hay conflicto con `handover_requests` (#11),
  `handover_denials` (#14) ni con las transiciones condicionales de la #12.
- `forward_client_message` no escribe casos (R53). Si el caso deja de estar `assigned` entre la
  lectura y el envío, el mensaje se entrega al asesor que lo tenía.
- **Carreras (D1 de la #12): resueltas antes de esta feature.** `/responder` y `/cerrar` llevan
  `assign` y `close` a Telegram, donde todos los asesores reciben el aviso a la vez. La #14 ya
  implementa, por decisión del humano (D10 de la #14), la asignación condicional (el `assign`
  que pierde la carrera recibe `403` sin escribir) y el cierre condicional (no puede cerrar un
  caso que ya quedó asignado a otro asesor: `403` + denegación). Riesgo residual aceptado por
  el humano en la D10 de la #14: dos `/responder` simultáneos sobre un caso sin asignar pasan
  los dos el `authorize` y los dos llegan al cliente; el segundo queda como `assign_failed`. Del
  mismo modo, un `/responder` autorizado justo antes de un `/cerrar` puede llegar al cliente
  después de `CASE_CLOSED_REPLY` (su `assign` sobre el caso cerrado falla y queda
  `assign_failed`). Esta feature no cambia `assign_case`, `close_case` ni `reply_to_case`.
- **Conexión pg8000 compartida (D2 de la #12): resuelta antes de esta feature.** Handover recibe
  una llamada `client-message` (→ `get_case`) por cada mensaje de cualquier contacto con un caso
  vinculado, concurrente con `timeouts_worker`, `authorize`, `assign` y `close`; el orquestador
  suma `get_contact_last_case` por mensaje. Ambas conexiones están ya serializadas con un
  `threading.Lock` (`PostgresCaseRepository._run`, #14; `PostgresRepository._run`, #18).
  `get_contact_last_case` usa `_run` como el resto de métodos, así que hereda el candado. Queda
  el coste de latencia (las llamadas se serializan), aceptable con el volumen esperado (C3).
- En el orquestador, el repositorio gana un método de lectura (`get_contact_last_case`) sin
  tabla nueva: no cambia `_SCHEMA` ni el conteo de `CREATE TABLE` de ningún test.

## 2. Archivos

| Acción | Ruta | Cambio |
|---|---|---|
| modificar | `services/orchestrator/orchestrator/domain.py` | `AdvisorCommand`, `MalformedCommand`, `parse_advisor_command`, `ForwardRejected`, `FORWARD_REJECTION_CODES`; `_handle_advisor_command`, `_command_reply`, `_command_close`, `_deny_command`, `_notify_sender`, `_forward_to_advisor`; `process_message` con los dos pasos nuevos |
| modificar | `services/orchestrator/orchestrator/adapters/handover.py` | `forward_client_message` y `close` en `HandoverClient`, `HttpHandoverClient` y `FakeHandoverClient`; `authorized_advisors` en el fake |
| modificar | `services/orchestrator/orchestrator/adapters/repository.py` | `get_contact_last_case` en `Repository`, `FakeRepository` y `PostgresRepository` |
| modificar | `services/orchestrator/orchestrator/adapters/gateway.py` | `FakeGatewayClient` gana `fail_for: set[int] \| None = None` (aditivo; §3.7) |
| modificar | `services/orchestrator/orchestrator/config.py` | ocho textos fijos nuevos (§6) |
| modificar | `services/handover/handover/domain.py` | `UpstreamError`, `build_client_forward`, `forward_client_message` |
| modificar | `services/handover/handover/main.py` | ruta `POST /cases/{case_id}/client-message` |
| modificar | `.env.example` | ocho variables en el bloque `# orchestrator` (§6) |
| crear | `services/orchestrator/tests/test_advisor_commands.py` | R1-R26, R60-R62 |
| crear | `services/orchestrator/tests/test_client_forward.py` | R27-R46 |
| modificar | `services/orchestrator/tests/test_security.py` | tres pruebas de seguridad obligatorias (tests nuevos) |
| crear | `services/handover/tests/test_client_message.py` | R47-R54, R57, R59 |
| modificar | `services/handover/tests/test_security.py` | entradas nuevas en `ROUTES`/`INVALID_BODIES` y una prueba de seguridad nueva |

`main.py` del orquestador no cambia: no hay rutas nuevas en el orquestador
(`test_only_health_and_messages_routes_exposed` sigue igual).

## 3. Orchestrator

### 3.1 Detección de comandos (pura, `domain.py`)

```python
ADVISOR_COMMAND_PREFIXES = ("/responder", "/cerrar")


@dataclass(frozen=True)
class AdvisorCommand:
    action: CaseAuthorizeAction          # "reply" | "close" (de lazaro_contracts, #13)
    case_id: str
    text: str | None                     # solo en "reply"


@dataclass(frozen=True)
class MalformedCommand:
    """Intento de comando que no cumple la forma `/responder <case_id> <texto>` ni `/cerrar <case_id>`."""


def parse_advisor_command(text: str) -> AdvisorCommand | MalformedCommand | None:
    """Pura: sin IO, sin reloj, sin configuración (R5)."""
```

Algoritmo (R1-R4):

1. `stripped = text.strip()`; si `stripped.split()` está vacío → `None`.
2. `first = stripped.split(maxsplit=1)[0]`. Si `not first.casefold().startswith(ADVISOR_COMMAND_PREFIXES)` → `None` (R1).
3. `parts = stripped.split(maxsplit=2)`.
4. `first == "/responder"`, `len(parts) == 3` y `1 <= len(parts[1]) <= MAX_IDENTIFIER_LENGTH` →
   `AdvisorCommand("reply", parts[1], parts[2])` (R2). `parts[2]` conserva saltos de línea y
   espacios internos; no se normaliza nada (el texto va tal cual al cliente).
5. `first == "/cerrar"`, `len(stripped.split()) == 2` y `1 <= len(parts[1]) <= MAX_IDENTIFIER_LENGTH` →
   `AdvisorCommand("close", parts[1], None)` (R3).
6. En otro caso → `MalformedCommand()` (R4).

Ejemplos: `/Responder case-1 hola`, `/responder@LazaroBot case-1 hola`, `/responder case-1`,
`/cerrar`, `/cerrar case-1 ya`, `/cerrarlo case-1`, `/responder <65 caracteres> hola` → mal
formado (ayuda). `/start`, `hola /responder case-1 x`, `responder case-1 x`, `/responde x` →
`None` (flujo actual). Ver D1.

El id escrito en el texto (p. ej. `/responder case-1 111 hola`) forma parte de `<texto>`; el
parser no extrae ningún id de asesor (R11).

### 3.2 `process_message`

```text
1. contact = get_or_create_contact(...)                     # sin cambios
2. command = parse_advisor_command(request.text)
   └─ command is not None → _handle_advisor_command(...) ; return     # R6-R26 (sin historial, D7)
3. add_message(contact.id, "user", request.text, received_at)        # sin cambios
4. _forward_to_advisor(contact, request, settings, adapters) → True ; return   # R27-R33
5. palabras clave de traspaso → RAG → LLM → validación              # sin cambios
```

El paso 2 va antes del reenvío (D8), de las palabras clave y del RAG: los comandos nunca pasan
por RAG ni por el LLM (R6). El paso 4 va antes de las palabras clave: un cliente con caso
`assigned` que escribe «quiero un asesor» ya tiene asesor y su mensaje se le reenvía.

### 3.3 Manejador de comandos

```python
def _handle_advisor_command(
    request: MessageRequest, contact: Contact, command: AdvisorCommand | MalformedCommand,
    settings: Settings, adapters: Adapters,
) -> None: ...
```

```text
MalformedCommand            → _notify_sender(chat_id, ADVISOR_COMMAND_HELP)            (R9)
telegram_user_id <= 0       → _deny_command(..., code="sender_not_user")              (R10, D2)
advisor_id = str(request.telegram_user_id)                                            (R11)
action == "reply" → _command_reply
    reply_to_case(case_id, CaseReplyRequest(advisor_id=advisor_id, text=command.text))  (R12)
    ├─ ok                    → _notify_sender(ADVISOR_REPLY_CONFIRMATION)              (R13)
    ├─ AdvisorForbidden      → _deny_command(..., code="forbidden")                    (R14, R24)
    ├─ CaseClosed            → _notify_sender(ADVISOR_COMMAND_CASE_CLOSED_REPLY)       (R60, R62)
    └─ CaseNotFound | UpstreamError → _notify_sender(ADVISOR_COMMAND_FAILED_REPLY)     (R15)
action == "close" → _command_close
    authorize(case_id, advisor_id, "close")                                           (R16, D4)
    close(case_id, advisor_id)                       # solo si authorize devolvió 200  (R17, R22)
    ├─ AuthorizationDenied(forbidden)   → _deny_command(code="forbidden")              (R21, R24)
    ├─ AuthorizationDenied(case_closed) → _notify_sender(ADVISOR_COMMAND_CASE_CLOSED_REPLY) (R61, R62)
    ├─ AuthorizationDenied(not_found) | ServiceUnavailable → FAILED_REPLY              (R23)
    └─ ok: contact_del_caso = get_case_contact(case_id)
           ├─ existe → _send(contact_del_caso, CASE_CLOSED_REPLY)  # historial rol bot  (R18)
           └─ None   → log case_closed_unlinked case_id=…                              (R20)
           _notify_sender(ADVISOR_CLOSE_CONFIRMATION)                                  (R19)
```

- `_notify_sender(chat_id, text, adapters)`: `adapters.gateway.send(chat_id, text)` **sin**
  guardar en el historial (R25, D7); si falla, `logger.error("advisor_command_reply_failed
  contact_id=%s", ...)`. Siempre al `chat_id` del remitente (en un grupo, al grupo).
- `_deny_command(request, contact, name, case_id, code, settings, adapters)`:
  `add_event(contact.id, "advisor_forbidden", f"command:{name} case:{case_id}
  advisor:{request.telegram_user_id} code:{code}", clock())` y `_notify_sender(...,
  ADVISOR_COMMAND_FORBIDDEN_REPLY)`. `name` ∈ {`responder`, `cerrar`}.
- Log por comando: `advisor_command action=<reply|close|malformed> contact_id=<id>
  result=<sent|closed|forbidden|failed|help>`; sin texto (R26). El `case_id` del texto no se
  escribe en el log (puede ser cualquier cosa que escriba un cliente); sí queda en el evento.
- `reply_to_case` no se modifica. Si lanza `AdvisorForbidden`, ya registró su propio
  `advisor_forbidden` en el contacto del caso o en el log (#14 R29/R30). Ver D6. Si lanza
  `CaseClosed`, no registró nada (D5 de la #14) y el manejador tampoco registra (R62).
- `CaseClosed` se captura **antes** que cualquier captura genérica de `DomainError`: hoy
  `CaseClosed`, `AdvisorForbidden`, `CaseNotFound` y `UpstreamError` son hermanas (todas
  heredan de `DomainError`), así que el orden de los `except` no cambia el resultado, pero el
  manejador debe capturar las cuatro por nombre, no `DomainError`.
- `/cerrar` sobre un caso `closed`: `authorize(close)` responde `409 case_closed` (C2 de la #13),
  así que nunca se llama a `close` (R22) y el cliente no recibe otra vez `CASE_CLOSED_REPLY`.
  `close` de handover sobre un caso `closed` responde `200` por S8; si aun así devolviera `409`
  (carrera o versión futura), el cliente HTTP lo traduce a `AuthorizationDenied("case_closed")` y
  sigue R61. Divergencia documentada con la ruta HTTP: `POST /cases/{id}/close` sobre `closed` →
  `200` sin cambios (S8); `/cerrar` sobre `closed` → texto «ya está cerrado» y ningún aviso.
  Ni el orquestador (R62) ni handover (D7 de la #14) registran denegación por un `409`.
- Una excepción no prevista en el manejador (p. ej. falla el `add_event` de `_record_forbidden`
  o de `_deny_command`, que en HTTP sería `500`) no se captura: sube a `_process` de `main.py`,
  que la registra como `process_message_failed` sin texto, igual que hoy. El remitente no recibe
  respuesta (fallo cerrado: no se envía nada a ningún cliente).
- `CaseReplyRequest(...)` no puede fallar con datos de Telegram: `text` viene de R2 (no vacío,
  ≤ 4096 porque es parte de un `MessageText`) y `advisor_id` es `str` de un entero positivo de
  Telegram (< 64 dígitos). Si fallara, la excepción la registra `_process` como hoy.

### 3.4 Reenvío cliente → asesor

```python
FORWARD_REJECTION_CODES = ("not_found", "upstream_error")


class ForwardRejected(Exception):
    """Interna: handover respondió 404 not_found o 502 upstream_error a client-message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _forward_to_advisor(
    contact: Contact, request: MessageRequest, settings: Settings, adapters: Adapters
) -> bool:
    """True si el mensaje quedó atendido (reenviado o fallo de reenvío); False → flujo actual."""
```

```text
case_id = repo.get_contact_last_case(contact.id)
None → False                                                          (R31)
forward_client_message(case_id, request.text, request.received_at)    (R27)
├─ forwarded       → evento forwarded_to_advisor "case:<id>" → True    (R28)
├─ not_assigned    → False                                             (R29)
├─ ForwardRejected("not_found")      → False                           (R30)
├─ ForwardRejected("upstream_error") → forward_failed "case:<id> code:upstream_error",
│                                      _send(FORWARD_FAILED_REPLY) → True   (R32)
└─ ServiceUnavailable → forward_failed "case:<id> code:handover_unavailable",
                        _send(FORWARD_FAILED_REPLY) → True              (R33, D5)
```

- `text` se envía **sin cambios** (R27): sin recorte (handover recorta, R48), sin escape y sin
  interpretar. El orquestador no tiene otro camino que lo use como instrucción: no llama al
  LLM, a RAG ni a ninguna otra ruta.
- `at` = `request.received_at` (la #15 dejaba este valor a la #16).
- Log: `forwarded_to_advisor contact_id=… case_id=…` / `forward_failed contact_id=… case_id=…
  code=…`, sin texto (R36). Aquí el `case_id` viene del repositorio, no del cliente.
- El mensaje del cliente ya quedó en el historial con rol `user` (paso 3), también si el
  reenvío falla: el asesor puede verlo después en el historial.
- Un asesor que escribe algo que no es un comando es un contacto más (R34): sus mensajes siguen
  este mismo camino. No se consulta `authorize` ni se compara con ninguna lista.

### 3.5 Repositorio (`adapters/repository.py`)

```python
class Repository(Protocol):
    ...  # sin cambios
    def get_contact_last_case(self, contact_id: str) -> str | None: ...
```

- `FakeRepository`: recorre `case_links` (dict, conserva el orden de inserción; `link_case` usa
  `setdefault`, así que una reutilización no reordena) y devuelve el último `case_id` cuyo
  `contact_id` coincide.
- `PostgresRepository`:
  `SELECT case_id FROM case_links WHERE contact_id = %s ORDER BY created_at DESC, case_id DESC LIMIT 1`.
  `created_at` es el reloj del orquestador al vincular. Un caso reutilizado por handover no se
  vuelve a vincular (`ON CONFLICT DO NOTHING`), pero tampoco hay un vínculo más nuevo: handover
  solo reutiliza el caso activo, que es el último.

### 3.6 Cliente HTTP de handover (`adapters/handover.py`)

```python
class HandoverClient(Protocol):
    def request(self, req: HandoverRequest) -> HandoverResponse: ...
    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...
    def authorize(self, case_id: str, advisor_id: str,
                  action: CaseAuthorizeAction) -> CaseAuthorizeResponse: ...   # #14
    def forward_client_message(
        self, case_id: str, text: str, at: datetime
    ) -> CaseClientMessageResponse: ...
    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse: ...
```

`HttpHandoverClient`, mismo estilo que `assign`/`authorize` (URL con `quote(case_id, safe='')`,
`X-Service-Token`, `Content-Type`, `timeout`). No se toca `authorize` ni `assign`.

`forward_client_message` (R37-R40):
1. `httpx.HTTPError` → `ServiceUnavailable`.
2. `200`: `CaseClientMessageResponse.model_validate(...)`; si no valida o el `case_id` no es el
   pedido → `ServiceUnavailable`.
3. `404` con `ErrorResponse.error == "not_found"` o `502` con `error == "upstream_error"` →
   `ForwardRejected(error)`; con otro cuerpo → `ServiceUnavailable`.
4. Cualquier otro código → `ServiceUnavailable`.
Log `handover_client_message_error code=<tipo o status>`, sin cuerpo.

`close` (R41-R43): igual que `authorize` de la #14: `200` válido con el mismo `case_id` →
`CaseCloseResponse`; `403`/`404`/`409` con `forbidden`/`not_found`/`case_closed` →
`AuthorizationDenied(error)`; el resto → `ServiceUnavailable`. Log `handover_close_error`.

`FakeHandoverClient` gana, sin cambiar los parámetros ni valores por defecto existentes (#7, #14):

```python
def __init__(self, ..., authorized_advisors: set[str] | None = None,
             client_message_status: str = "not_assigned",
             client_message_error: str | None = None, fail_client_message: bool = False,
             close_error: str | None = None, fail_close: bool = False) -> None: ...
    self.client_messages: list[tuple[str, str, datetime]] = []
    self.closed: list[tuple[str, str]] = []

# authorize (#14) gana al principio, tras registrar la llamada:
#   if self.authorized_advisors is not None and advisor_id not in self.authorized_advisors:
#       raise AuthorizationDenied("forbidden")
```

Por defecto `client_message_status="not_assigned"`: todos los tests existentes en los que un
contacto con caso vinculado vuelve a escribir siguen el flujo actual sin cambios.

### 3.7 Fake del gateway (`adapters/gateway.py`)

Hoy `FakeGatewayClient(fail: bool = False)` falla para todos los chats. Los tests de comandos
necesitan que falle solo el envío al cliente y no el texto fijo al asesor (T25). Cambio aditivo,
igual que el fake del gateway de handover:

```python
class FakeGatewayClient:
    def __init__(self, fail: bool = False, fail_for: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail = fail
        self.fail_for: set[int] = set(fail_for or ())

    def send(self, chat_id: int, text: str) -> None:
        if self.fail or chat_id in self.fail_for:
            raise ServiceUnavailable("Gateway caído")
        self.sent.append((chat_id, text))
```

`fail` conserva su posición, nombre y valor por defecto: ningún test existente cambia.

## 4. Handover

### 4.1 Firmas nuevas (`domain.py`)

```python
CLIENT_FORWARD_TEMPLATE = "Caso {case_id} | Cliente: {text}"


class UpstreamError(DomainError):
    code = "upstream_error"
    status_code = 502


def build_client_forward(case_id: str, text: str) -> str:
    """Texto plano `Caso <id> | Cliente: <texto>` recortado a MAX_TEXT_LENGTH. Pura."""
    return CLIENT_FORWARD_TEMPLATE.format(case_id=case_id, text=text)[:MAX_TEXT_LENGTH]


def forward_client_message(
    case_id: str, req: CaseClientMessageRequest, adapters: Adapters
) -> CaseClientMessageResponse: ...
```

```text
case = repo.get_case(case_id)
None                         → CaseNotFound 404                       (R50)
status != "assigned"         → 200 not_assigned, sin enviar           (R49)
advisor_id no casa con r"-?\d+" (o es None) → log, UpstreamError 502  (R52)
gateway.send(int(advisor_id), build_client_forward(case_id, req.text))   (R47, R48, R54)
  └─ ServiceUnavailable      → log, UpstreamError 502                 (R51)
200 forwarded
```

- `str.format` con `text` como argumento no interpreta llaves dentro del `text`: el texto del
  cliente se inserta tal cual (R53).
- No se modifica el caso ni se guarda nada (R53). No se reutiliza `add_notification`: es el
  registro de avisos de traspaso (#7) y mezclarlo cambiaría su significado; el historial completo
  ya está en el orquestador (mismo criterio que la #11).
- Log: `client_message_forwarded case_id=%s` / `client_message_forward_failed case_id=%s
  code=<send_failed|invalid_advisor_id>`; nunca `req.text` (R57).
- Texto plano (R54): `HttpGatewayClient.send` de handover construye `SendRequest(chat_id, text)`
  (contrato sin `parse_mode`, `extra="forbid"`) y el gateway llama a `sendMessage` con solo
  `chat_id` y `text`. No se toca el gateway; el test de R54 comprueba el cuerpo que sale de
  handover.

### 4.2 Ruta (`main.py`)

```python
@app.post("/cases/{case_id}/client-message", response_model=CaseClientMessageResponse)
def post_client_message(
    case_id: str, body: CaseClientMessageRequest
) -> CaseClientMessageResponse:
    return forward_client_message(case_id, body, adapters)
```

`401` (R55) y `422` (R56) los dan el middleware y el manejador existentes. Las rutas fijas
(`/cases/check-timeouts`) no colisionan: la nueva tiene dos segmentos tras `/cases/`.

## 5. Excepciones

| Servicio | Excepción | Código | HTTP | Nueva |
|---|---|---|---|---|
| handover | `UpstreamError(DomainError)` | `upstream_error` | 502 | sí |
| handover | `CaseNotFound` | `not_found` | 404 | no |
| orchestrator | `ForwardRejected(Exception)` | interna (`not_found`, `upstream_error`) | — | sí |
| orchestrator | `AuthorizationDenied`, `AdvisorForbidden` | interna / `forbidden` | — / 403 | no (#14) |
| orchestrator | `CaseClosed` | `case_closed` | 409 | no (#14, C5 de la #13) |
| orchestrator | `CaseNotFound`, `UpstreamError`, `ServiceUnavailable` | — | — | no |

En el camino de comandos ninguna excepción llega a HTTP: `POST /messages` ya respondió `202` y
el procesamiento es en segundo plano; todo se traduce a textos fijos.

## 6. Variables de entorno nuevas (orchestrator)

Se añaden al bloque `# orchestrator` de `.env.example` y a `Settings` con el mismo valor por
defecto (R44, R45). Ninguna en handover.

```dotenv
ADVISOR_REPLY_CONFIRMATION=Respuesta enviada al cliente.
ADVISOR_CLOSE_CONFIRMATION=Caso cerrado.
CASE_CLOSED_REPLY=Tu caso con el asesor quedó cerrado. Si necesitas algo más, escríbenos por aquí.
FORWARD_FAILED_REPLY=No pude hacer llegar tu mensaje al asesor. Inténtalo de nuevo en unos minutos.
ADVISOR_COMMAND_HELP=Comandos de asesor: /responder <case_id> <texto> para responder al cliente y /cerrar <case_id> para cerrar el caso.
ADVISOR_COMMAND_FORBIDDEN_REPLY=No tienes permiso para usar ese comando sobre ese caso.
ADVISOR_COMMAND_FAILED_REPLY=No se pudo completar el comando. Revisa el número de caso o inténtalo de nuevo en unos minutos.
ADVISOR_COMMAND_CASE_CLOSED_REPLY=Ese caso ya está cerrado.
```

Campos: `advisor_reply_confirmation`, `advisor_close_confirmation`, `case_closed_reply`,
`forward_failed_reply`, `advisor_command_help`, `advisor_command_forbidden_reply`,
`advisor_command_failed_reply`, `advisor_command_case_closed_reply` (`str`, mismo estilo que
`no_advisors_reply`). `ADVISOR_COMMAND_FAILED_REPLY` y `ADVISOR_COMMAND_CASE_CLOSED_REPLY` no
están en la lista del humano: ver D3 y D4. El texto de caso cerrado solo lo recibe un asesor
registrado: por la precedencia de S12 (C1 de la #13), quien no está en `ADVISOR_CHAT_IDS`
recibe `403` antes que `404` o `409` y ve el texto de no autorizado.

Los textos son fijos: no incluyen el `case_id` ni datos del cliente (así no hay plantillas que
un valor de entorno mal escrito pueda romper). `ADVISOR_COMMAND_HELP` también lo recibe un
cliente que escriba mal un comando: solo revela la sintaxis, no datos.

## 7. Limitaciones y notas

- **Identidad.** En Telegram la identidad la da el update validado con
  `TELEGRAM_WEBHOOK_SECRET`; el orquestador confía en el `telegram_user_id` de
  `POST /messages` porque esa ruta exige `SERVICE_TOKEN`. La limitación de la #14 (§7: quien
  tenga `SERVICE_TOKEN` puede suplantar) se mantiene: también podría fabricar un
  `POST /messages`. Esta feature no la empeora ni la resuelve más allá de Telegram.
- **Chat privado del asesor.** El reenvío va al chat `int(advisor_id)`. Con S13 de la #15
  (identidad = `telegram_user_id`), un asesor que asigna un caso con `/responder` queda asignado con su `telegram_user_id`; si
  nunca abrió un chat privado con el bot, Telegram rechaza el envío y el cliente recibe
  `FORWARD_FAILED_REPLY` (R51, R32). Es operativo: cada asesor debe iniciar el bot una vez.
- **Asesor retirado de `ADVISOR_CHAT_IDS` con un caso `assigned` (caso huérfano).** *Decidido
  por el humano (2026-10-31): opción C + procedimiento A*, publicado por la #17 en S12 e
  implementado por la #14 (D11, `is_orphan_case`, recuento al arrancar). Efecto en esta feature,
  sin código nuevo:
  - **Salida para el cliente (opción C):** cualquier asesor registrado puede enviar
    `/cerrar <case_id>` sobre un huérfano: handover autoriza `close` y cierra; el orquestador
    avisa al cliente (R16-R19). Después el cliente vuelve al flujo normal y puede pedir otro
    asesor (caso nuevo). `/responder` sobre un huérfano de otro asesor recibe `403` → texto de
    no autorizado (R14). Ya cubierto en handover por
    `test_authorize_close_orphan_case_allowed_for_any_registered_advisor`,
    `test_close_orphan_case_by_any_registered_advisor` y
    `test_orphan_case_cannot_be_replied_or_assigned_by_other_advisor` (#14).
  - **Procedimiento A:** antes de retirar a un asesor, este cierra sus casos con `/cerrar`;
    handover registra al arrancar cuántos huérfanos hay (sin ids).
  - **Riesgo residual aceptado (no se eligió la opción B):** hasta que alguien cierre el
    huérfano, `client-message` lo sigue tratando como `assigned` (S13: `assigned` → `forwarded`)
    y reenvía los mensajes del cliente al Telegram del asesor retirado. Esta feature no lo
    cambia: hacerlo contradiría S13 de la #15 y la decisión del humano. El `WARNING`
    `orphan_cases_present` del arranque es la señal para que un asesor activo cierre los casos.
- **Consecuencias de lo decidido (C1-C4, §9)**: un caso `assigned` no vence y bloquea el RAG del
  cliente hasta que se cierre (C1); el cliente no recibe acuse al reenviar (C2); cada mensaje de
  un contacto con caso vinculado llama a handover y, con Render dormido, D5 envía
  `FORWARD_FAILED_REPLY` (C3); las carreras y la conexión compartida de la #12 ya están
  mitigadas por la #14 y la #18, con el riesgo residual aceptado en D10 de la #14 (C4, §1).
- **Ley 1581.** El texto del cliente se envía al Telegram personal del asesor (es el propósito de
  la feature), pero no se copia en handover ni se escribe en ningún log (R36, R57). Esto **amplía
  el tratamiento de datos** que ya hacía la #7 (solo `last_messages` en el aviso): ahora cada
  mensaje del cliente mientras el caso está `assigned` sale hacia un tercero. Ver §11 (duda de
  `docs/proyecto.md` §12 sobre aviso y autorización).

## 8. Tests existentes que cambian (R58)

Regla: ningún test se elimina; ninguna aserción se relaja.

| Test | Cambio | Aserciones |
|---|---|---|
| `services/handover/tests/test_security.py` (`ROUTES`) | entrada nueva `("/cases/case-x/client-message", {"text": "hola", "at": "2026-01-02T03:00:00Z"})` | solo se amplía |
| `services/handover/tests/test_security.py` (`INVALID_BODIES`) | entradas nuevas: sin `at`, `at` sin zona, `text` vacío, campo extra | solo se amplía |

Ningún test existente del orquestador cambia: el fake devuelve `not_assigned` por defecto, la
ruta `/messages` y su contrato no cambian, y ningún texto de prueba existente empieza por
`/responder` ni `/cerrar` (comprobado con `grep` sobre `services/` y `eval/`).
`test_settings_fields_are_in_env_example` (orchestrator) pasa a exigir las ocho variables
nuevas: se cumple con T5.

## 9. Decisiones y supuestos (todos cerrados)

Revisión nocturna del 2026-11-01: no queda ninguna marca de revisión ni decisión bloqueante.
Cada punto es (i) una decisión del humano ya publicada en un contrato o en otra feature, o (ii)
un supuesto del spec_author resuelto con la opción **más conservadora**: no amplía permisos, no
envía nada a un cliente que no lo esperaba, no cambia contratos publicados ni código de la #14,
y si un texto es nuevo, es fijo y configurable. Cualquiera puede cambiarse después con una
feature nueva sin migrar datos.

### 9.1 Decididas por el humano o publicadas en contratos

| Id | Decisión | Fuente | Requirements | Tests (`tasks.md`) |
|---|---|---|---|---|
| Identidad (antes Rec. 1) | El `advisor_id` de un comando es `str(telegram_user_id)` del remitente; la pertenencia a `ADVISOR_CHAT_IDS` se comprueba con ese id, no con el `chat_id`; un id de grupo no usa comandos | Acceptance A4 de la #16; S13 de la #15 | R10, R11 | T20, T21, T56 |
| C5 (antes Rec. 2) | `/responder` sobre un caso `closed`: `reply_to_case` lanza `CaseClosed` (`409 case_closed`), sin enviar nada al cliente y sin `advisor_forbidden`; el asesor recibe `ADVISOR_COMMAND_CASE_CLOSED_REPLY` | C5 de la #13; D5 de la #14 (código actual) | R60, R62 | T71, T73 |
| `closed` en `client-message` (antes Rec. 3) | Un caso `closed` responde `not_assigned`; el cliente sigue el flujo actual (RAG) | S13 y R11 de la #15 | R29, R49 | T39, T61 |
| D4 | `/cerrar` pide `authorize(action="close")` antes de `close` (opción (a)) | Acceptance de la #13; línea `Llama` de `authorize` | R16, R22 | T26, T31 |
| Huérfanos | Opción C + procedimiento A (§7) | #17 (S12); D11 de la #14 | R14, R16-R19 | tests de la #14 en handover |
| Carreras / conexión | Asignación y cierre condicionales; candados en ambos repositorios | D10 de la #14; #18 | — | tests de la #14 y la #18 |

Cómo encaja la identidad con lo que ya existe: handover compara el `advisor_id` con `str(int)`
de cada id de `ADVISOR_CHAT_IDS` (R1 de la #14), y el orquestador le pasa
`str(telegram_user_id)` (R11). En un chat privado `telegram_user_id == chat_id`, así que S6
(«`advisor_id` contiene el chat_id del asesor») sigue siendo cierto para los asesores de chat
privado. Un id de grupo en `ADVISOR_CHAT_IDS` sigue siendo válido para recibir avisos (#10) y
para la ruta HTTP `reply` (#14), pero nunca coincide con un `telegram_user_id` positivo, y D2
impide el caso en que el gateway rellena `telegram_user_id` con el `chat_id` del grupo.

### 9.2 Supuestos del spec_author resueltos de forma conservadora

| Id | Supuesto | Por qué es el más conservador | Requirements |
|---|---|---|---|
| D1 | Gramática estricta: nombre exacto en minúsculas, sin sufijo `@bot`, `case_id` sin espacios de 1-64; cualquier primer token que empiece (sin distinguir mayúsculas) por `/responder` o `/cerrar` y no cumpla la forma recibe la ayuda | Determinista; un error de tecleo nunca llega al RAG, al LLM ni a otro cliente. Aceptar `@bot` exigiría configurar el nombre del bot | R1-R4 |
| D2 | `telegram_user_id <= 0` en un comando → no autorizado sin llamar a handover (`code:sender_not_user`) | Los usuarios de Telegram tienen ids positivos. El gateway usa `chat_id` como `telegram_user_id` cuando el update no trae `from`; sin esta regla, un id de grupo en `ADVISOR_CHAT_IDS` autorizaría comandos, contra S13. Comprobación pura que no lee la lista de asesores | R10 |
| D3 | Texto nuevo `ADVISOR_COMMAND_FAILED_REPLY` para comandos sobre un caso inexistente o con handover/gateway caídos | El humano no fijó qué recibe el asesor; el texto de «no autorizado» sería falso y la ayuda no aplica. Un no asesor nunca llega aquí (precedencia C1: `403` antes que `404`) | R15, R23 |
| D4-closed | `/cerrar` sobre un caso `closed` (`authorize` → `409`): texto nuevo `ADVISOR_COMMAND_CASE_CLOSED_REPLY`, sin `advisor_forbidden`, sin llamar a `close` y sin repetir `CASE_CLOSED_REPLY` (opción (c) del cambio 3 del informe de revisión) | Coherente con C5 (la #13 descartó ocultar al asesor que el caso está cerrado) y con D5/D7 de la #14 (un `409` no es denegación). No reenvía avisos al cliente. Diverge de S8 solo en el texto al asesor: la ruta HTTP sigue con `200` | R61, R62 |
| D5 | Si `client-message` no responde (red, `401`, `5xx` distinto de `502 upstream_error`, cuerpo inválido), se trata como fallo de reenvío (texto fijo, `forward_failed`, sin RAG) | Sin respuesta no se sabe si el caso está `assigned`; contestar con el bot a un cliente que habla con un asesor contradice «no se vuelve al RAG». Coste aceptado (C3): si handover cae o está dormido en Render, cualquier contacto con un caso vinculado, aunque esté cerrado, recibe `FORWARD_FAILED_REPLY` en vez de RAG | R33 |
| D6 | La denegación (`403`) de un comando registra `advisor_forbidden` en el contacto remitente; en `/responder`, `reply_to_case` (#14) registra además el suyo en el contacto del caso. Códigos: `sender_not_user` o `forbidden`. Un `409` no registra nada | Cumple «queda un evento `advisor_forbidden`» del acceptance; el remitente siempre tiene contacto. No modifica la #14 | R24, R62 |
| D7 | El mensaje del comando **no** se guarda en el historial del remitente, ni las respuestas fijas que recibe | El `<texto>` de `/responder` es para otro cliente: guardarlo lo copiaría a los `last_messages` de un traspaso futuro del asesor (Ley 1581). La respuesta queda en el historial del cliente con rol `advisor` y el aviso de cierre con rol `bot` | R7, R25 |
| D8 | Los intentos de comando se detectan antes del reenvío: un cliente con caso `assigned` que escribe `/cerrar …` no lo reenvía, recibe el texto de no autorizado | Una sola regla («un comando nunca se reenvía ni va a RAG»); no expone al asesor textos con forma de comando | R8 |
| D9 | El aviso `CASE_CLOSED_REPLY` solo se envía cuando el cierre llega por `/cerrar`; `POST /cases/{id}/close` de handover (herramienta interna con token) no avisa | No cambia el comportamiento ni los tests publicados de la ruta `close` de la #14; handover no tiene el historial y el aviso no quedaría registrado. El acceptance enmarca la confirmación y el aviso en los comandos de Telegram | R18, R59 |
| C1 | Un caso `assigned` no vence: mientras nadie lo cierre, todo mensaje del cliente se reenvía (antes de las palabras clave) y no recibe RAG ni puede pedir otro asesor | Consecuencia directa de «solo `assigned` se reenvía» y de que el vencimiento (#12) solo mira `open`. Salida: `/cerrar` del asesor asignado o, si es huérfano, de cualquier asesor registrado. Un vencimiento de `assigned` sería una feature nueva (opción F del informe de revisión) | R27 |
| C2 | El cliente no recibe acuse cuando su mensaje se reenvía | Añadir un acuse sería un texto nuevo que el humano no pidió y un mensaje extra por cada mensaje del cliente | R28 |
| C3 | Cada mensaje de un contacto con algún caso vinculado llama a handover | Necesario para saber si el caso sigue `assigned` sin duplicar el estado en el orquestador (principio 1). Coste: latencia y D5 | R27, R33 |
| C4 | Carreras y conexión compartida | Mitigadas por la #14 (D10) y la #18; riesgo residual aceptado en D10 de la #14 (§1) | — |

## 10. Alternativas descartadas

- **Que el orquestador decida si el remitente es asesor leyendo `ADVISOR_CHAT_IDS`.**
  Descartada: el acceptance lo prohíbe («el orquestador no lee la lista de asesores») y
  `docs/architecture.md` §3.1 hace de handover el único dueño de la lista.
- **Detectar comandos con el LLM o dejarlos pasar por RAG.** Descartada: el acceptance exige que
  nunca pasen por RAG ni por el LLM; además el LLM no es determinista y sería una superficie de
  inyección.
- **Reimplementar en el comando la lógica de `POST /cases/{id}/reply` o llamar al orquestador por
  HTTP.** Descartada: llamar a `reply_to_case` garantiza «los mismos efectos» y la autorización
  de la #14 sin duplicar código; una llamada HTTP a sí mismo añadiría red sin valor.
- **Contestar al aviso de Telegram (`reply_to_message`) en lugar de comandos.** Descartada por
  decisión del humano; exigiría `message_id` en `POST /send` (otro contrato).
- **Reenviar desde el orquestador directamente al chat del asesor con `POST /send`.**
  Descartada: el orquestador no sabe qué asesor tiene el caso; handover sí (#15, alternativa
  descartada allí).
- **Guardar el comando en el historial del remitente con rol `user`.** Descartada (D7):
  copiaría el texto destinado a otro cliente a la conversación del asesor.
- **Tratar un caso `closed` como «no autorizado» en los comandos (antigua Rec. 2 y D5 anterior
  de la #14).** Descartada: el humano decidió C5 en la #13 (`409 case_closed`, no ocultar al
  asesor que el caso está cerrado) y la #14 ya lo implementa con `CaseClosed` sin
  `advisor_forbidden`. Usar el texto de no autorizado y registrar una denegación contradiría el
  código actual y la D7 de la #14 (R60-R62).
- **Reutilizar `ADVISOR_COMMAND_FAILED_REPLY` para el caso cerrado.** Descartada: su texto
  («revisa el número de caso o inténtalo de nuevo») invita a reintentar un comando que nunca
  funcionará; un texto propio configurable es más claro y no añade riesgo.
- **Dejar de reenviar a un asesor retirado (opción B de huérfanos).** Descartada
  por el humano (#17 eligió C + A); exigiría cambiar S13 de la #15.
- **Volver al RAG cuando handover no responde a `client-message`.** Descartada (D5): rompe la
  decisión «si falla el reenvío, no se vuelve al RAG» en el caso en que no se puede saber si el
  caso está asignado.

## 11. Supuestos a confirmar

| Id | Supuesto | Valor por defecto |
|---|---|---|
| S13 (#15) | Reenvío solo con `assigned`; comandos por `POST /messages`; `advisor_id` = `telegram_user_id` | — (publicado) |
| D1-D9, C1-C4 | §9.2 | lo descrito en §9.2 |
| Textos fijos | Redacción de las ocho variables de §6 | `.env.example` (configurable) |
| Huérfanos | Opción C + procedimiento A (§7); el reenvío a un asesor retirado sigue hasta el cierre | decidido por el humano (#17) |

Dudas de `docs/proyecto.md` §12 que esta feature toca (no las resuelve; se recogen como
supuesto, sin variable nueva):

- **«Si se acepta separar el bot de clientes y el de personal».** La decisión del humano
  (comandos por `POST /messages`, S13) implica, por ahora, **un único bot** para clientes y
  asesores. Cualquiera puede ver la ayuda de los comandos (solo revela la sintaxis). Separar los
  bots sería otra feature (otro token y otro webhook en el gateway); los comandos seguirían
  llegando por `POST /messages`.
- **«Datos personales: aviso y autorización según la Ley 1581».** El reenvío al Telegram
  personal del asesor **amplía** el tratamiento que ya hacía la #7 (solo `last_messages` en el
  aviso de traspaso): ahora cada mensaje del cliente mientras su caso está `assigned` sale hacia
  el asesor, y en un huérfano hacia un asesor retirado hasta que se cierre (§7). Mitigaciones de
  esta feature: el texto no se copia en handover ni se escribe en ningún log (R36, R57), y los
  comandos no se guardan en el historial del asesor (D7). El aviso y la autorización del cliente
  siguen siendo una duda abierta del proyecto.

## 12. Dependencias

Ninguna nueva. `lazaro_contracts` con los modelos de la #13 y la #15; `httpx`, `pydantic` y
`pg8000` ya están en los `requirements.txt` de ambos servicios.
