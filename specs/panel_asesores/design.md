# #29 panel_asesores — Design

## Decisión

El panel vive en el orchestrator, junto al de #21, en rutas `/asesor/*`. Reutiliza
la tabla `admin_sessions`, la tabla `admin_login_attempts`, `hash_token`,
`verify_password`, CSRF de sincronización, `security_headers()`, `render_page`,
`/admin/static/admin.css` y `html.escape`. El orchestrator llama a handover desde
el servidor con `HttpHandoverClient` y `SERVICE_TOKEN`; el navegador solo ve HTML.
Sin servicio nuevo, sin JS, sin dependencias nuevas, sin código externo.

Las reglas de quién puede hacer qué viven solo en handover (S12, #14, #17). El
panel no las evalúa: identifica al asesor y traduce la respuesta de handover.

## Archivos

| Archivo | Cambio |
|---------|--------|
| `orchestrator/advisor_panel.py` (nuevo) | Plantillas puras con `html.escape`: `render_advisor_login`, `render_advisor_home(csrf, ok, linked)` (formularios responder/asignar/cerrar con `case_id`), `render_advisor_error(status, code, csrf)` con mensajes fijos por código (R14). Reutiliza `admin.render_page`/`security_headers`. |
| `orchestrator/advisor_routes.py` (nuevo) | `create_advisor_router(settings, adapters)`: `GET/POST /asesor/login`, `POST /asesor/logout`, `GET /asesor`, `POST /asesor/reply`, `POST /asesor/assign`, `POST /asesor/close`; `GET /asesor/cases` solo tras el contrato previo (R13). Reutiliza `_form`, `_require_csrf`, `client_ip` de `admin_routes.py` (se importan, no se copian). |
| `orchestrator/domain.py` | `authenticate_profile(username, password, ip, role, settings, adapters)`; `authenticate_admin` pasa a delegar con `role="admin"` sin cambiar su comportamiento. `close_case(case_id, advisor_id, settings, adapters)` extraído de `_command_close` (authorize → close → aviso al cliente); `_command_close` lo usa y conserva su comportamiento observable. `assign_case(case_id, advisor_id, adapters)`. Ambos llaman a `_record_forbidden` en `403` (R15). |
| `orchestrator/adapters/handover.py` | `try_assign(case_id, advisor_id) -> CaseAssignResponse` en Protocol, Http y Fake: `403 forbidden` / `404 not_found` / `409 case_closed` → `AuthorizationDenied(code)` (mismo mapeo y validación que `authorize` con `_DENIAL_CODES`); resto → `ServiceUnavailable`. `assign` existente **no cambia** (lo usa `reply_to_case` y su fallo sigue siendo `assign_failed`). |
| `orchestrator/adapters/repository.py` | `get_session_for_role(token_hash, now, role)` en Protocol, Fake y Postgres; `get_session` delega con `role="admin"` (R5). Sin tablas nuevas. |
| `orchestrator/main.py` | `include` del router; el middleware de `X-Service-Token` deja pasar `/asesor` y `/asesor/*`; el handler de `LoginRequired` redirige a `/asesor/login` cuando el path empieza por `/asesor`; `CsrfInvalid` siempre devuelve `403` con la página de error del panel. |
| `tests/test_advisor_panel.py` (nuevo) | R1–R15 con `FakeRepository`, `FakeHandoverClient`, `FakeGateway`. |

## Firmas

```python
# domain.py
def authenticate_profile(username, password, client_ip, role, settings, adapters) -> str | None
def assign_case(case_id: str, advisor_id: str, adapters: Adapters) -> CaseAssignResponse
    # AdvisorForbidden | CaseNotFound | CaseClosed | UpstreamError
def close_case(case_id: str, advisor_id: str, settings: Settings, adapters: Adapters) -> None
    # AdvisorForbidden | CaseNotFound | CaseClosed | UpstreamError

# adapters/repository.py
def get_session_for_role(self, token_hash, now, role) -> AdminSession | None
    # Postgres: JOIN profiles ... AND p.role = %s (parametrizado)

# advisor_routes.py
def _advisor_id(session, adapters) -> str   # str(profile.telegram_user_id) o TelegramNotLinked (403, R9)
```

Orden en cada `POST` protegido: sesión (R4) → leer formulario → CSRF (R6) →
perfil vinculado (R9) → validación `case_id` con `Identifier` y `text` con
`CaseReplyRequest` (`422`) → dominio → `303` o página de error (R14).

- **Sesión.** Mismo token (`secrets.token_urlsafe(32)`, se guarda su SHA-256),
  misma tabla; cookie distinta `advisor_session` con `Path=/asesor`. Como la
  cookie admin tiene `Path=/admin`, el navegador no cruza cookies; además
  `get_session_for_role` rechaza una sesión de otro rol aunque se fuerce la
  cookie (R5). El login de `/asesor` comparte el límite de intentos de #21
  (`count_login_failures`/`record_login_failure`), sin columna de panel: un
  fallo cuenta para ambos (R3).
- **advisor_id.** Se lee el perfil (`get_profile`) en cada acción, así un cambio
  de vínculo o de rol se aplica a la siguiente petición.
- **Reply** reutiliza `reply_to_case` tal cual (autoriza, envía, guarda, asigna,
  registra `advisor_forbidden` en `403`).
- **Errores (R14).** Mapeo de excepciones existentes: `AdvisorForbidden` → 403
  `forbidden`; `CaseNotFound` → 404 `not_found`; `CaseClosed` → 409
  `case_closed`; `UpstreamError` → 502 `upstream_error`. Nunca se muestra el
  `message` de handover; los logs solo llevan acción, `case_id` y resultado.
- **Datos personales.** Las páginas nunca muestran `chat_id`, `contact_id`,
  ids de Telegram de clientes ni texto de la conversación; el texto enviado no se
  re-renderiza tras el `303`.

## Dependencia #33: contrato para listar casos (R13)

Handover no expone ninguna ruta de lectura de casos y el orquestador no tiene
estado ni asesor de los casos (`case_links` solo guarda `case_id → contact_id`).
Listar "los casos que las reglas permiten" exige una ruta nueva en el contrato
de handover y, según `docs/architecture.md` §3.2, eso es una feature propia.

Feature previa registrada como #33 y añadida a `dependencies` de #29: **`contrato_listar_casos_asesor`** — handover publica
`GET /cases?advisor_id=<id>` (con `X-Service-Token`) que devuelve, aplicando S12
y #17 en handover: casos `open`/`timed_out` si el asesor está en
`ADVISOR_CHAT_IDS`; `assigned` a ese asesor; huérfanos (solo acción `close`).
Defaults seguros propuestos: campos `case_id`, `status`, `created_at`,
`actions: list["reply"|"assign"|"close"]`; sin `contact_id`, `chat_id`,
`reason` ni `last_messages`; asesor no registrado → `200` con lista vacía;
máximo `CASE_LIST_LIMIT=50`, más antiguos primero.

La implementación de `GET /asesor/cases` espera a que #33 esté done; la home ofrece los
formularios por `case_id` (igual que los comandos de Telegram, que también
reciben el `case_id` del aviso). Las tasks T9–T10 dependen de #33.

## Config

Sin variables nuevas: se reutilizan `ADMIN_SESSION_TTL_MINUTES`,
`ADMIN_COOKIE_SECURE`, `ADMIN_LOGIN_MAX_ATTEMPTS`, `ADMIN_LOGIN_WINDOW_MINUTES`,
`ADMIN_TRUST_PROXY_HEADERS` y `CASE_CLOSED_REPLY`.

## Dependencias

Ninguna nueva.

## Alternativas descartadas

- **Servicio `advisor_panel` aparte**: tendría que guardar `SERVICE_TOKEN` y
  duplicar sesiones; `docs/architecture.md` §1 pide no añadir servicios.
- **Comprobar reglas S12 en el orquestador** (p. ej. ocultar botones según
  estado): duplicaría reglas de handover y podría divergir. El panel pregunta a
  handover y muestra su respuesta.
- **Listar casos desde `case_links`/eventos del orquestador**: no tiene estado
  ni asesor, mostraría casos ajenos o cerrados y violaría el aislamiento.
- **Cambiar `assign` existente para distinguir 403/404/409**: alteraría
  `reply_to_case` (hoy cualquier fallo de assign es `assign_failed`); se añade
  `try_assign` en su lugar.

## Supuestos a confirmar

- Solo el rol `asesor` entra a `/asesor`; un `admin` que también atienda casos
  necesita un perfil `asesor` aparte (no se mezclan permisos de paneles).
- La autorización efectiva sigue siendo `ADVISOR_CHAT_IDS` (#14): un perfil
  `asesor` vinculado cuyo id no esté en la lista recibe `403` de handover.
- Los campos y el límite del listado son los defaults de la feature previa
  propuesta; si el humano quiere mostrar `reason` o mensajes, se decide allí.
