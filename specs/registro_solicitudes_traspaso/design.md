# Design — registro_solicitudes_traspaso

## Alcance

- Solo `services/handover/`. No se toca `contracts/`, ni `services/orchestrator/`, ni
  `docker-compose.yml`, ni `.env.example` (no hay variables nuevas).
- `POST /handover` sigue devolviendo exactamente lo mismo (`HandoverResponse` o el `500
  internal_error` de siempre) y los avisos a asesores no cambian (R14, R15).
- No se guarda ningún texto de mensajes (decisión del humano, Ley 1581): solo
  `messages_count` (R2, R19). El historial completo sigue viviendo en el orquestador.
- Fuera de alcance: rutas de consulta de registros, retención y borrado. Por eso el
  repositorio solo escribe registros; no hay método de lectura en Postgres.

## Estado actual del código (2026-11-01, tras #10, #13, #14 y #17)

El spec se escribió el 2026-10-31; desde entonces se cerraron la #10, #13, #14 y #17. Puntos
del código actual en los que se apoya este design (líneas del árbol de trabajo a esta fecha;
orientativas, el implementer debe localizar por nombre):

| Archivo | Estado actual relevante |
|---|---|
| `handover/config.py` | `parse_advisor_chat_ids(raw)` (l.17-37) devuelve los ids en orden, ignora entradas vacías y lanza `ValueError` ante una entrada no entera o repetida; `Settings._validate_advisor_chat_ids` (l.51-55) lo aplica al construir `Settings`, así que una lista inválida impide el arranque. `Settings.advisor_ids` (l.57-60) es una propiedad que vuelve a parsear (siempre válida). |
| `handover/domain.py` | `logger = logging.getLogger(__name__)` (l.28); `dataclass` y `Literal` ya importados (l.5, l.7). Modelos `Case`, `Notification`, `Denial` (l.62-88); `Adapters` (l.91-95). `open_case` (l.163-205) es el cuerpo que se mueve a `_process_handover`: `find_active_case` → `update_case`/`create_case` → bucle de `gateway.send` + `add_notification` por asesor (log `advisor_notice_failed` en `ERROR`) → `notified`, o `update_case(timed_out)` + `logger.warning("no_advisors …")` → `no_advisors`. La #14 añadió `authorize_case`, `assign_case`, `close_case`, `log_orphan_cases`, etc.; ninguna llama a `open_case`. |
| `handover/adapters/repository.py` | `CaseRepository` (l.15-38) incluye ya `add_denial`, `assign_if_unassigned`, `close_if_still_allowed` y `count_assigned_by_advisor` (#14). `FakeCaseRepository` (l.44-117) tiene `cases`, `notifications` y `denials`. `_SCHEMA` (l.120-132) tiene **3** sentencias: `handover_cases`, `handover_notifications`, `handover_denials`. `PostgresCaseRepository` (l.176-329): `self._lock = threading.Lock()` (l.183); `_connection()` (l.185-193) abre la conexión y ejecuta todo `_SCHEMA` en el primer uso; `_run(sql, params, fetch=False)` (l.195-206) toma `self._lock` alrededor de `_connection()` + `execute` + `fetchall` + `commit` (o `rollback` y relanza). El import de dominio es `from ..domain import Case, Denial, Notification` (l.12). |
| `handover/main.py` | `configure_logging()` (l.51-58), llamada al importar el módulo (l.156), pone el logger `handover` en `INFO` con un `StreamHandler` si no hay handlers. `create_app` registra `advisors_configured count=%d` al construirse (l.79-82) y el `lifespan` ejecuta `log_orphan_cases` (l.85-88). `post_handover` (l.133-135) es `def` síncrona (FastAPI la ejecuta en el threadpool) y llama a `open_case`. Handler genérico `Exception` → `logger.exception("Excepción no controlada")` + `500 internal_error` (l.124-127). |
| `tests/test_repository.py` | `_FakeConn(rows=...)` (l.34-47), helper `_statements(conn)` (~l.169-170, sentencias sin `CREATE`). Dos tests cuentan **3** `CREATE TABLE`: `test_postgres_repository_connects_lazily_and_once` (l.88-97) y `test_postgres_repository_connects_once_with_concurrent_first_use` (l.292-315). `test_postgres_repository_uses_parameters_only` (l.62-85) cuenta 6 sentencias no-`CREATE` y no se ve afectado. |
| `tests/conftest.py` | `START`, `ADVISORS = [111, 222, 333]`, `FakeClock`, `Env` (con `repo`, `gateway`, `clock`, `settings`, `adapters`, `handover(...)`), fixtures `env`, `env_factory`, `env_no_advisors`. El cliente de `make_env` no usa `with`, así que el `lifespan` no se ejecuta en esos tests. |

Consecuencias para este design:

- `handover_requests` es la **cuarta** sentencia de `_SCHEMA` (no la tercera) y los dos tests
  que hoy esperan 3 `CREATE TABLE` pasan a esperar 4.
- `add_request` y `complete_request` usan `_run` (una sentencia cada uno), así que quedan bajo
  el `threading.Lock` existente sin código nuevo de concurrencia. Ver «Concurrencia».
- `advisors_configured = len(settings.advisor_ids)` es exactamente el número de ids
  configurados (ver S5).
- Con `configure_logging()` los `INFO` del paquete ya llegan a la salida; el nivel `ERROR` de
  R20/R21 se mantiene por otro motivo (ver «Logs»).

## Coordinación con la #12 (`vencimiento_automatico`) y con la #14

La #12 (aún `spec_ready`) también modificará `handover/adapters/repository.py` y `domain.py`.
Esta feature es independiente de la #12 y **no invade su alcance**:

- No cambia la firma, el SQL ni el comportamiento de ningún método existente del repositorio
  (`find_active_case`, `create_case`, `update_case`, `get_case`, `list_open_cases`,
  `add_notification`, `add_denial`, `assign_if_unassigned`, `close_if_still_allowed`,
  `count_assigned_by_advisor`), ni `_connection`, ni `_run`, ni el `_lock`. Solo **añade**
  `add_request` y `complete_request` y una cuarta sentencia al final de `_SCHEMA`.
- En `domain.py`, `open_case` sigue haciendo las mismas llamadas a `update_case` en el mismo
  orden; solo se envuelve (ver «Flujo»). Si la #12 cambia esas llamadas, se integran dentro de
  `_process_handover` sin tocar el registro.
- Con la #14 (ya hecha): no se tocan `authorize_case`, `assign_case`, `close_case`,
  `log_orphan_cases` ni `handover_denials`. `FakeCaseRepository` gana la lista `requests`
  junto a `denials`.
- Puntos de posible conflicto de merge (textuales, no de diseño): la tupla `_SCHEMA` y el
  conteo de `CREATE TABLE` de los dos tests de `test_repository.py` citados arriba. Quien
  llegue segundo suma su tabla/sentencia a lo que haya.

## Tabla nueva

```sql
CREATE TABLE IF NOT EXISTS handover_requests (
  id                  BIGSERIAL PRIMARY KEY,   -- id propio del registro
  requested_case_id   TEXT        NOT NULL,    -- case_id de la petición
  case_id             TEXT        NULL,        -- caso efectivo (NULL hasta conocerlo)
  contact_id          TEXT        NOT NULL,
  reason              TEXT        NOT NULL,    -- motivo de ESTA petición
  received_at         TIMESTAMPTZ NOT NULL,    -- reloj inyectado
  result              TEXT        NOT NULL,    -- received | notified | no_advisors | error
  advisors_configured INTEGER     NOT NULL,
  notices_delivered   INTEGER     NOT NULL,
  messages_count      INTEGER     NOT NULL
)
```

Sin claves foráneas, `CHECK` ni índices, igual que `handover_notifications`. No existe
columna para texto de mensajes (R2).

## Ciclo del registro

```
recepción (solicitud válida) ──add_request──► result = received, case_id = NULL, delivered = 0
        │
        ├─ procesamiento OK ──complete_request──► notified | no_advisors, case_id, delivered
        │
        └─ excepción ─────────complete_request──► error, case_id (o NULL), delivered hasta ahí
                                                   y se relanza la excepción original
```

- Las peticiones con `401` o `422` nunca llegan a `open_case` (middleware y validación de
  FastAPI), así que no crean registro (R13). No hace falta código nuevo en `main.py`.
- `received` es el valor intermedio; solo queda persistido si el proceso muere entre las dos
  escrituras (ver supuesto S1).

## Archivos

| Archivo | Cambio |
|---|---|
| `services/handover/handover/domain.py` | `RequestResult`, `HandoverRequestRecord`, `_RequestTally`; `open_case` envuelve la lógica actual (movida a `_process_handover`) con el registro. |
| `services/handover/handover/adapters/repository.py` | Import `from ..domain import Case, Denial, HandoverRequestRecord, Notification, RequestResult`; `CaseRepository` + `add_request` / `complete_request`; implementación en `FakeCaseRepository` (lista `requests`) y `PostgresCaseRepository` (vía `_run`); cuarta sentencia al final de `_SCHEMA`. |
| `services/handover/tests/test_requests.py` | **Nuevo.** Tests de dominio/HTTP de R1-R15 y R18-R21. |
| `services/handover/tests/test_repository.py` | Tests nuevos de Postgres (R16, R17) y actualizar el conteo de `CREATE TABLE` de 3 a 4 en `test_postgres_repository_connects_lazily_and_once` y en `test_postgres_repository_connects_once_with_concurrent_first_use`. |

`main.py`, `config.py`, `gateway.py`, `tests/fakes.py` y `tests/conftest.py` no cambian
(`FakeCaseRepository` ya se reexporta; el fixture `env` ya da acceso a `env.repo`,
`env.settings` y `env.adapters`).

## Firmas nuevas

```python
# domain.py
RequestResult = Literal["received", "notified", "no_advisors", "error"]

class HandoverRequestRecord(BaseModel):
    request_id: int | None = None      # lo asigna el repositorio
    requested_case_id: str
    case_id: str | None = None
    contact_id: str
    reason: str
    received_at: datetime
    result: RequestResult
    advisors_configured: int
    notices_delivered: int
    messages_count: int

@dataclass
class _RequestTally:                   # progreso para poder registrar un error (R8)
    case_id: str | None = None
    delivered: int = 0

def open_case(req: HandoverRequest, settings: Settings, adapters: Adapters) -> HandoverResponse
    # firma sin cambios
def _process_handover(req: HandoverRequest, settings: Settings, adapters: Adapters,
                      tally: _RequestTally) -> HandoverResponse
    # cuerpo actual de open_case; además fija tally.case_id cuando conoce el caso y suma
    # tally.delivered tras cada gateway.send con éxito (antes de add_notification)

# adapters/repository.py
class CaseRepository(Protocol):
    ...  # métodos existentes sin cambios
    def add_request(self, record: HandoverRequestRecord) -> int: ...   # devuelve el id
    def complete_request(self, request_id: int, case_id: str | None,
                         result: RequestResult, notices_delivered: int) -> None: ...
```

`FakeCaseRepository`:
- `self.requests: list[HandoverRequestRecord] = []`.
- `add_request` asigna `request_id = len(self.requests) + 1`, guarda una copia y devuelve el id.
- `complete_request` sustituye el registro de ese id por una copia con `case_id`, `result` y
  `notices_delivered` actualizados.

`PostgresCaseRepository` (mismo `_run`, siempre `%s`):
- `add_request`: `INSERT INTO handover_requests (requested_case_id, case_id, contact_id,
  reason, received_at, result, advisors_configured, notices_delivered, messages_count)
  VALUES (%s × 9) RETURNING id` con una sola llamada `self._run(..., fetch=True)`; devuelve
  `int(rows[0][0])`.
- `complete_request`: una sola llamada `self._run("UPDATE handover_requests SET case_id = %s,
  result = %s, notices_delivered = %s WHERE id = %s", (...))`.

### Concurrencia

- `post_handover` es síncrona y FastAPI la ejecuta en el threadpool, así que puede haber
  varias `open_case` a la vez. El dominio no comparte estado: `request_id` y `_RequestTally`
  son locales a cada llamada.
- En Postgres, `add_request` y `complete_request` pasan por `_run`, que ya toma
  `self._lock` (`threading.Lock`, **no reentrante**) alrededor de `_connection()` + `execute`
  + `fetchall` + `commit`. El `INSERT … RETURNING id` y la lectura del id ocurren dentro del
  mismo bloqueo, así que cada hilo recibe su id. Si `add_request` es la primera sentencia del
  proceso, crea el esquema (las 4 tablas) bajo el mismo bloqueo, como ya hace cualquier otro
  método (R45 de la #14).
- Regla para el implementer: los dos métodos nuevos llaman a `_run` **una vez** y nunca desde
  dentro de otro `_run` ni con `self._lock` tomado (un `Lock` no reentrante se bloquearía).
  No se añade ningún lock nuevo.
- El registro y las escrituras del caso son sentencias separadas (cada `_run` hace su
  `commit`), como el resto de handover; no hay transacción que las agrupe.
- `FakeCaseRepository` no es seguro entre hilos (`len(self.requests) + 1`), igual que el resto
  del fake: solo se usa en tests de un hilo.

## Flujo de `open_case`

```python
def open_case(req, settings, adapters):
    repo = adapters.repository
    request_id = _start_request(req, settings, adapters)        # None si add_request falla (R10)
    tally = _RequestTally()
    try:
        response = _process_handover(req, settings, adapters, tally)
    except Exception:
        logger.error("handover_request_failed request_id=%s case_id=%s",
                     request_id, tally.case_id)                  # R21
        _finish_request(repo, request_id, tally.case_id, "error", tally.delivered)  # R8, R12
        raise                                                    # R9: excepción original
    _finish_request(repo, request_id, response.case_id, response.status, tally.delivered)  # R3-R5, R11
    return response
```

- `_start_request` construye el `HandoverRequestRecord` (R1: `received_at = adapters.clock()`,
  `advisors_configured = len(settings.advisor_ids)`; R19: `messages_count =
  len(req.last_messages)`) y llama a `repo.add_request`. Si lanza cualquier excepción, emite
  `handover_request_not_recorded` (`ERROR`, R20) y devuelve `None`.
- `_finish_request` no hace nada si `request_id is None`; si `complete_request` lanza, emite
  `handover_request_update_failed` (`ERROR`, R20) y **no** relanza (R11, R12). Así el registro nunca cambia la respuesta ni
  sustituye la excepción original.
- `_process_handover` es el cuerpo actual de `open_case` (`domain.py` l.164-205) sin cambios
  de comportamiento (R7, R14, R15): mismo aviso (`build_advisor_notice`), mismas
  notificaciones, mismo log `advisor_notice_failed`, mismo paso a `timed_out` y mismo
  `logger.warning("no_advisors case_id=%s")`, `Case.reason` intacto al reutilizar. Solo se
  añaden `tally.case_id = case.case_id` justo después de `update_case`/`create_case` y
  `tally.delivered += 1` justo después de un `gateway.send` con éxito (antes de
  `add_notification`).
- Base de datos caída: `add_request` falla primero (en `_connection()`), se emite
  `handover_request_not_recorded` y `request_id = None`; después `find_active_case` falla
  igual que hoy → `handover_request_failed request_id=None case_id=None`, `_finish_request`
  no hace nada y se relanza → `500 internal_error`, la misma respuesta que antes de esta
  feature (R9, R10).

### Logs (R18, R20, R21)

Solo identificadores y nombres de excepción, nunca texto de clientes (R18). Todos con
`logger.error` del logger de `domain.py` (nivel `ERROR`), sin `exc_info`:

| Código | Nivel | Cuándo | Requirement |
|---|---|---|---|
| `handover_request_not_recorded code=<TipoExcepcion>` | `ERROR` | falla `add_request` | R20 |
| `handover_request_update_failed request_id=<id> code=<TipoExcepcion>` | `ERROR` | falla `complete_request` | R20 |
| `handover_request_failed request_id=<id> case_id=<id\|None>` | `ERROR` | error interno en `_process_handover` | R21 |

- `handover_request_not_recorded` y `handover_request_update_failed` son `ERROR` porque, con
  S2, son la **única huella** de un hueco de auditoría (solicitud sin registro o registro
  atascado en `received`). Desde la #10, `configure_logging()` (`main.py` l.51-58) hace
  visibles los `INFO` del paquete `handover`, así que el motivo ya no es la visibilidad sino
  la gravedad: un hueco de auditoría es un fallo que hay que vigilar, al mismo nivel que
  `advisor_notice_failed`, y no debe confundirse con los `INFO` de arranque
  (`advisors_configured`, `orphan_cases`).
- `handover_request_failed` también es `ERROR`: acompaña a un `500` y enlaza el id del
  registro `error` con la traza que sigue registrando el handler genérico de `main.py`
  (`logger.exception`, como hoy). Mismo nivel que los errores existentes del servicio
  (`gateway_error`, `timeout_reply_failed`). Se emite antes de `_finish_request`, así que
  aparece aunque `complete_request` falle después. Si `request_id` es `None` (falló
  `add_request`), se emite igual con `request_id=None`.
- Sin `exc_info`: el mensaje de la excepción podría contener datos; la traza completa ya la
  deja el handler de `main.py` para el error interno.

## Cómo se prueban los errores con fakes

Sin tocar los fakes: los tests sustituyen métodos de la instancia `env.repo`
(`FakeCaseRepository`) con `monkeypatch.setattr(env.repo, "<método>", boom)`, donde `boom`
lanza `RuntimeError("fallo-simulado")`.

| Caso | Método sustituido | Cómo se observa |
|---|---|---|
| Error antes de conocer el caso (R8) | `find_active_case` | `env.repo.requests[0]`: `result="error"`, `case_id=None`, `notices_delivered=0` |
| Error tras un aviso entregado (R8) | `add_notification` | `result="error"`, `case_id="case-1"`, `notices_delivered=1` (el `send` ya tuvo éxito) |
| 500 sin cambios (R9) | `find_active_case` | `TestClient(create_app(env.settings, env.adapters), raise_server_exceptions=False)` → `500`, `error == "internal_error"` |
| Falla crear el registro (R10) | `add_request` | respuesta `notified` idéntica, `env.repo.requests == []` |
| Falla completar tras éxito (R11) | `complete_request` | respuesta `notified` idéntica, registro sigue en `received` |
| Falla completar tras error (R12) | `find_active_case` y `complete_request` | llamada directa a `open_case(...)` con `pytest.raises(RuntimeError, match="fallo-simulado")` (la de `complete_request` lanza `OSError`) |
| Registro creado al recibir (R1) | `find_active_case` envuelto con un espía | el espía copia `env.repo.requests` en el momento de la llamada: hay un registro `received`, `case_id=None`, `notices_delivered=0` |

En los casos que lanzan excepción (R8, R12, R18), como el cliente del fixture `env` relanza
las excepciones del servidor, se usa `pytest.raises(RuntimeError)` alrededor de
`env.handover(...)` o un cliente con `raise_server_exceptions=False`.

R18, R20 y R21 se comprueban con `caplog` (`caplog.set_level(logging.DEBUG)`) en los
escenarios de R8, R10 y R11, enviando un `last_messages` con un texto marcador
(`"TEXTO-CLIENTE-SECRETO"`): el marcador no debe aparecer en `caplog.text` (R18), y el
`LogRecord` cuyo mensaje empieza por cada código del design debe existir y tener
`levelno == logging.ERROR` (R20, R21). (El logger `handover` queda en `INFO` por
`configure_logging()`, así que `caplog.set_level(logging.DEBUG)` no hace aparecer `DEBUG` del
paquete; no importa, los tres códigos son `ERROR` y el marcador se busca en todo lo emitido.)

## Excepciones

No se añaden excepciones nuevas. Se reutiliza el handler genérico de `Exception` de
`main.py` (`500 internal_error`). `open_case` captura `Exception` solo para registrar el
`error` y la relanza.

## Alternativas descartadas

- **Un solo `INSERT` al final (en `finally`) con el resultado ya conocido.** Más simple, pero
  si el proceso muere durante los avisos (hasta `HTTP_TIMEOUT_SECONDS` por asesor) no queda
  ninguna huella de la solicitud, y el acceptance pide crear el registro al recibirla.
  Con dos fases, un registro que queda en `received` delata una solicitud interrumpida.
- **Reutilizar `handover_notifications` (una fila extra por solicitud) o añadir columnas a
  `handover_cases`.** Sin asesores no hay notificaciones, y un caso reutilizado tiene una sola
  fila: justo los dos huecos que motivan la feature. Además mezclaría conceptos distintos.
- **Copiar `last_messages` en el registro.** Descartada por el humano (2026-10-31, Ley 1581):
  solo `messages_count`.
- **Id generado en el dominio con `uuid4`.** Haría los tests no deterministas o exigiría
  inyectar un generador; `BIGSERIAL` + `RETURNING id` es coherente con
  `handover_notifications`.
- **Registrar desde un middleware de `main.py`.** El middleware no conoce el caso efectivo ni
  los avisos entregados sin duplicar lógica de dominio, y rompería la separación de capas.

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar (revisión humana)

Ninguno está decidido en el acceptance ni en `progress/propuesta_etapa2.md` §6; son la
propuesta de este spec. Los marcados **REVISAR (pendiente del humano)** son las «Decisiones
para el humano» de `progress/specreview_registro_solicitudes_traspaso.md`: este spec no las
decide; da su recomendación y el humano debe confirmarlas o cambiarlas.

| Id | Supuesto (propuesta del spec) | Alternativa | Recomendación |
|---|---|---|---|
| **S1 — REVISAR (pendiente del humano)** | Valor intermedio `received` mientras se procesa (dos escrituras: `INSERT` + `UPDATE`); queda así solo si el proceso muere entre las dos escrituras o si falla `complete_request`. | Sin valor intermedio: un solo `INSERT` al final. | Mantener `received`: es la única forma de que una solicitud interrumpida deje huella. |
| **S2 — REVISAR (pendiente del humano)** | Si no se puede crear o completar el registro, el traspaso sigue y la respuesta no cambia (R10, R11): prima atender al cliente sobre la auditoría; queda una línea de log `ERROR` (R20). | Registro obligatorio: si `add_request` falla, `POST /handover` responde `500` y no se avisa a nadie. | Mantener S2 (el traspaso sigue). Nota: no cubre un fallo del propio `CREATE TABLE handover_requests`, porque `_connection()` (`repository.py` l.185-193) ejecuta todo `_SCHEMA` de una vez y no guarda la conexión si alguna sentencia falla; si esa sentencia falla, falla todo handover (cada método reintentaría abrir la conexión). |
| **S3 — REVISAR (pendiente del humano)** | En `error`, `notices_delivered` cuenta los `send` con éxito antes del fallo (aunque su `add_notification` haya fallado). | Dejar `0` en todo registro `error`. | Mantener el conteo real: refleja a qué asesores sí llegó el aviso. |
| **S4 — REVISAR (pendiente del humano)** | No se guarda fecha de finalización (`completed_at`): el acceptance solo pide la de recepción. | Añadir `completed_at TIMESTAMPTZ NULL` con el reloj inyectado. | No añadirla ahora (no la pide el acceptance); se puede sumar en una feature posterior. |
| **S5** | `advisors_configured = len(settings.advisor_ids)`. La #10 ya está hecha: `parse_advisor_chat_ids` (`config.py` l.17-37) no descarta entradas no numéricas ni repetidas (lanzan `ValueError` y `Settings` no se construye, así que el servicio no arranca) y solo ignora las vacías (`"111,,222"` → 2 ids). `advisors_configured` es exactamente el número de ids configurados, el mismo valor que `create_app` registra al arrancar (`advisors_configured count=%d`, `main.py` l.79-80). | Contar las entradas crudas de la variable (diferiría solo por entradas vacías). | — (ajustado según el spec review; no es decisión pendiente). |
| **S6 — REVISAR (pendiente del humano)** | Reintentos del orquestador con el mismo `case_id` crean registros distintos (no hay deduplicación): cada `POST /handover` válido es una solicitud. | Deduplicar por `requested_case_id`. | Sin deduplicación: coherente con «cada `POST /handover` válido» y deja ver los reintentos. |
| **S7** | `reason` se guarda (es una etiqueta cerrada de `HandoverReason`, no texto del cliente). | — | — (lo pide A1). |
| **Retención — REVISAR (pendiente del humano)** | La tabla guarda `contact_id` y `reason` sin límite de tiempo; retención y borrado quedan fuera de alcance por el acceptance. | Incluir una política de retención en esta feature. | Mantener fuera de alcance, pero abrir una feature de retención (Ley 1581) antes de producción. |
