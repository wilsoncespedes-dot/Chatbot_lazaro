# Design — panel_tiempo_real (#53)

## Resumen

Un websocket de **solo lectura** (`/asesor/ws`) avisa «algo cambió en el caso X». No transporta
datos de conversación: el navegador, al recibir el aviso, vuelve a pedir un **fragmento HTML**
por HTTP (`/asesor/live/...`), que pasa por la sesión y la autorización normales. Así se
cumple por construcción «sin tokens, secretos ni datos de otros clientes», «sin perder ni
duplicar» (el fragmento reemplaza, no anexa) y «recuperar el estado al reconectar».

El transporte entre procesos/instancias es una **tabla Postgres `panel_events`** sondeada por
cada conexión. Postgres ya es dependencia aprobada; no se introduce Redis ni otra librería de
mensajería.

## Archivos

Crear (orchestrator):
- `services/orchestrator/orchestrator/panel_live.py` — dominio puro del tiempo real:
  `PanelEvent`, `origin_allowed`, `event_payload`, `dedupe_new_events`, `LIVE_CSP`.
- `services/orchestrator/orchestrator/panel_live_routes.py` — `create_panel_live_router(settings, adapters)`
  con `WS /asesor/ws`, `GET /asesor/live/inbox`, `GET /asesor/live/cases/{case_id}`,
  `GET /asesor/static/panel_live.js`.
- `services/orchestrator/orchestrator/panel_live_js.py` — constante `PANEL_LIVE_JS` (patrón de
  `ADMIN_CSS` en `admin.py`: se sirve desde una constante Python, sin depender del empaquetado).
- Tests: `test_panel_live_pure.py`, `test_panel_live_ws.py`, `test_panel_live_publish.py`,
  `test_panel_live_fragments.py`, `test_panel_live_security.py`, `test_panel_live_js.py`,
  `test_panel_live_repository.py` (todos en `services/orchestrator/tests/`).

Modificar:
- `adapters/repository.py` — Protocol, `InMemoryRepository` y `PostgresRepository` (esquema,
  `add_message`, `link_case`, nuevos métodos, borrado en supresión).
- `domain.py` — `publish_case_event`, `advisor_case_history` (history extraído de
  `advisor_case_view` a `_case_history`), llamadas tras `assign_case`, `close_case`,
  `transfer_case`, `reassign_case`, `return_case`, `reply_to_case`.
- `advisor_panel.py` — `<script ... defer>`, contenedor `<div id="live-region" data-...>`,
  `<noscript><meta refresh>`, funciones `render_inbox_table` / `render_history_fragment`
  (extraídas de `render_advisor_cases` y `_history_section`; el HTML inicial no cambia).
- `admin.py` — `PANEL_CSP` y `panel_security_headers()` (el CSP del panel administrativo no cambia).
- `advisor_routes.py` — `_html`/`_redirect` usan `panel_security_headers()`; registra el router en
  `main.py` (`app.router.routes.extend(...)`, igual que los demás).
- `config.py`, `.env.example`, `requirements.txt` (ver Dependencias), `docs/architecture.md`
  (párrafo en «Panel de asesores multicanal»: la bandeja ya no es «sin JavaScript»; JS propio
  de mismo origen).

No se tocan `services/handover`, `gateway`, `rag`, `contracts/`.

## Firmas nuevas

```python
# panel_live.py (puro, sin IO)
@dataclass(frozen=True)
class PanelEvent:
    id: int
    case_id: str
    kind: Literal["message", "case_created", "case_updated"]

def origin_allowed(origin: str | None, host: str | None, allowed: tuple[str, ...]) -> bool: ...
def event_payload(event: PanelEvent) -> dict[str, str | int]: ...   # {"type","id","case_id"}
def dedupe_new_events(events: Sequence[PanelEvent], seen: MutableSet[int]) -> list[PanelEvent]: ...

# repository (Protocol + InMemory + Postgres)
def publish_panel_event(self, case_id: str, kind: str, at: datetime) -> None: ...
def panel_events_cursor(self) -> int: ...
def panel_events_since(self, after_id: int, since: datetime, limit: int) -> list[PanelEvent]: ...
    # id > after_id OR created_at >= since  (ventana de solape), orden por id
def delete_panel_events_before(self, before: datetime) -> int: ...
def latest_case_for_contact(self, contact_id: str) -> str | None: ...

# domain.py
def publish_case_event(case_id: str, kind: str, adapters: Adapters) -> None  # traga y registra errores
def advisor_case_history(case_id: str, actor: Profile, settings: Settings,
                         adapters: Adapters) -> tuple[HistoryItem, ...]
def visible_case_ids(actor: Profile, scope: str, adapters: Adapters) -> frozenset[str]
```

Tabla (`_SCHEMA`, `CREATE TABLE IF NOT EXISTS`, sin migración destructiva):

```sql
CREATE TABLE IF NOT EXISTS panel_events (
  id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS panel_events_created ON panel_events (created_at);
```

`PostgresRepository.add_message` añade en **la misma transacción**:
`INSERT INTO panel_events (case_id, kind, created_at) SELECT case_id, 'message', %s FROM case_links WHERE contact_id = %s ORDER BY created_at DESC LIMIT 1`.
Como cubre todo `add_message`, funciona aunque el mensaje lo procese un `BackgroundTask`
de otra instancia (R15, R19). `link_case` hace lo propio con `case_created`. Un fallo de este
INSERT adicional no debe abortar el mensaje: se ejecuta en un `SAVEPOINT` o, si el adaptador
no lo soporta, en una segunda sentencia tras el commit con `try/except` y log (R18).

## Flujo del websocket (`panel_live_routes.py`)

1. Antes de `accept()`: `settings.panel_live_enabled` (R35) → `Origin` con `origin_allowed` (R3–R5)
   → cookie + `get_session_for_roles(hash_token(token), clock(), PANEL_ROLES)` y rol en
   `ADVISOR_ROLES` (R2) → `scope` válido (R7) → contador por perfil (R9). Cualquier fallo:
   `await websocket.close(code=1008)` sin aceptar (Starlette responde `403` al handshake).
   Se usa `get_session_for_roles` directamente, **no** `_require_session`, para no llamar a
   `touch_advisor_presence` (R8).
2. `accept()`, envía `hello` con `panel_events_cursor()` (R14) e inicializa `seen` con los ids de la
   ventana de solape.
3. Bucle con `asyncio.sleep(panel_events_poll_seconds)` y una tarea paralela de `receive()`: si
   llega un mensaje → cierre `1003` (R10); si llega `websocket.disconnect` → sale. Cada ciclo,
   en `run_in_threadpool` (repositorio síncrono pg8000): revalida sesión (R6, cierre `4401`),
   `panel_events_since`, `dedupe_new_events` (R20), `visible_case_ids` una sola vez por lote
   (R11/R12, falla cerrado) y envía `event_payload` (R13).
4. `finally`: decrementa el contador.

El filtro de visibilidad usa `handover.list_cases(advisor_id, scope)`: es exactamente lo que la
bandeja muestra, así que un asesor no recibe avisos de casos que su bandeja no le mostraría.

## Fragmentos y JS

- `/asesor/live/inbox` reutiliza `advisor_inbox`/`advisor_all_cases` y `render_inbox_table`. La
  tabla incluye formularios de reasignación con `csrf_token` de la misma sesión (misma respuesta
  autenticada de mismo origen; el token **nunca** viaja por el websocket).
- `/asesor/live/cases/{id}` usa `advisor_case_history`: autoriza con
  `handover.authorize(case_id, advisor_id, "reply")` (regla de la vista de caso), no escribe
  `memory_viewed` ni `case_viewed` para no inundar la auditoría con cada refresco.
- La región en vivo se marca con atributos de datos (sin JS inline):
  `<div id="live-region" data-live-src="/asesor/live/inbox?canal=..." data-ws="/asesor/ws?scope=mine"
  data-poll="30" data-case-id="...">`.
- `PANEL_LIVE_JS`: conecta `new WebSocket(...)` (`wss` si la página es https), al `hello` y a cada
  evento cuyo `case_id` sea relevante (bandeja: cualquiera; caso: el abierto) hace `fetch(src,
  {credentials: "same-origin"})`, convierte con `DOMParser` y `replaceChildren` (reemplazo
  idempotente). Backoff 1 s → 30 s; mientras no esté conectado, `setInterval(fn, poll*1000)`
  con función (no cadena). Sin `eval`, `Function`, CDN ni `innerHTML` con datos de red.
- Solo se reemplaza la tabla (bandeja) o el historial (caso); los formularios y textareas quedan
  fuera de la región, así no se pierde lo que el asesor esté escribiendo.
- Sin JS: `<noscript><meta http-equiv="refresh" content="N"></noscript>` en la bandeja (R33).
  La vista de caso conserva `refresh=0` como hoy.

## CSP

`PANEL_CSP = "default-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"`.
`admin.security_headers()` no cambia (panel de administración); `panel_security_headers()` se usa
en todas las respuestas de `advisor_routes.py` y del router live (R29).

## Excepciones

Se reutilizan `LoginRequired`, `AdvisorAccessDenied`, `CaseNotFound`, `AdvisorForbidden`,
`UpstreamError`, `AuthorizationDenied`. No se añaden nuevas: el websocket traduce errores a
códigos de cierre y los fragmentos HTTP usan los manejadores existentes. `/asesor/live/*` con
sesión inválida redirige como el resto (`LoginRequired`, R26).

## Configuración (`.env.example`)

| Variable | Default | Uso |
|---|---|---|
| `PANEL_LIVE_ENABLED` | `true` | Interruptor general (R35) |
| `PANEL_WS_ALLOWED_ORIGINS` | vacío | CSV de orígenes exactos (R4); vacío → mismo `Host` (R5) |
| `PANEL_EVENTS_POLL_SECONDS` | `2` (1–30) | Intervalo de sondeo (R19) |
| `PANEL_EVENTS_RETENTION_HOURS` | `24` (1–168) | Retención de `panel_events` (R21) |
| `PANEL_WS_MAX_CONNECTIONS_PER_PROFILE` | `5` (1–20) | Límite por perfil e instancia (R9) |

La ventana de solape (5 s) es constante en `panel_live.py`, no ajuste de producto.

## Alternativas descartadas

1. **Redis pub/sub** (Redis está en `docker-compose.yml`): el orchestrator no tiene cliente Redis
   en `requirements.txt`; añadirlo es una dependencia no aprobada y, además, pub/sub pierde
   eventos si una instancia se reconecta. Con Postgres el evento queda en la misma transacción
   que el mensaje.
2. **`LISTEN/NOTIFY` de Postgres**: exige una conexión dedicada por instancia fuera del patrón
   síncrono de pg8000 y no entrega nada a quien estaba desconectado. El sondeo de una tabla
   pequeña cada 2 s es más simple y suficiente para una bandeja de asesores.
3. **Enviar el mensaje completo por el websocket**: obligaría a replicar la autorización y el
   filtrado de historial dentro del canal y a deduplicar en el navegador. Descartado a favor de
   «aviso + refetch».
4. **Eventos en memoria de proceso**: no cumple multi-instancia ni mensaje procesado por otro proceso.

## Dependencias nuevas

- `websockets>=13,<16` (BSD-3-Clause) en `services/orchestrator/requirements.txt`. Uvicorn la necesita
  para atender handshakes websocket en ejecución real; **los tests no la necesitan**
  (`fastapi.testclient` usa su propio transporte). El humano la instala en `.venv` antes de
  implementar; el implementer no la instala.

## Supuestos a confirmar

- **S1** Origen por defecto = mismo `Host` cuando `PANEL_WS_ALLOWED_ORIGINS` está vacío; en producción
  detrás de proxy el operador debe fijar la lista (el proxy debe preservar `Host`).
- **S2** El websocket es solo un aviso; el contenido va por fragmentos HTTP autorizados.
- **S3** Los cambios que nacen solo dentro de `handover` (p. ej. vencimiento por tiempo de espera)
  no pasan por el orchestrator y no generan evento; se reflejan en el sondeo de respaldo cada
  `ADVISOR_INBOX_REFRESH_SECONDS`. La asignación automática (#52) ocurre al escalar, que sí pasa por
  el orchestrator (`link_case`/`case_updated`).
- **S4** Un asesor al que se le quita un caso deja de recibir sus eventos (el caso sale de su
  `list_cases`); su bandeja se corrige en el siguiente evento o sondeo de respaldo.
- **S5** `connect-src 'self'` basta para `ws(s)` de mismo origen en navegadores con CSP3; si algún
  navegador lo bloquea, el panel cae al sondeo de respaldo (R32).
- **S6** Si `ADVISOR_INBOX_REFRESH_SECONDS=0`, no hay sondeo de respaldo ni `<noscript>` refresh (como hoy).
