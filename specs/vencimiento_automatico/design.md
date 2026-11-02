# Design — vencimiento_automatico

## Alcance

- Script `scripts/vencer_casos.py` (llamada única o bucle) y servicio `timeouts_worker` en
  `docker-compose.yml` que lo ejecuta en bucle.
- Handover: el paso `open` → `timed_out` y la reutilización de un caso dejan de reescribir el caso
  entero; pasan a escrituras condicionales o parciales.
- **No** cambia contratos (`POST /cases/check-timeouts` ya existe y su respuesta no cambia).
- **No** diseña ningún despliegue: cómo se ejecuta en Render queda PENDIENTE (decisión del humano
  2026-10-31). No se tocan `.github/` ni `render.yaml` (no existe).

## Mapa de acceptance → requirements

| Acceptance de `feature_list.json` | R |
|---|---|
| Script de llamada única con códigos de salida | R1-R5 |
| `--intervalo` (por defecto `CHECK_TIMEOUTS_INTERVAL_SECONDS`); fallo registrado y el bucle sigue | R6, R7, R8, R9, R10, R30 |
| El token nunca en log ni salida | R11 |
| `timeouts_worker` en compose sin puertos; variables en `.env.example` | R13, R14, R15, R16 |
| `open` → `timed_out` condicional; no se pierde la asignación | R17, R19, R20, R21, R22, R27 |
| Dos ejecuciones simultáneas no envían dos veces | R17, R18, R24, R27, R28 |
| Reutilización simultánea con asignación no la deshace | R25, R26 |
| Decidido: intervalo inicial 60 s configurable | R7, R16 |
| Decidido: Render pendiente; no se despliega | este documento (sin tareas de despliegue) |
| Tests pedidos | ver tasks.md |

R12 no sale de un criterio literal: es necesaria porque una llamada a `check-timeouts` puede
tardar varios envíos al gateway (hasta `HTTP_TIMEOUT_SECONDS` cada uno) y la configuración solo se
lee de variables de entorno (`docs/architecture.md` §3.5). R29 (valor inválido de esa variable)
y R30 (la llamada única no valida el intervalo) completan su comportamiento para que no quede
nada en el design sin requirement. Ver «Decisiones pendientes del humano» (D3).

## Precondición de orden (10 → 11 → 14 → 12)

Esta feature se implementa **después** de la #10 (`validacion_config_asesores`), de la #11
(`registro_solicitudes_traspaso`) y de la #14 (`autorizacion_asesores`), las tres `done`. Todo
este design describe el código tal como lo deja la #14:
- `open_case` es el envoltorio del registro de solicitudes (`_start_request` /
  `_finish_request`) y la lógica de reutilización y de la rama `no_advisors` vive en
  `_process_handover(req, settings, adapters, tally)` (#11). Sus dos escrituras con
  `update_case` (reutilización y `no_advisors`) siguen ahí y son las que cambia la #12, junto con
  la de `check_timeouts`.
- `assign_case(case_id, advisor_id, settings, adapters)` y `close_case(case_id, advisor_id,
  settings, adapters)` (#14) ya no usan `update_case`: escriben con
  `assign_if_unassigned`/`close_if_still_allowed` (escrituras condicionales) y rechazan con
  `_deny` → `AdvisorForbidden` (`403`) a un asesor que no esté en `ADVISOR_CHAT_IDS`.
- `PostgresCaseRepository._run` toma un `threading.Lock` (`self._lock`, #14): las sentencias de
  la conexión compartida quedan serializadas dentro del proceso.
- `_SCHEMA` tiene cuatro `CREATE TABLE` (`handover_cases`, `handover_notifications`,
  `handover_denials` de la #14, `handover_requests`) y
  `test_postgres_repository_connects_lazily_and_once` cuenta 4.

Si al empezar la #12 alguna de la #10, #11 o #14 no está `done`, el implementer para y lo
reporta; no reimplementa nada de ellas.

## Archivos

### Nuevos
- `scripts/vencer_casos.py` — script (mismo estilo que `scripts/cargar_manual.py`: `main(argv,
  client)` inyectable, `httpx`, sin dependencias de `lazaro_contracts`).
- `services/handover/tests/test_vencer_casos.py` — tests del script. Siguen el modelo de
  `services/rag/tests/test_cargar_manual.py` (los tests del script viven en el servicio al que
  llama; se carga con `importlib.util.spec_from_file_location`). No se crea `scripts/tests/`.
- `services/handover/tests/test_timeout_races.py` — carreras con repositorio falso.
- `services/handover/tests/test_worker_compose.py` — compose, Dockerfile y `.env.example`.

### Modificados
- `services/handover/handover/adapters/repository.py` — métodos nuevos en `CaseRepository`,
  `FakeCaseRepository` y `PostgresCaseRepository`; columna nueva en el esquema.
- `services/handover/handover/domain.py` — `_process_handover` (creado por la #11) y
  `check_timeouts` usan los métodos nuevos. `open_case` (envoltorio del registro de la #11) no
  cambia.
- `services/handover/Dockerfile` — una línea `COPY scripts/vencer_casos.py ./vencer_casos.py`.
- `docker-compose.yml` — servicio `timeouts_worker`.
- `.env.example` — `CHECK_TIMEOUTS_INTERVAL_SECONDS=60`, `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`.
- `services/handover/tests/test_repository.py` — cambio acotado del test de la #7
  `test_postgres_repository_uses_parameters_only` (detalle exacto en «Supuestos a confirmar»,
  S1) y tests nuevos T5-T7.

No se tocan `main.py`, `config.py` de handover, `assign_case`/`close_case` ni sus métodos
`assign_if_unassigned`/`close_if_still_allowed` (de la #14).

`services/handover/tests/conftest.py` **no se modifica**: `make_env(advisors=None, repo=None,
gateway=None)` y el fixture `env_factory` ya existen (#14) y bastan para inyectar las subclases
de prueba del repositorio y del gateway.

## Script `scripts/vencer_casos.py`

```python
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_HTTP_TIMEOUT_SECONDS = 120
CHECK_TIMEOUTS_PATH = "/cases/check-timeouts"

logger = logging.getLogger("vencer_casos")

def main(
    argv: list[str] | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_rounds: int | None = None,
) -> int: ...

def _call_once(http: httpx.Client, url: str, token: str, timeout: float) -> bool: ...
```

- `argparse`: `--intervalo` con `nargs="?"`, `const=<sentinela>`, `default=None`.
  - Sin la opción → llamada única (R1-R4): `return 0 if ok else 1`.
  - `--intervalo` sin valor → `CHECK_TIMEOUTS_INTERVAL_SECONDS` o 60 (R7).
  - `--intervalo 30` → 30. Se acepta `float`.
  - Solo en modo bucle se resuelve y valida el intervalo: si es no numérico o ≤ 0 →
    `parser.error(...)` (salida 2) antes de cualquier petición (R8). Con `--intervalo 30` la
    variable `CHECK_TIMEOUTS_INTERVAL_SECONDS` no se lee.
  - En llamada única `CHECK_TIMEOUTS_INTERVAL_SECONDS` **no se lee**: un valor inválido no
    afecta (R30; p. ej. un futuro Cron Job con la variable mal puesta sigue funcionando).
- `HANDOVER_URL` y `SERVICE_TOKEN` se leen de `os.environ`; si falta alguna → log de error con el
  **nombre** de la variable, `return 1`, sin peticiones (R5).
- `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` (por defecto 120) se pasa como `timeout=` en cada
  `http.post(...)`, no al construir el cliente, para que también aplique con un cliente inyectado
  y sea verificable en `request.extensions["timeout"]` con `httpx.MockTransport` (R12). Se valida
  en ambos modos, antes de cualquier petición: si está definida y no es un número mayor que 0 →
  log de error con el **nombre** de la variable (no su valor) y `return 2`, sin peticiones (R29).
- Orden de validación (todo antes de la primera petición): argumentos e intervalo (solo bucle,
  R8) → `HANDOVER_URL`/`SERVICE_TOKEN` (R5) → `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` (R29).
- `_call_once`: `POST {HANDOVER_URL.rstrip('/')}/cases/check-timeouts`, `json={}`,
  `headers={"X-Service-Token": token}`.
  - `200` → `logger.info("check_timeouts_ok timed_out=%s", n)` con `n = len(timed_out_cases)`
    si el cuerpo lo permite (si no, `?`); devuelve `True`.
  - Otro código → `logger.error("check_timeouts_failed status=%s error=%s", code, error)`, donde
    `error` es el campo `error` del cuerpo JSON (`unauthorized`, `internal_error`…) o
    `http_<code>`; nunca el cuerpo completo (R9).
  - `httpx.HTTPError` → `logger.error("check_timeouts_failed error=%s", type(exc).__name__)`.
    Solo el nombre de la clase, nunca `str(exc)` (R9, R11).
- Bucle (R6, R10): `rounds = 0; while True: _call_once(...) envuelto en try/except Exception
  (log del nombre de la clase); rounds += 1; if max_rounds is not None and rounds >= max_rounds:
  return 0; sleep(interval)`. Es decir: con `max_rounds=N` hace N llamadas y N-1 esperas. En
  producción `max_rounds` es `None` y el proceso solo termina por señal (Docker envía `SIGTERM`).
  El intervalo se cuenta **después** de cada llamada, no a ritmo fijo: el periodo real es
  intervalo + duración de la llamada.
- Logs: `logging` (nunca `print`, `docs/architecture.md` §6). En `if __name__ == "__main__":`
  `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")` y
  `sys.exit(main())`. Ningún mensaje interpola el token, los encabezados ni la petición (R11).
- Sin `lazaro_contracts`: el cuerpo es `{}` literal y el encabezado `"X-Service-Token"`; así el
  script corre igual en el contenedor, en local o en un futuro cron sin instalar el paquete de
  contratos.

## Docker Compose (justificación del proceso nuevo, `docs/architecture.md` §1)

```yaml
  timeouts_worker:
    build: {context: ., dockerfile: services/handover/Dockerfile}
    env_file: [.env]
    command: ["python", "vencer_casos.py", "--intervalo"]
    depends_on: [handover]
    restart: unless-stopped
```

Justificación de añadir un proceso a Compose:
1. La feature #12 lo pide de forma explícita («`docker-compose.yml` incluye un servicio
   `timeouts_worker`»), y `CONTRATOS.md` ya dice que la ruta la llama «worker o cron».
2. No es un servicio HTTP nuevo ni una capa nueva: no expone rutas, no publica puertos (R14), no
   tiene paquete propio ni base de datos; solo llama a una ruta interna existente con
   `X-Service-Token` (principios 1 y 8).
3. Un bucle dentro de handover no sirve (decisión del humano): el plan gratuito de Render duerme
   el servicio. Un proceso aparte que solo hace HTTP se puede trasladar tal cual a cualquiera de
   las opciones pendientes (Render Cron Job con llamada única, worker o GitHub Actions
   `schedule`): por eso el script admite llamada única y bucle.
4. No crea imagen nueva: reutiliza la de handover (Python 3.12 + `httpx`, usuario sin
   privilegios), a la que solo se añade una línea `COPY` (R15). El `CMD` de handover no cambia;
   compose lo sustituye con `command`.

`restart: unless-stopped`: el bucle ya sobrevive a los fallos de cada llamada (R10); el reinicio
cubre solo una salida inesperada del proceso. Con una configuración inválida (R5, R8, R29) el
contenedor se reiniciaría en bucle dejando el error en el log de cada arranque; se considera
aceptable en local. Ver D5 en «Decisiones pendientes del humano».

## Handover: transiciones condicionales

### El problema (hallazgo)
`update_case` reescribe todos los campos con `WHERE case_id = %s`. `check_timeouts` lee los casos
`open`, envía (hasta `HTTP_TIMEOUT_SECONDS`) y escribe el caso entero con `timed_out`: una
asignación hecha durante el envío se pierde (estado y `advisor_id`). `_process_handover` (antes
de la #11, `open_case`) lee el caso activo, y al reutilizarlo reescribe el caso entero con `last_messages` nuevos: una asignación
hecha entre la lectura y la escritura vuelve a `open`. Y dos ejecuciones de `check-timeouts`
leen el mismo caso `open` y envían las dos.

### Firmas nuevas (`adapters/repository.py`)

```python
class CaseRepository(Protocol):
    # ... métodos existentes sin cambios (incluido update_case) ...
    def claim_timeout(self, case_id: str, now: datetime, stale_before: datetime) -> bool: ...
    def release_timeout_claim(self, case_id: str) -> None: ...
    def mark_timed_out(self, case_id: str) -> bool: ...
    def update_last_messages(self, case_id: str, last_messages: list[LastMessage]) -> None: ...
```

| Método | Efecto | Postgres (una sentencia, `%s`) |
|---|---|---|
| `claim_timeout` | Si el caso está `open` y su reclamación es `NULL` o `<= stale_before`, la fija a `now` y devuelve `True`; si no, `False` sin cambiar nada | `UPDATE handover_cases SET timeout_claimed_at = %s WHERE case_id = %s AND status = %s AND (timeout_claimed_at IS NULL OR timeout_claimed_at <= %s) RETURNING case_id` |
| `release_timeout_claim` | Pone la reclamación a `NULL` solo si el caso sigue `open` | `UPDATE handover_cases SET timeout_claimed_at = NULL WHERE case_id = %s AND status = %s` |
| `mark_timed_out` | Si el caso está `open`, lo pasa a `timed_out`, borra la reclamación y devuelve `True`; si no, `False` | `UPDATE handover_cases SET status = %s, timeout_claimed_at = NULL WHERE case_id = %s AND status = %s RETURNING case_id` |
| `update_last_messages` | Escribe solo `last_messages` | `UPDATE handover_cases SET last_messages = CAST(%s AS JSONB) WHERE case_id = %s` |

- Se usa `RETURNING case_id` + `fetch=True` del `_run` existente para saber si la fila cambió
  (filas devueltas no vacías), en lugar de `cursor.rowcount`: funciona igual con pg8000 y con la
  conexión falsa de `test_repository.py`.
- En Postgres cada `UPDATE` con la condición en el `WHERE` es atómico por fila **entre
  conexiones distintas**: con dos transacciones concurrentes en conexiones distintas, la segunda
  espera el bloqueo de fila, reevalúa el `WHERE` sobre la versión confirmada (READ COMMITTED) y
  no cambia nada. Eso es lo que garantiza R17/R18 en la base real cuando las ejecuciones usan
  conexiones distintas (p. ej. dos procesos de handover). Dentro de un mismo proceso,
  `PostgresCaseRepository` comparte una sola conexión pg8000 entre los hilos de FastAPI, pero
  `_run` ya la serializa con `self._lock` (#14): cada `UPDATE` condicional se ejecuta entero
  antes que la siguiente sentencia, así que la condición del `WHERE` también decide entre
  peticiones del mismo proceso (riesgo (f), resuelto por la #14). Los métodos nuevos usan `_run`
  y no añaden ni cambian el candado. El repositorio falso reproduce la atomicidad porque cada
  método comprueba y escribe sin ceder el control.
- Esquema (R28): se añade a `_SCHEMA`, tras los `CREATE TABLE`,
  `ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS timeout_claimed_at TIMESTAMPTZ NULL`
  (las bases creadas por la #7 ya tienen la tabla; `CREATE TABLE IF NOT EXISTS` no añadiría la
  columna). La columna **no** entra en `_CASE_COLUMNS` ni en `Case`: es un detalle de
  coordinación interno del repositorio, `_row_to_case` y los tests de filas de la #7 no cambian, y
  `update_case` no la toca.
- `FakeCaseRepository`: atributo nuevo `timeout_claims: dict[str, datetime]` con la misma
  semántica; `cases` no cambia de forma (los tests de la #7 que comparan `env.repo.cases` siguen
  válidos).
- `update_case` **se mantiene** en el `Protocol` y en las dos implementaciones: lo usa el test
  de la #7 `test_postgres_repository_uses_parameters_only` (`test_repository.py`, l.68) y
  quitarlo no lo pide el acceptance. Tras la #12 queda sin uso en `domain.py` (la #14 ya lo quitó
  de `assign_case`/`close_case` y la #12 lo quita de `_process_handover` y `check_timeouts`).

### `check_timeouts` (domain.py)

```python
now = adapters.clock()
stale_before = now - timedelta(seconds=settings.handover_timeout_seconds)
for case in repo.list_open_cases():
    if no vencido: continue
    if not repo.claim_timeout(case.case_id, now, stale_before):   # R17, R18, R19, R24
        continue
    try:
        adapters.gateway.send(case.chat_id, settings.handover_timeout_reply)
    except ServiceUnavailable:
        logger.error("timeout_reply_failed case_id=%s", case.case_id)
        repo.release_timeout_claim(case.case_id)                  # R23
        continue
    if repo.mark_timed_out(case.case_id):                         # R20
        timed_out.append(case.case_id)
    else:
        logger.warning("timeout_superseded case_id=%s", case.case_id)  # R21, R22
```

### Cómo encaja «si el envío falla, el caso queda `open`» (#7 R19) con «nunca dos envíos»

Se eligió **reclamar antes de enviar, sin cambiar el estado**:
- Durante el envío el caso sigue `open`: `find_active_case` lo sigue encontrando (una
  reutilización simultánea no crea un caso duplicado) y `assign_case` lo puede asignar.
- Una segunda ejecución ve el caso `open` pero no obtiene la reclamación vigente → no envía (R18).
- Si el envío falla se libera la reclamación (R23): el caso queda `open` y sin marca, exactamente
  como pide R19 de la #7, y la siguiente llamada lo reintenta de inmediato (el test existente
  `test_check_timeouts_send_failure_keeps_case_open` sigue pasando sin cambios).
- Si el proceso muere entre reclamar y marcar, la reclamación caduca a los
  `HANDOVER_TIMEOUT_SECONDS` y otra ejecución la retoma (R24). Ese caso extremo (y el de un envío
  que el gateway entregó pero respondió con error, que ya existía en la #7) puede producir un
  segundo aviso: se prefiere «al menos una vez» a que un cliente no reciba nunca el aviso. Entre
  ejecuciones sanas y simultáneas la garantía es «como mucho una vez».
- Si el caso se asigna o se cierra durante el envío, el cliente ya recibió el aviso de espera (no
  se puede deshacer), pero `mark_timed_out` no encuentra el caso `open` y no lo toca (R21) ni lo
  lista (R22).

### `_process_handover` (domain.py, tal como lo deja la #11)

- Reutilización: `repo.update_last_messages(case.case_id, list(req.last_messages))` en lugar de
  `update_case(...)` (R25). El `case` leído se sigue usando solo para `case_id` y para el
  `status` de la rama sin asesores. `Case.reason` queda intacto al reutilizar, como exige la #11.
- Rama `no_advisors` (R10 de la #7): `if case.status == "open": repo.mark_timed_out(case.case_id)`
  en lugar de `update_case(...)` (R26). Si el caso se asignó entre la lectura y esta escritura,
  `mark_timed_out` devuelve `False` y no cambia nada. La respuesta sigue siendo `no_advisors`.
- No se toca nada del registro de la #11: `open_case`, `_start_request`, `_finish_request` y el
  uso de `tally` (`tally.case_id` al conocer el caso, `tally.delivered` tras cada `send`) quedan
  igual. Solo cambian las dos llamadas a `update_case` del cuerpo de `_process_handover`.
- La respuesta de `POST /handover`, los avisos y los registros de `handover_requests` no cambian.

## Cómo se prueban las carreras (sin hilos, deterministas)

Las carreras se reproducen intercalando la operación rival en el punto exacto de la ventana, con
subclases de prueba definidas en `test_timeout_races.py` e inyectadas con el `make_env(repo=...,
gateway=...)` existente de `conftest.py` (o el fixture `env_factory`, que lo devuelve); ninguno
se modifica:

- `HookGateway(FakeGatewayClient)`: ejecuta un `on_send` una sola vez dentro de `send`, antes de
  registrar el envío. Sirve para «asignación durante el envío» (llama a
  `domain.assign_case(case_id, "222", env.settings, env.adapters)`), «cierre durante el envío»
  (`domain.close_case(case_id, "222", env.settings, env.adapters)`) y «dos vencimientos
  simultáneos» (llama a `domain.check_timeouts(env.settings, env.adapters)` anidado: la segunda
  ejecución ocurre mientras la primera tiene la reclamación y aún no ha marcado).
- `HookRepository(FakeCaseRepository)`: ejecuta un `after_list` tras `list_open_cases` (asignar
  o cerrar entre la lectura y la reclamación, R19) y un `after_find` tras `find_active_case`
  (asignar entre la lectura y la escritura de la reutilización, R25, R26).
- Toda llamada a `assign_case`/`close_case` lleva la firma completa de la #14 (`case_id,
  advisor_id, env.settings, env.adapters`) y un asesor de `ADVISORS` (`111`, `222` o `333`); con
  otro asesor `is_registered_advisor` es falso y `_deny` lanza `AdvisorForbidden`. Se usa `"222"`.
- Rama `no_advisors` (T21, R26): `make_env(advisors=[], repo=HookRepository(...))`, y el
  `after_find` asigna **directamente con el repositorio**:
  `repo.assign_if_unassigned(case_id, "222", env.clock())`. No se usa `assign_case`, porque con
  `advisors=[]` el `222` no está registrado y fallaría con `403`. Así no hay ningún aviso
  entregado (no hay asesores) y la respuesta llega a `no_advisors` sin gateway especial.
- Con esto la T7b de `specs/autorizacion_asesores/tasks.md` (pasar `settings` a
  `assign_case`/`close_case` en `test_timeout_races.py`, con asesores de `ADVISORS`) queda
  cumplida al crear el archivo; se anota en `progress/impl_vencimiento_automatico.md` (T42).

Cada test comprueba el estado final del caso (`status`, `advisor_id`, `assigned_at`), los envíos
del gateway y `timed_out_cases`. Con el código actual (`update_case` en `check_timeouts` y
`_process_handover`) estos tests fallan, que es
lo que demuestra que reproducen el hallazgo. La atomicidad en Postgres se verifica por la forma de
la sentencia (R27) con la conexión falsa; no hay test con Postgres real (opcional y marcado
`integration`, fuera de esta feature).

## Excepciones

No se añaden. Se reutilizan `ServiceUnavailable` (gateway) y el manejador genérico de `main.py`
(`500 internal_error`) si el repositorio lanza.

## Dependencias nuevas

Ninguna. El script usa `httpx` (ya en `requirements-dev.txt` y en
`services/handover/requirements.txt`, que es lo que instala la imagen de `timeouts_worker`).

## Alternativas descartadas

1. **Marcar `timed_out` antes de enviar y volver a `open` si el envío falla.** Sin columna nueva,
   pero durante el envío el caso no es `open`: una reutilización simultánea no lo encuentra en
   `find_active_case` y crea un caso duplicado, y el caso «parpadea» de estado si el envío falla.
   La reclamación mantiene `open` todo el tiempo.
2. **Estado intermedio `timing_out` en `CaseStatus`.** Mismo problema de visibilidad que (1) y
   obliga a revisar todas las consultas por estado (`find_active_case`, `assign_case`, R18 de la
   #7).
3. **Bloqueo `SELECT ... FOR UPDATE SKIP LOCKED` durante el envío.** Mantiene una transacción y un
   bloqueo de fila abiertos hasta `HTTP_TIMEOUT_SECONDS` mientras se habla con el gateway, y
   bloquearía también `assign_case`; no se puede reproducir con el repositorio falso.
4. **Versión optimista (`version` en `Case` y `UPDATE ... WHERE version = %s`).** Cambia `Case`,
   `_CASE_COLUMNS`, `_row_to_case` y todos los tests de filas de la #7, y no evita el doble envío:
   ambas ejecuciones enviarían antes de descubrir el conflicto.
5. **Bucle dentro de handover (tarea de fondo en FastAPI).** Descartado por el humano: el plan
   gratuito de Render duerme el servicio.
6. **Imagen propia para `timeouts_worker` (`scripts/Dockerfile`).** Otro Dockerfile que mantener
   con la misma base y dependencias que handover; la reutilización solo cuesta una línea `COPY`.

## Fuera de alcance (riesgos residuales para que los revise el humano)

**Resueltos por la #14** (escrituras condicionales `assign_if_unassigned`/`close_if_still_allowed`
que solo escriben sus campos, y `threading.Lock` en `_run`; `specs/autorizacion_asesores/design.md`
§3.3 y §3.5). Se conservan las letras para no romper referencias; la #12 no hace nada con ellos:

- (a) RESUELTO por la #14 — `assign` contra `close`: `assign_if_unassigned` solo escribe si el
  caso sigue `open` o `timed_out`; un cierre simultáneo ya no se pierde.
- (b) RESUELTO por la #14 — `assign` contra reutilización: `assign_if_unassigned` no reescribe
  `last_messages`; los mensajes nuevos no se pierden.
- (c) RESUELTO por la #14 — `close` contra `assign`: `close_if_still_allowed` solo escribe
  `status`, `closed_by` y `closed_at` si el caso sigue permitido; `advisor_id` y `assigned_at` no
  se pierden.
- (f) RESUELTO en handover por la #14 — conexión pg8000 compartida entre hilos
  (`pg8000.dbapi.threadsafety = 1`): `_run` toma `self._lock`. En el orquestador lo cubre la #18
  (`candado_repositorio_orquestador`). Ver D2.

**Siguen abiertos** (el acceptance de la #12 no los cubre y esta feature **no** los resuelve):

- (d) **Reutilización de un caso que se cierra a mitad:** si el caso se cierra entre
  `find_active_case` y `update_last_messages` (dentro de `_process_handover`), los mensajes se
  escriben en un caso `closed` y se avisa a los asesores con el `case_id` de un caso cerrado; la
  respuesta es `notified`. `update_last_messages` es incondicional a propósito (R25 solo pide no
  tocar estado ni asesor).
- (e) Dos `POST /handover` simultáneos del mismo contacto sin caso activo crean dos casos (ya
  existía en la #7).
- (g) Si se reutiliza un caso mientras otra ejecución le envía el aviso de espera, el caso termina
  `timed_out` justo después de avisar a los asesores; sigue siendo asignable (`timed_out` →
  `assigned`, R11 de la #7).
- (h) Despliegue en Render: PENDIENTE (decisión del humano; ver D6).

## Nota de coordinación con la #10, la #11 y la #14 (orden 10 → 11 → 14 → 12)

- La #12 se implementa **después** de la #11 y de la #14 (ver «Precondición de orden»). Cuando
  llega, la lógica de reutilización y de `no_advisors` ya está en `_process_handover`; la #12
  cambia solo las dos llamadas a `update_case` de ese cuerpo y la de `check_timeouts`, y no toca
  `open_case`, el registro, `assign_case`, `close_case` ni los métodos de la #14.
- `_SCHEMA`: la #12 añade su `ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS
  timeout_claimed_at ...` **al final**, tras el último `CREATE TABLE` (hoy el de
  `handover_requests`). Orden final: `CREATE handover_cases`, `CREATE handover_notifications`,
  `CREATE handover_denials` (#14), `CREATE handover_requests` (#11), `ALTER handover_cases`
  (#12).
- `test_postgres_repository_connects_lazily_and_once` cuenta solo `CREATE TABLE`: sigue en 4 (el
  valor que deja la #14); el `ALTER` no lo altera y la #12 no lo modifica. Lo mismo vale para la
  otra aserción de `== 4` sobre `CREATE TABLE` de `test_repository.py`.
- `test_postgres_repository_uses_parameters_only`: ver S1.
- Los tests de la #11 (`tests/test_requests.py`) y de la #14 (`tests/test_assign_close_races.py`,
  `tests/test_authorization.py`, `tests/test_cases.py`) deben pasar sin cambios: usan los
  fixtures `env`/`env_no_advisors`/`env_factory` y `make_env`, que la #12 no modifica. En
  `tests/test_repository.py`, los tests de la #14 y la #11 que usan el helper `_statements`
  (`test_postgres_repository_add_denial_uses_parameters_only`,
  `test_postgres_request_methods_use_parameters_only` y los que leen `_statements(conn)[-1]`)
  pasan sin tocar sus aserciones gracias al cambio (B) de S1 sobre ese helper; es el único
  cambio en código de test de la #11/#14.
- La #10 no afecta al worker: el script lee `os.environ` y no importa `handover.config`.

## Supuestos a confirmar (revisión humana)

| Id | Supuesto | Detalle |
|---|---|---|
| — | DECIDIDO por el humano: intervalo del bucle | 60 s (`CHECK_TIMEOUTS_INTERVAL_SECONDS`); aviso al cliente entre 300 y 360 s tras abrirse el caso, más la duración de la llamada |
| **S1 (REVISAR)** | **Cambio de un test de la #7 y de un helper de test de la #14.** El acceptance de la #12 no autoriza explícitamente cambiar tests de otras features, pero `test_postgres_repository_uses_parameters_only` (`services/handover/tests/test_repository.py`) fallaría sin tocarlo: el `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` no lleva parámetros (rompe `assert params`) y no empieza por `CREATE`. Además, `_connection` ejecuta todo `_SCHEMA` con el cursor falso, que lo registra en `conn.log`; el helper `_statements` de la #14 (`test_repository.py` l.169-170) filtra solo `not sql.startswith("CREATE")`, así que el `ALTER` aparecería en sus resultados y romperían `test_postgres_repository_add_denial_uses_parameters_only` (`len == 1` pasaría a 2 y `statements[0]` sería el `ALTER`) y `test_postgres_request_methods_use_parameters_only` de la #11 (`len == 1`/`len == 2` pasarían a 2/3 y `statements[0]` dejaría de ser el `INSERT`). | Cambios exactos, en dos puntos de `test_repository.py`. **(A) Test de la #7:** (1) el filtro de `statements` pasa de `not sql.startswith("CREATE")` a `not sql.startswith(("CREATE", "ALTER"))`; (2) se añaden al final de las llamadas del test `repo.claim_timeout("case-1", NOW, NOW)`, `repo.release_timeout_claim("case-1")`, `repo.mark_timed_out("case-1")` y `repo.update_last_messages("case-1", case.last_messages)`; (3) el recuento pasa de `len(statements) == 6` a `len(statements) == 10`. Se mantienen **sin cambios** las demás aserciones: las comprobaciones de `CREATE TABLE` de `handover_cases` y `handover_notifications`; `SECRET`, `"case-1"` y `"contact-1"` fuera del SQL; `sql.count("%s") == len(params)`; `params` no vacío; el texto de cliente (`SECRET`) presente solo en parámetros; y ningún literal entre comillas simples en el SQL. Ni la #11 ni la #14 modifican este test (solo el recuento de `CREATE TABLE` de `test_postgres_repository_connects_lazily_and_once`, hoy 4), así que parte de 6 (`test_repository.py` l.78). **(B) Helper `_statements` de la #14:** su filtro pasa de `not sql.startswith("CREATE")` a `not sql.startswith(("CREATE", "ALTER"))` (alternativa equivalente válida: extraer un helper común usado por ambos filtros). No cambia ninguna aserción ni ningún otro test de la #11 o la #14: con el helper ajustado, `test_postgres_repository_add_denial_uses_parameters_only`, `test_postgres_request_methods_use_parameters_only` y los que usan `_statements(conn)[-1]` pasan tal cual. No hay más cambios en tests existentes; requirements.md y el alcance no cambian. |

## Decisiones pendientes del humano

D1 y D2 ya están resueltas por otras features. D3-D6 no están decididas; el spec propone un
valor por defecto o una recomendación, pero el humano debe confirmarlas o cambiarlas. Esta
feature **no** amplía su alcance por ellas.

- **D1 — RESUELTA por la #14 (opción (b)): carreras de `assign_case`/`close_case`** (riesgos
  (a), (b) y (c) de «Fuera de alcance»). La #14 hizo condicionales la asignación y el cierre
  (`assign_if_unassigned`, `close_if_still_allowed`; `specs/autorizacion_asesores/design.md` §3.3
  y §8.5). El riesgo (d) (reutilización de un caso que se cierra a mitad) sigue abierto y no
  entra en la #12.
- **D2 — RESUELTA: conexión pg8000 compartida entre hilos** (riesgo (f)). En handover, por el
  `threading.Lock` alrededor de `_run` de `PostgresCaseRepository` (#14); en el orquestador, por
  la #18 (`candado_repositorio_orquestador`). La #12 no toca el candado.
- **D3 — REVISAR (pendiente del humano): `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`** (variable
  nueva, R12, R29). Debe cubrir varios envíos al gateway en una misma llamada (hasta
  `HTTP_TIMEOUT_SECONDS=10` cada uno). *Recomendación del spec:* mantener la variable y 120 s;
  gracias a la reclamación, un timeout del cliente no provoca dobles envíos.
- **D4 — REVISAR (pendiente del humano): caducidad de la reclamación = `HANDOVER_TIMEOUT_SECONDS`**
  (300 s, R24). Exige que sea mayor que `HTTP_TIMEOUT_SECONDS`, o un envío lento podría ser
  retomado por otra ejecución. *Recomendación del spec:* reutilizar `HANDOVER_TIMEOUT_SECONDS`
  sin variable propia (300 > 10 con los valores por defecto).
- **D5 — REVISAR (pendiente del humano): `restart: unless-stopped`** en `timeouts_worker` y
  **sin reintento rápido** tras un fallo (el bucle espera el intervalo normal, sin espera
  creciente). *Recomendación del spec:* mantener ambos; con configuración inválida el contenedor
  se reinicia en bucle dejando el error en el log, aceptable en local.
- **D6 — REVISAR (pendiente del humano): Render.** Sigue PENDIENTE (decisión del humano
  2026-10-31). El script admite llamada única (Render Cron Job o GitHub Actions `schedule`) y
  bucle (worker). *Recomendación del spec:* no decidir hasta que se aborde el despliegue; esta
  feature no crea `render.yaml` ni toca `.github/`.
