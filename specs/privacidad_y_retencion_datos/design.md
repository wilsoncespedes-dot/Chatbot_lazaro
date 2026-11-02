# Design — privacidad_y_retencion_datos (feature #27)

## 1. Alcance

- **orchestrator**: puerta de consentimiento en la ruta de cliente de `process_message`, prueba
  mínima de consentimiento, `POST /privacy/purge` y validación de configuración.
- **handover**: `POST /privacy/purge` sobre sus propias tablas (incluido el cierre y borrado de
  casos activos que superan el límite) y validación de configuración. Es seguro dentro de la
  arquitectura: cada servicio purga solo su base (no hay acceso cruzado), con el mismo patrón ya
  usado por `POST /cases/check-timeouts`.
- **scripts + compose**: `scripts/purgar_datos.py` y servicio `retention_worker`, calco de
  `vencer_casos.py` / `timeouts_worker` (#12), con orden fijo handover → orchestrator.
- **contracts**: modelos y documentación de `POST /privacy/purge`.
- **Sin cambios**: `telegram_gateway` (no persiste datos; Redis solo guarda `update_id` con TTL
  `DEDUP_TTL_SECONDS`) y `rag` (solo manuales).
- Sin dependencias nuevas.

## 2. Inventario de datos y frontera

| Tabla (servicio) | Contenido personal | Tratamiento |
|---|---|---|
| `messages` (orch) | texto de cliente y de asesor | borrar por antigüedad `at` < corte (R22) |
| `events` (orch) | `contact_id`; `reason` puede llevar `telegram_user_id`/`case_id` | borrar por antigüedad (R23) |
| `contacts` (orch) | `telegram_user_id`, `chat_id` | borrar si inactivo (R24) |
| `case_links` (orch) | `case_id` ↔ `contact_id` | borrar con su contacto inactivo (R24) |
| `handover_cases` (hand) `closed` | `contact_id`, `chat_id`, `last_messages` | borrar con `closed_at` < corte (R34) |
| `handover_cases` (hand) activos | `contact_id`, `chat_id`, `last_messages` | cerrar y borrar con `created_at` < corte de casos activos (R35, R37) |
| `handover_requests` (hand) | `contact_id` | borrar por `received_at` < corte (R38) y las de casos borrados por R35 (R36) |
| `privacy_consents` (orch, nueva) | `telegram_user_id` | **conservar**: prueba de autorización (S5) |

**Registros operativos preservados y justificación** (R26, R37, R39):

- Personal (fuera de alcance de #27): `profiles`, `link_tokens`, `admin_sessions`,
  `admin_login_attempts` (ya tiene su propia purga), `db_query_audit` (auditoría exigida por
  `docs/proyecto.md` §6). No se borran credenciales ni perfiles.
- Sin dato personal: `processed_updates` (solo `update_id`), `query_categories`, `app_settings`,
  `privacy_purge_runs`.
- `handover_notifications`, `handover_denials`: solo `case_id`, `advisor_id` (personal) y códigos.
  Al borrarse el caso dejan de enlazar con el cliente; se conservan como auditoría de seguridad.
- Casos activos con `created_at` ≥ corte de casos activos: siguen operativos (un `timed_out` aún
  puede asignarse) y no se tocan (R37). Ningún registro reciente se borra.

### 2.1 Coherencia handover ↔ orchestrator (casos activos)

Problema: el orchestrator borra un contacto inactivo con sus `case_links` (R24) sin conocer el
estado del caso; si handover lo conservara vivo, `send_case_reply` daría `CaseNotFound` sobre un
caso aún asignable, y sus datos quedarían retenidos sin límite.

Regla: **ningún caso activo sobrevive a su `case_link`**. Se garantiza con tres piezas:

1. **Límite obligatorio** `PRIVACY_ACTIVE_CASE_MAX_DAYS` (handover), sin valor por defecto,
   requerido en producción (R29) y estrictamente menor que `PRIVACY_RETENTION_DAYS` (R31).
2. **Cierre por retención** en la purga de handover: todo caso activo con `created_at` < corte de
   casos activos se cierra y borra con sus `handover_requests` en una transacción (R35, R36). No
   se persiste un estado `closed` intermedio: el caso deja de existir (cualquier operación
   posterior sobre él da `case_not_found`). No se notifica a cliente ni asesor (S6).
3. **Orden** en cada iteración del worker: primero handover, luego orchestrator, y el
   orchestrator no se llama si handover falló (R41–R43).

Demostración: el `case_link` se crea después de que handover crea el caso, así que
`case.created_at ≤ link.created_at`. El orchestrator solo borra un `case_link` si
`link.created_at < t₂ − R` (t₂ = reloj del orchestrator). Con `A < R` en días enteros,
`t₂ − R ≤ t₂ − A − 1 día < t₁ − A` mientras `t₂ − t₁ < 1 día` (t₁ = reloj de handover en la misma
iteración; ambas llamadas tardan como mucho 2 × `PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS`). Por tanto
el caso ya tenía `created_at` < corte de casos activos y handover lo borró antes. Por eso R31
exige desigualdad estricta: con `A = R` una iteración que cruce el instante del corte podría
dejar un caso vivo sin `case_link`.

## 3. Firmas nuevas

### contracts (`lazaro_contracts/privacy.py`, exportadas en `__init__.py`)

```python
class PrivacyPurgeRequest(ContractModel): pass           # cuerpo {}
class PrivacyPurgeResponse(ContractModel):
    cutoff: AwareDatetime
    deleted: dict[str, int]          # tabla -> filas borradas
    closed_active_cases: int = 0     # handover: casos activos cerrados y borrados (R35); orch: 0
```
Error nuevo en la tabla común: `503 privacy_not_configured` en `/privacy/purge`.

### orchestrator

- `config.py`: campos `privacy_notice_text: str = ""`, `privacy_notice_version: str = ""`,
  `privacy_accept_phrase: str = ""`, `privacy_accepted_reply: str = ""`,
  `privacy_retention_days: str = ""` (cadena para distinguir vacío). Propiedades
  `privacy_configured -> bool`, `retention_days -> int | None`. Las 5 variables se añaden a
  `REQUIRED_IN_PRODUCTION` (R1). Validadores R2 y R3 con `normalize_privacy_text`. El
  orchestrator no lee `PRIVACY_ACTIVE_CASE_MAX_DAYS`.
- `privacy.py` (nuevo, puro): `normalize_privacy_text(text) -> str`,
  `notice_sha256(text) -> str`, `is_acceptance(text, phrase) -> bool` (igualdad normalizada).
- `domain.py`:
  - `_privacy_gate(request, settings, adapters) -> bool`: `True` si hay que seguir. Orden:
    config incompleta → log `privacy_not_configured`, `False` → `202` (R4–R6); consentimiento
    vigente → `True` (R16); `is_acceptance` → `add_privacy_consent(...)`,
    `_notify_sender(accepted_reply)`, `False` (R9–R11, R17/R18: la excepción se propaga antes
    del envío); si no → `_notify_sender(notice_text)`, `False` (R7, R8, R12, R13).
  - `process_message`: `get_or_create_contact` deja de ejecutarse al inicio. Las rutas de
    personal lo obtienen igual que hoy dentro de su rama (R19); la ruta de cliente llama a
    `_privacy_gate` **antes** de `get_or_create_contact` y de `add_message`.
  - `purge_personal_data(settings, adapters) -> PrivacyPurgeResponse`: sin `retention_days`
    lanza `DomainError("privacy_not_configured", 503)` (R21); si no, `cutoff = clock() - días`
    y delega en el repositorio; `closed_active_cases = 0`.
- `adapters/repository.py` (Protocol, InMemory, Postgres):
  - `has_privacy_consent(telegram_user_id: int, notice_version: str) -> bool`
  - `add_privacy_consent(telegram_user_id: int, notice_version: str, notice_sha256: str,
    accepted_at: datetime) -> None`
  - `purge_personal_data(cutoff: datetime, ran_at: datetime) -> dict[str, int]` — una
    transacción en Postgres, en este orden: calcular contactos inactivos; borrar sus
    `case_links`; borrar esos `contacts`; borrar `messages` < corte; borrar `events` < corte;
    insertar `privacy_purge_runs` (R22–R28). Claves: `messages`, `events`, `contacts`,
    `case_links`.
  - Esquema: `privacy_consents (id BIGSERIAL PK, telegram_user_id BIGINT NOT NULL,
    notice_version TEXT NOT NULL, notice_sha256 TEXT NOT NULL, accepted_at TIMESTAMPTZ NOT NULL)`
    con índice `(telegram_user_id, notice_version)`; `privacy_purge_runs (id BIGSERIAL PK,
    ran_at TIMESTAMPTZ NOT NULL, cutoff TIMESTAMPTZ NOT NULL, counts JSONB NOT NULL)`.
- `main.py`: `POST /privacy/purge` (`PrivacyPurgeRequest` → `PrivacyPurgeResponse`); el token lo
  aplica el middleware existente (R20).

### handover

- `config.py`: `privacy_retention_days: str = ""` y `privacy_active_case_max_days: str = ""`,
  ambos en `REQUIRED_IN_PRODUCTION` (R29); validadores R30 (entero ≥ 1 si no vacío) y R31
  (`active < retention` si ambos presentes); propiedades `retention_days -> int | None`,
  `active_case_max_days -> int | None`, `retention_configured -> bool`.
- `domain.py`: `purge_personal_data(settings, adapters) -> PrivacyPurgeResponse`: si
  `retention_configured` es falso lanza `DomainError("privacy_not_configured", 503)` (R32); si
  no, `cutoff = clock() - retention_days`, `active_cutoff = clock() - active_case_max_days` (un
  solo `clock()`), delega en el repositorio y construye la respuesta (R40).
- `adapters/repository.py` (Protocol, InMemory, Postgres):
  `purge_personal_data(cutoff, active_cutoff, ran_at) -> tuple[dict[str, int], int]`, una
  transacción en Postgres, en este orden:
  1. `SELECT case_id FROM handover_cases WHERE status IN ('open','assigned','timed_out') AND
     created_at < %s FOR UPDATE` (active_cutoff) → ids expirados;
  2. `DELETE FROM handover_requests WHERE case_id = ANY(%s) OR requested_case_id = ANY(%s)`
     (R36);
  3. `DELETE FROM handover_cases WHERE case_id = ANY(%s)` → `closed_active_cases` (R35, R37);
  4. `DELETE FROM handover_cases WHERE status='closed' AND closed_at < %s` (cutoff, R34);
  5. `DELETE FROM handover_requests WHERE received_at < %s` (cutoff, R38);
  6. insertar en `privacy_purge_runs` de handover (misma forma; `counts` incluye
     `closed_active_cases`).
  Claves de `deleted`: `handover_cases` (solo paso 4), `handover_requests` (pasos 2 + 5). En
  InMemory también se descarta la entrada de `timeout_claims` del caso borrado. Un
  `mark_timed_out`/`assign_*` concurrente sobre un caso borrado devuelve `False`/no encontrado
  con el comportamiento existente.
- `main.py`: `POST /privacy/purge` (token por middleware existente, R33).

### scripts / compose / .env.example

- `scripts/purgar_datos.py`: misma estructura que `vencer_casos.py` (`_call_once(url)`,
  `_run_iteration() -> bool`, `main(argv)`, `--intervalo`). `_run_iteration` llama a handover;
  solo si responde `200` llama al orchestrator (R41–R43); devuelve `True` si ambas fueron `200`.
  Logs `privacy_purge_ok service=<s> deleted=<json> closed_active_cases=<n>`,
  `privacy_purge_failed service=<s> status=<c>` y
  `privacy_purge_skipped service=orchestrator reason=handover_failed`.
- `services/handover/Dockerfile`: `COPY scripts/purgar_datos.py ./purgar_datos.py` (R48).
- `docker-compose.yml`: `retention_worker` (build con Dockerfile de handover, `env_file: [.env]`,
  `command: ["python", "purgar_datos.py", "--intervalo"]`, `depends_on: [orchestrator, handover]`,
  `restart: unless-stopped`, sin `ports`) (R47, R49).
- `.env.example`, sección `# privacidad (#27) — valores APROBADOS POR EL DUEÑO`:
  `PRIVACY_NOTICE_TEXT=`, `PRIVACY_NOTICE_VERSION=`, `PRIVACY_ACCEPT_PHRASE=`,
  `PRIVACY_ACCEPTED_REPLY=`, `PRIVACY_RETENTION_DAYS=`, `PRIVACY_ACTIVE_CASE_MAX_DAYS=` (vacíos,
  sin ejemplo de plazo; comentario: debe ser menor que `PRIVACY_RETENTION_DAYS`) y, solo para
  activar el mecanismo, `PRIVACY_PURGE_INTERVAL_SECONDS=86400`,
  `PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS=120` (R50).

## 4. Excepciones

Se reutilizan `ProductionConfigError`, `ValueError` de validación de `Settings` y `DomainError`
(código `privacy_not_configured`, `503`) de cada servicio. Fallo de BD al guardar consentimiento
→ excepción no capturada → `500 internal_error` del manejador existente (R17, R18). Fallo de BD
en la purga de handover → rollback completo (ningún caso activo queda medio borrado) → `500` →
el script no llama al orchestrator (R43).

## 5. Alternativas descartadas

- **Poner la puerta antes de todas las rutas**: rompería a asesores de `ADVISOR_CHAT_IDS` sin
  perfil vinculado (los autoriza handover, no el orchestrator) y el `/start <token>`. Las rutas
  de personal no guardan texto como mensaje de cliente; sus registros (denegaciones en `events`)
  quedan sujetos a la purga por antigüedad.
- **Anonimizar `events` en vez de borrarlos**: `reason` puede llevar `telegram_user_id` y
  `case_id`; anonimizar exigiría reescribir motivos. Borrar por antigüedad es más simple y seguro.
- **Que el orchestrator borre datos de handover**: rompe la propiedad de datos por servicio.
- **Plazo o límite por defecto**: prohibido; no hay base aprobada para un número.
- **Aceptar por «contiene la frase» o por `/start`**: no es una acción inequívoca (R12–R14).
- **Conservar casos activos sin límite (`retained_active`)**: solo hacía visible la retención
  indefinida y dejaba casos vivos sin `case_link`. Reemplazado por el límite obligatorio (§2.1).
- **Que el orchestrator conserve `case_links` de casos no cerrados**: el orchestrator no conoce
  el estado del caso (exigiría una llamada cruzada por enlace) y seguiría sin acotar la
  retención en handover.
- **Límite por última actividad (`assigned_at`/`timeout_claimed_at`)**: no existe `timed_out_at`
  y la demostración de §2.1 depende de `case.created_at ≤ link.created_at`; `created_at` es la
  única base que garantiza la coherencia.
- **Intentar el orchestrator aunque falle handover**: podría borrar el `case_link` de un caso
  que handover no llegó a cerrar.

## 6. Supuestos a confirmar (aprobación del dueño requerida)

La interpretación legal **no está verificada con abogado** (`docs/proyecto.md` §11). Ningún
valor se decide aquí; el sistema falla cerrado hasta que el dueño los configure.

| Id | Decisión del dueño | Variable / efecto mientras falte |
|---|---|---|
| S1 | Texto del aviso, finalidades, responsable y canal de derechos del titular | `PRIVACY_NOTICE_TEXT`; sin él no se procesa la ruta de cliente |
| S2 | Versión del aviso | `PRIVACY_NOTICE_VERSION`; cambiarla exige reaceptación (R15) |
| S3 | Frase de aceptación (debe aparecer en el aviso, R3) y respuesta de confirmación | `PRIVACY_ACCEPT_PHRASE`, `PRIVACY_ACCEPTED_REPLY` |
| S4 | Plazo de retención y su base (aquí: antigüedad de cada registro; contactos por inactividad) | `PRIVACY_RETENTION_DAYS`; sin él `/privacy/purge` responde `503` y producción no arranca |
| S5 | Cuánto conservar `privacy_consents` (prueba de autorización); #27 no la purga | sin variable; decisión pendiente |
| S6 | Vida máxima de un caso `open`/`assigned`/`timed_out` desde su `created_at`; al excederla se cierra y borra sin aviso a cliente ni asesor | `PRIVACY_ACTIVE_CASE_MAX_DAYS` (< `PRIVACY_RETENTION_DAYS`, R31); sin él producción no arranca y `/privacy/purge` de handover responde `503` |

**Fuera de alcance (posibles features futuras):** solicitudes individuales de supresión o
revocación por el titular; datos sensibles; logs de plataforma (stdout), copias de seguridad de
Render y datos del personal; aviso al asesor antes del cierre por retención.

## 7. Fuentes oficiales consultadas

- Ley 1581 de 2012 (Función Pública):
  <https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981> — enlace oficial; la
  descarga automática falló por certificado TLS, el texto no se citó literalmente.
- SIC, preguntas frecuentes de protección de datos (autorización previa, expresa e informada,
  obtenida por un medio consultable después): <https://www.sic.gov.co/preguntas-frecuentes-pdp>
- SIC, boletín jurídico: los avisos de privacidad no reemplazan la autorización previa, expresa
  e informada:
  <https://sedeelectronica.sic.gov.co/publicaciones/boletin-juridico/boletin/no-es-una-buena-practica-utilizar-mecanismos-para-que-tenga-el-mismo-efecto-que-la-persona-acepte-o-no-acepte>

De ahí salen tres reglas de diseño: (a) se pide la aceptación antes de guardar o procesar
(R4–R8); (b) la aceptación es una acción explícita del cliente, no silencio ni opción marcada
por defecto (R12–R14); (c) la prueba se puede consultar después (R9). Nada de esto sustituye la
revisión legal del dueño.

## 8. Trazabilidad diseño → requirements

| Pieza | R |
|---|---|
| `config.py` (orch) | R1–R3 |
| `_privacy_gate`, `privacy.py`, `process_message` | R4–R19 |
| `purge_personal_data` + endpoint (orch) | R20–R28 |
| `config.py` (hand) | R29–R31 |
| `purge_personal_data` + endpoint (hand) | R32–R40 |
| script | R41–R46 |
| Dockerfile, compose, `.env.example` | R47–R50 |
| contracts | R51, R52 |
