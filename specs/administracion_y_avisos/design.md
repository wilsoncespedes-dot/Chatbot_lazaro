# #42 administracion_y_avisos — Design

Todo vive en el **orchestrator** (panel admin HTML sin JS, como #21/#37/#41).
`contracts` gana dos modelos aditivos para la ruta interna del aviso; `scripts`
gana un worker con el mismo patrón que `purgar_datos.py`. No hay servicios ni
carpetas de primer nivel nuevas ni dependencias nuevas.

## Qué ya existe y se reutiliza (no se duplica)

| Pieza existente | Origen | Uso en #42 |
|---|---|---|
| `create_client`, `renew_credential`, `revoke_credential`, `close_client_session`, `_client_status`, `ClientNotFound`, `CredentialRevoked`, `UsernameTaken` | #38 `domain.py` | Acciones de `/admin/clientes` (R3–R11). Sin cambios de lógica. |
| `credential_status`, `days_remaining` (calculados, sin contador) | #38 `identity.py` | R2, R46. Sin cambios. |
| `resolve_identity_policy` + claves `identity.*` en `app_settings` | #38 | Se integran en el registro de ajustes (R36–R40); `_POLICY_FIELDS` pasa a público `POLICY_FIELDS` para no duplicar rangos. |
| `ConversationTexts`, `/admin/texts`, `save_conversation_texts` | #37 | Se añaden 4 campos y versionado (R15–R24). |
| `channel_window`, `TemplateBlock`, `send_channel_blocks`, `advisor_send_template`, plantilla de supresión | #36/#41 | Ventana para el aviso (R50/R51); plantillas efectivas (R32–R35, R72, R73). |
| `panel_audit`, `record_panel_audit`, `_audit` | #41 | Auditoría admin (R44). Se amplía la lista de acciones y `target` admite clave/campo. |
| Sesión admin + CSRF + `LoginRequired` → 303 | #21 | R12, R13. |
| `/clients…` internos con `X-Service-Token` | #38 | Se conservan; el panel llama al dominio directamente. |

## Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/administration.py` | **Nuevo, puro** (sin IO): registro de ajustes, `resolve_operational_settings`, `validate_settings_form`, `BusinessHours`, `within_business_hours`, `format_local_date`, `render_expiry_notice`, transiciones de plantillas, `effective_templates`, agregados de métricas (`median_minutes`, `first_response_summary`). |
| `services/orchestrator/orchestrator/identity.py` | Renombrar `_POLICY_FIELDS` → `POLICY_FIELDS` (alias privado conservado). |
| `services/orchestrator/orchestrator/privacy.py` | `ConversationTexts` + `expiry_notice`, `out_of_hours_reply`, `closing_reply`, `topics_list` (R15). No entran en `consent_configured`. |
| `services/orchestrator/orchestrator/domain.py` | Excepciones nuevas; `operational_settings`; `list_clients_admin`; `update_conversation_texts` con versionado (R16–R18); `text_history`; CRUD/estado de plantillas; `effective_templates_for`; `save_operational_settings`; `send_expiry_notices`; `admin_metrics`; ajustes en `_handover` (R42), `close_case` (R23), bienvenida activa (R24), `advisor_send_template`/`advisor_case_view` (R34, R72), supresión (R35, R73), `suppression_queue` (R40). |
| `services/orchestrator/orchestrator/adapters/repository.py` | Tablas `text_versions`, `whatsapp_templates`, `credential_expiry_notices`; métodos nuevos en Protocol, `FakeRepository` y `PostgresRepository`. |
| `services/orchestrator/orchestrator/admin_routes.py` | Rutas nuevas `/admin/clientes…`, `/admin/texts/{field}/historial`, `/admin/plantillas…`, `/admin/ajustes`, `/admin/metricas`; validación de formularios; auditoría. |
| `services/orchestrator/orchestrator/admin.py` | Renderers nuevos y enlaces de navegación (R70); versión vigente en `render_conversation_texts` (R19). |
| `services/orchestrator/orchestrator/main.py` | `POST /credentials/expiry-notices` (token de servicio, R14, R45). |
| `services/orchestrator/orchestrator/config.py` | Variables de §Config con validación (R69). |
| `contracts/lazaro_contracts/credentials.py` (nuevo), `__init__.py` | `ExpiryNoticeRunRequest`, `ExpiryNoticeRunResponse` (R45). |
| `contracts/examples/expiry_notice_run_request.json`, `expiry_notice_run_response.json` | Ejemplos; mapear en `contracts/tests/test_examples.py`. |
| `contracts/CONTRATOS.md` | Sección `### POST /credentials/expiry-notices` (200/401/422). |
| `scripts/avisar_vencimientos.py` | **Nuevo**, copia estructural de `purgar_datos.py` con una sola llamada al orchestrator (R60, R61). |
| `scripts/tests/test_avisar_vencimientos.py` | Nuevo. |
| `services/handover/Dockerfile` | `COPY scripts/avisar_vencimientos.py ./avisar_vencimientos.py` (mismo patrón que los otros dos workers). |
| `docker-compose.yml` | Servicio `expiry_notice_worker` (imagen handover, `python avisar_vencimientos.py --intervalo`, `depends_on: [orchestrator]`). |
| `render.yaml` | Worker `expiry-notice-worker` con `ORCHESTRATOR_URL` (`fromService` web orchestrator), `EXPIRY_NOTICE_INTERVAL_SECONDS`, `EXPIRY_NOTICE_HTTP_TIMEOUT_SECONDS`. Variables nuevas del orchestrator. |
| `scripts/tests/test_render_blueprint.py` | Aserciones del worker nuevo. |
| `.env.example` | Sección "administración y avisos (#42)". |
| `docs/architecture.md` | Una línea en §1: administración (clientes, textos versionados, plantillas, ajustes, métricas) en `admin_routes.py`/`administration.py`; worker de avisos. |
| `services/orchestrator/tests/test_admin_clients.py`, `test_admin_texts_versions.py`, `test_admin_templates.py`, `test_admin_settings.py`, `test_business_hours.py`, `test_expiry_notices.py`, `test_admin_metrics.py`, `test_admin_permissions.py`, `test_administration_pure.py` | Nuevos (ver tasks). |
| `services/orchestrator/tests/test_config.py`, `test_repository_schema.py` | Rutas nuevas en el test de superficie `APIRoute`; tablas/índices nuevos idempotentes. |

## Esquema (aditivo e idempotente en `_SCHEMA` / `_INDEXES`)

```sql
CREATE TABLE IF NOT EXISTS text_versions (
  id BIGSERIAL PRIMARY KEY, field TEXT NOT NULL, version INTEGER NOT NULL,
  value TEXT NOT NULL, created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (field, version))
CREATE TABLE IF NOT EXISTS whatsapp_templates (
  name TEXT PRIMARY KEY, purpose TEXT NOT NULL, language TEXT NOT NULL,
  variables INTEGER NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
  approved_by TEXT, approved_at TIMESTAMPTZ,
  updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL)
CREATE TABLE IF NOT EXISTS credential_expiry_notices (
  profile_id TEXT NOT NULL, valid_until TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,            -- sending | sent | failed
  method TEXT,                     -- text | template
  attempts INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (profile_id, valid_until))
CREATE INDEX IF NOT EXISTS whatsapp_templates_purpose ON whatsapp_templates (purpose, status)
CREATE INDEX IF NOT EXISTS events_type_at ON events (type, at)
CREATE INDEX IF NOT EXISTS case_links_created ON case_links (created_at)
```

`client_credentials` no gana columnas (R2: nada de contador). Las filas de
`credential_expiry_notices` no contienen datos personales más allá del
`profile_id` (la supresión de #40 hoy no borra `client_credentials` ni
`identity_audit`; estas filas siguen la misma regla y no se tocan en #42).

## Ajustes operativos (registro en `administration.py`)

```python
@dataclass(frozen=True)
class SettingSpec:
    key: str; kind: Literal["int", "bool", "time", "days"]
    minimum: int | None; maximum: int | None; default_attr: str  # atributo de Settings

OPERATIONAL_SETTINGS: tuple[SettingSpec, ...]
```

| Clave `app_settings` | Tipo / rango | Default (variable de entorno) |
|---|---|---|
| `identity.link_ttl_minutes` … `identity.expiry_notice_days` (6 claves) | rangos de `POLICY_FIELDS` (#38) | `IDENTITY_*`, `CREDENTIAL_VALIDITY_DAYS`, `CREDENTIAL_EXPIRY_NOTICE_DAYS` |
| `expiry_notice.enabled` | bool (`true`/`false`) | `EXPIRY_NOTICE_ENABLED=true` |
| `business_hours.enabled` | bool | `BUSINESS_HOURS_ENABLED=false` |
| `business_hours.start` / `business_hours.end` | `HH:MM` 00:00–23:59, distintos | `BUSINESS_HOURS_START=06:00`, `BUSINESS_HOURS_END=21:00` |
| `business_hours.days` | CSV de 1–7 sin duplicados, no vacío | `BUSINESS_HOURS_DAYS=1,2,3,4,5,6,7` |
| `business_hours.utc_offset_minutes` | int −720..840 | `BUSINESS_HOURS_UTC_OFFSET_MINUTES=-300` |
| `suppression.deadline_business_days` | 1–60 | `SUPPRESSION_DEADLINE_BUSINESS_DAYS` (#41) |
| `suppression.due_soon_business_days` | 0–30 y < deadline | `SUPPRESSION_DUE_SOON_BUSINESS_DAYS` (#41) |

```python
@dataclass(frozen=True)
class BusinessHours:
    enabled: bool; start: time; end: time; days: frozenset[int]; utc_offset_minutes: int

@dataclass(frozen=True)
class OperationalSettings:
    identity: IdentityPolicy; expiry_notice_enabled: bool; hours: BusinessHours
    suppression_deadline_business_days: int; suppression_due_soon_business_days: int

def resolve_operational_settings(settings: Settings, overrides: dict[str, str]) -> OperationalSettings   # R39
def validate_settings_form(form: dict[str, str], settings: Settings,
                           current: dict[str, str]) -> tuple[dict[str, str], tuple[str, ...]] # (a guardar, a borrar) o SettingsInvalid  R37, R38, R74
def within_business_hours(now: datetime, hours: BusinessHours) -> bool                           # R41
def format_local_date(at: datetime, utc_offset_minutes: int) -> str                              # dd/mm/aaaa
def render_expiry_notice(template_text: str, days: int, date_text: str) -> str                   # str.replace de {dias} y {fecha}, nunca str.format
```

`identity.resolve_identity_policy` sigue existiendo y se usa dentro de
`resolve_operational_settings` (no se duplica). En dominio:

```python
def operational_settings(settings: Settings, adapters: Adapters) -> OperationalSettings
    # repo.get_app_settings(OPERATIONAL_PREFIXES) → resolve_operational_settings
```

Se lee en cada operación (sin caché en memoria), así un cambio desde el panel
rige en la petición siguiente sin reinicio (R40). `suppression_queue` y
`execute_suppression_from_panel` pasan a usar los dos valores de supresión
efectivos en lugar de `settings.*` directamente.

## Textos versionados

```python
@dataclass(frozen=True)
class TextVersion: field: str; version: int; value: str; created_by: str; created_at: datetime

# Repository
def save_conversation_texts(texts, admin_profile_id, at) -> None   # ahora: compara con lo vigente
    # en la misma transacción: por campo cambiado, INSERT text_versions(version = COALESCE(MAX,0)+1) + upsert app_settings
def current_text_versions() -> dict[str, int]                      # MAX(version) por campo
def text_history(field: str, limit: int) -> list[TextVersion]
```

`update_conversation_texts` (dominio) comprueba R18 antes de llamar al
repositorio: `texts.notice_text != vigente.notice_text and
texts.notice_version == vigente.notice_version` → `NoticeVersionRequired`
(422). La ruta `/admin/texts` mapea a 422 con el formulario. El valor vigente
sigue en `app_settings` (lectura de #37 sin cambios); `text_versions` es el
historial append-only. Los campos sin filas muestran «sin historial» (no se
crean versiones retroactivas).

Bienvenida (R24): helper `_active_welcome_text(texts)` usado en `login_client`
y `renew_credential`. Cierre (R23): `close_case` pasa `texts.closing_reply or
settings.case_closed_reply` a `_close_with_notice`.

## Plantillas

```python
TemplatePurpose = Literal["advisor_reply", "suppression_result", "expiry_notice"]
TemplateStatus = Literal["draft", "pending", "approved", "rejected", "paused"]
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]]  # R29
@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str; purpose: str; language: str; variables: int; body: str; status: str
    approved_by: str | None; approved_at: datetime | None; updated_at: datetime

def effective_templates(purpose: str, registered: Sequence[WhatsAppTemplate],
                        env_fallback: Sequence[str]) -> tuple[str, ...]   # puro, R32, R33

# Repository
def list_whatsapp_templates() -> list[WhatsAppTemplate]
def create_whatsapp_template(t: WhatsAppTemplate) -> None             # TemplateExists
def update_whatsapp_template(name, language, variables, body, actor, at) -> bool   # status=draft, aprobación NULL (R31)
def set_whatsapp_template_status(name, from_status, to_status, actor, at) -> bool  # UPDATE ... WHERE status = from_status

# domain.py
def effective_templates_for(purpose: str, settings, adapters) -> tuple[str, ...]
def create_template(...), update_template(...), change_template_status(name, to_status, actor, adapters)
```

`advisor_send_template` cambia `settings.advisor_whatsapp_template_list` por
`effective_templates_for("advisor_reply", ...)` (R34, R72); `advisor_case_view`
igual en `templates`. La supresión (R35, R73) toma
`effective_templates_for("suppression_result", ...)[0]` o, sin plantillas,
`notification_result = "skipped"`. `env_fallback` de `suppression_result` es
`(settings.suppression_result_template,)`; de `expiry_notice` es `()`.

El estado de aprobación lo registra el administrador según la respuesta del
proveedor (Meta u otro); la integración con la API real del proveedor es #43.
El gateway sigue validando su propia lista aprobada como segunda barrera.

## Horario y traspaso (R42, R43)

En `_handover`, en la rama `notified` donde hoy se envía
`settings.handover_ack_reply`:

```python
hours = operational_settings(settings, adapters).hours
if hours.enabled and not within_business_hours(adapters.clock(), hours):
    repo.add_event(contact.id, "out_of_hours", "queued", adapters.clock())
    _send(contact, texts.out_of_hours_reply or settings.handover_ack_reply, adapters)
else:
    _send(contact, settings.handover_ack_reply, adapters)
```

La rama `no_advisors` no cambia. Con `BUSINESS_HOURS_ENABLED=false` (default)
el comportamiento histórico es idéntico (R43, R71).

## Aviso de vencimiento

```python
@dataclass(frozen=True)
class ExpiringCredential: profile_id: str; valid_until: datetime

# Repository
def list_expiring_credentials(now: datetime, horizon: datetime) -> list[ExpiringCredential]
    # revoked_at IS NULL AND valid_from <= now AND valid_until > now AND valid_until <= horizon
def last_client_contact(profile_id: str) -> Contact | None          # client_sessions ORDER BY last_activity_at DESC LIMIT 1 → contacts
def claim_expiry_notice(profile_id, valid_until, now, max_attempts) -> bool
def finish_expiry_notice(profile_id, valid_until, status, method, now) -> None
def current_expiry_notice_status(profile_id, valid_until) -> str | None
```

Postgres `claim_expiry_notice` (R53, R54), una sola sentencia:

```sql
INSERT INTO credential_expiry_notices (profile_id, valid_until, status, method, attempts, created_at, updated_at)
VALUES (%(p)s, %(v)s, 'sending', NULL, 1, %(now)s, %(now)s)
ON CONFLICT (profile_id, valid_until) DO UPDATE
  SET status = 'sending', attempts = credential_expiry_notices.attempts + 1, updated_at = EXCLUDED.updated_at
  WHERE credential_expiry_notices.status = 'failed'
    AND credential_expiry_notices.attempts < %(max)s
RETURNING profile_id
```

Fila devuelta → reclamado. `FakeRepository` lo reproduce bajo un
`threading.Lock`.

```python
def send_expiry_notices(settings: Settings, adapters: Adapters) -> ExpiryNoticeRunResponse
```

Orden por candidata (R45–R59):
1. `ops = operational_settings(...)`; `not ops.expiry_notice_enabled` → respuesta `enabled=False` sin leer candidatas (R47).
2. `list_expiring_credentials(now, now + timedelta(days=ops.identity.expiry_notice_days))` (R46).
3. Horario activo y fuera de horario → `skipped.out_of_hours = len(candidatas)`; fin (R48).
4. `last_client_contact` → `None` → `no_chat` (R49).
5. Método: `contact.channel == "whatsapp"` y `channel_window(...) != "open"` → plantilla; si no, texto (R50, R51).
6. Precondición sin escribir: texto vacío → `no_text`; sin plantilla efectiva → `no_template` (R52).
7. `claim_expiry_notice` → `False` → `skipped.already_notified` (R53).
8. `send_channel_blocks(contact.channel, destino, [bloque])` (destino como en #38/#41: `external_chat_id` o `str(chat_id)` legacy).
9. Éxito → `finish(..., "sent", method)`, evento `expiry_notice` (motivo = método) e `identity_audit(profile_id, contact.id, "expiry_notice", method)` (R57). `ServiceUnavailable` (incluida `ChannelRejected`) → `finish(..., "failed", method)`, evento `expiry_notice_failed` (R58); se sigue con la siguiente.

No se llama `add_message`, `apply_conversation_event` ni `touch_client_session` (R59).
Días = `days_remaining(valid_until, now)`; fecha = `format_local_date(valid_until, offset)`.

### Contrato (aditivo, `contracts/lazaro_contracts/credentials.py`)

```python
class ExpiryNoticeRunRequest(ContractModel):
    """Cuerpo vacío {} de POST /credentials/expiry-notices."""

class ExpiryNoticeRunResponse(ContractModel):
    enabled: bool
    candidates: int = Field(ge=0)
    sent_text: int = Field(ge=0)
    sent_template: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: dict[str, int]   # out_of_hours | no_chat | no_text | no_template | already_notified
```

### Worker `scripts/avisar_vencimientos.py`

Mismo esqueleto que `purgar_datos.py` (argparse `--intervalo [s]`,
`normalize_service_url`, `MIN_SERVICE_TOKEN_LENGTH` en producción,
`main(argv, client, sleep, max_rounds)` inyectable para tests). Variables:
`ORCHESTRATOR_URL`, `SERVICE_TOKEN`, `EXPIRY_NOTICE_INTERVAL_SECONDS` (3600),
`EXPIRY_NOTICE_HTTP_TIMEOUT_SECONDS` (120). Log `expiry_notices_ok
sent_text=… sent_template=… failed=… skipped=…` o `expiry_notices_failed
status=… error=…`, sin `profile_id` ni chats. No se copia código de terceros.

## Métricas

```python
@dataclass(frozen=True)
class FirstResponseSummary: cases: int; answered: int; unanswered: int
    avg_minutes: float | None; median_minutes: float | None
@dataclass(frozen=True)
class AdminMetrics:
    since: datetime; until: datetime; first_response: FirstResponseSummary
    per_advisor: tuple[tuple[str, int], ...]; escalation_reasons: tuple[tuple[str, int], ...]
    unanswered_total: int; unanswered_samples: tuple[tuple[datetime, str], ...]

# administration.py (puro)
def first_response_summary(rows: Sequence[tuple[datetime, datetime | None]]) -> FirstResponseSummary
def median_minutes(values: Sequence[float]) -> float | None

# Repository
def case_first_responses(since, until) -> list[tuple[datetime, datetime | None]]
    # case_links en [since, until) LEFT JOIN LATERAL primer messages(role='advisor', at >= created_at)
def advisor_reply_contacts(since, until) -> list[tuple[str, int]]     # events advisor_reply, reason 'advisor:%', COUNT(DISTINCT contact_id)
def event_reason_counts(event_type: str, since, until) -> list[tuple[str, int]]
def count_events(types: tuple[str, ...], since, until) -> int
def unanswered_samples(since, until, limit) -> list[tuple[datetime, str]]  # LATERAL último messages(role='user', at <= e.at)

# domain.py
def admin_metrics(days: int, settings, adapters) -> AdminMetrics      # R62–R68
```

Etiqueta de asesor (R64): `advisor_ref` numérico →
`get_profile_by_telegram_user_id(int(ref))` → `username`; si no, el `ref`. Los
textos de R66 se truncan a 300 en dominio y el renderer los escapa. Con
`ADMIN_METRICS_UNANSWERED_LIMIT=0` no se llama `unanswered_samples` (R68).

## Rutas nuevas del panel (`admin_routes.py`, sesión admin + CSRF en POST)

| Ruta | Acción | Errores |
|---|---|---|
| `GET /admin/clientes` | Tabla (R1, R2) | — |
| `POST /admin/clientes` | Crear (R3–R6) | 422, 409 |
| `POST /admin/clientes/{id}/renovar` | R7 | 404, 409 |
| `POST /admin/clientes/{id}/revocar` | R9 | 404 |
| `POST /admin/clientes/{id}/cerrar-sesion` | R10 | 404 |
| `GET /admin/texts/{field}/historial` | R20 | 404 |
| `GET /admin/plantillas`, `POST /admin/plantillas` | R25–R28 | 422, 409 |
| `POST /admin/plantillas/{name}` | Editar (R31) | 404, 422 |
| `POST /admin/plantillas/{name}/estado` | R29, R30 | 404, 409 |
| `GET /admin/ajustes`, `POST /admin/ajustes` | R36–R38, R74 | 422 |
| `GET /admin/metricas?dias=N` | R62–R68 | 422 |

`/admin/texts` (existente) gana R16–R19. Errores de dominio se muestran con
`admin.render_error` y el código HTTP; nada de JSON en el panel. Todos los
valores se escapan (`_esc`/`html.escape`).

## Ruta interna (`main.py`)

`POST /credentials/expiry-notices` → `send_expiry_notices`; protegida por el
middleware existente de `X-Service-Token` (no se añade a la lista de
exenciones). Cuerpo distinto de `{}` → 422 (modelo `extra="forbid"` de
`ContractModel`).

## Excepciones nuevas (`domain.py`, subclases de `DomainError`)

- `NoticeVersionRequired` — `notice_version_required`, 422 (R18).
- `SettingsInvalid` — `validation_error`, 422 (R38); lleva la lista de claves inválidas.
- `TemplateExists` — `template_exists`, 409 (R28).
- `TemplateNotFound` — `template_not_found`, 404.
- `TemplateTransitionInvalid` — `invalid_transition`, 409 (R30).
- Se reutilizan `ClientNotFound`, `CredentialRevoked`, `UsernameTaken`,
  `PanelValidationError` (R27, R67, R72).

`admin.render_error` gana mensajes para los códigos nuevos.

## Config (`.env.example`, sección "administración y avisos (#42)")

| Variable | Default | Rango |
|---|---|---|
| `BUSINESS_HOURS_ENABLED` | `false` | bool |
| `BUSINESS_HOURS_START` | `06:00` | `HH:MM` |
| `BUSINESS_HOURS_END` | `21:00` | `HH:MM`, ≠ start |
| `BUSINESS_HOURS_DAYS` | `1,2,3,4,5,6,7` | CSV 1–7 |
| `BUSINESS_HOURS_UTC_OFFSET_MINUTES` | `-300` | −720..840 |
| `EXPIRY_NOTICE_ENABLED` | `true` | bool |
| `EXPIRY_NOTICE_MAX_ATTEMPTS` | `3` | 1–10 |
| `EXPIRY_NOTICE_INTERVAL_SECONDS` | `3600` | > 0 (solo worker) |
| `EXPIRY_NOTICE_HTTP_TIMEOUT_SECONDS` | `120` | > 0 (solo worker) |
| `ADMIN_TEXT_HISTORY_LIMIT` | `20` | 1–200 |
| `ADMIN_METRICS_UNANSWERED_LIMIT` | `20` | 0–200 |

Las cinco `BUSINESS_HOURS_*` y `EXPIRY_NOTICE_ENABLED` son solo el valor por
defecto: el panel los sobrescribe en `app_settings` (`docs/architecture.md`
§3.5). `EXPIRY_NOTICE_MAX_ATTEMPTS` y los límites de UI son infraestructura.

## Dependencias

Ninguna nueva. Se evita `zoneinfo` con base de datos IANA (en Windows y en
imágenes slim puede requerir el paquete `tzdata`): el horario usa un
desplazamiento UTC fijo configurable (Colombia no tiene horario de verano).

## Alternativas descartadas

- **Programar el aviso dentro del proceso del orchestrator** (hilo o tarea al
  arrancar): Render duerme los servicios web gratuitos y varias instancias
  duplicarían envíos. Se usa un worker externo como `retention-worker`, con la
  idempotencia en BD (R53, R54).
- **Añadir el aviso al `retention-worker`**: acoplaría la purga legal (que se
  salta el orchestrator si handover falla) con un aviso comercial y su
  intervalo de 24 h es demasiado grueso. Coste: un worker más en Render (ver S5).
- **Contador de días en `client_credentials`**: lo prohíbe el acceptance y
  `docs/especificacion.md`; se calcula siempre desde fechas (R2).
- **Mover `PRIVACY_RETENTION_DAYS` / `PRIVACY_ACTIVE_CASE_MAX_DAYS` al panel**:
  los lee también handover en su propia purga; cambiarlo solo en el
  orchestrator desincronizaría los servicios. Requiere contrato propio (S3).
- **Restaurar una versión antigua de texto con un botón**: no lo pide el
  acceptance; el historial (R20) permite copiar el valor. Queda para otra
  feature.
- **Integrar la aprobación con la API de Meta**: depende del proveedor real
  (#43). Aquí el administrador registra el estado.

## Supuestos a confirmar (defaults seguros configurables, no bloquean)

- **S1 Horario**: 06:00–21:00 todos los días en UTC−5, desactivado por defecto
  (`BUSINESS_HOURS_ENABLED=false`) hasta que el administrador lo active en
  `/admin/ajustes`; sin festivos. Fuera de horario el caso se crea igual y el
  cliente recibe `out_of_hours_reply`.
- **S2 Aviso único por periodo**: clave `(profile_id, valid_until)`; hasta
  `EXPIRY_NOTICE_MAX_ATTEMPTS=3` intentos solo si el envío falló; un envío
  ambiguo (timeout tras entrega) puede no reintentarse si se marcó `sent`, y un
  fallo real se reintenta a la hora. Una fila `sending` huérfana (caída del
  proceso) no se reintenta: se prefiere no duplicar un mensaje con coste.
- **S3 Plazos de retención** siguen en entorno (multiservicio); el plazo de
  supresión (`suppression.*`, solo orchestrator) sí pasa al panel, como
  anunciaba #41 S4. Pendiente de validación legal (`docs/proyecto.md` §12).
- **S4 Plantillas**: sin registro de un propósito rige la lista de entorno de
  #41 (compatibilidad); en cuanto se registra una plantilla de ese propósito,
  solo las `approved` valen. El aviso de vencimiento nunca usa respaldo de
  entorno: sin plantilla aprobada no se envía por WhatsApp fuera de ventana
  (cada envío tiene coste; `docs/especificacion.md` "si se aprueba").
- **S5 Worker en Render**: `expiry-notice-worker` es un servicio adicional
  (posible coste). El plan lo elige el humano al crear el Blueprint, como el
  resto.
- **S6 Aviso fuera de horario**: con horario activo los avisos esperan a la
  siguiente pasada dentro de horario (no se escribe de noche).
- **S7 Preguntas sin respuesta**: se muestran hasta 20 textos truncados para
  mejorar la base de conocimiento; `ADMIN_METRICS_UNANSWERED_LIMIT=0` los
  oculta. Los textos desaparecen con la purga de `messages`.
- **S8 Supervisor**: no existe ese rol (#41); las métricas son solo para
  `admin`. Reactivar credenciales revocadas (#38 supuesto 1) sigue fuera.
- **S9 Fechas del formulario**: `AAAA-MM-DD` interpretadas como medianoche
  local con `business_hours.utc_offset_minutes`.
