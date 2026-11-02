# Design — autorizacion_asesores (feature #14)

> Cómo se construye lo pedido en `requirements.md`. Fuentes: acceptance de la #14, criterios
> «Decidido por el humano (2026-10-31)», `progress/propuesta_etapa2.md` §4 y §6, el spec de la
> #13 (`specs/contrato_autorizacion_asesores/`, `done`: S12, C1-C6, R26), la regla de casos
> huérfanos que publica la #17, el spec de la #12 (`specs/vencimiento_automatico/design.md`, D1 y
> D2) y el de la #7 (`specs/traspaso_asesor/`, R11-R16 y R31-R38). Apoyado en
> `docs/architecture.md` §3 (principios 1, 3, 4, 7, 9) y `docs/conventions.md`.

## 1. Alcance y dependencias de orden

- Toca `services/handover/` y `services/orchestrator/`. **No** toca `contracts/` (lo hacen la
  #13 y la #17), `eval/`, `scripts/`, `docker-compose.yml`, `.github/` ni `.env.example` (no hay
  variables nuevas).
- **Requiere la #13 implementada** (`done`): se importan de `lazaro_contracts`
  `CaseAuthorizeRequest`, `CaseAuthorizeResponse` y `CaseAuthorizeAction` tal cual los define su
  `design.md` §3. Si al implementar no existen, el implementer para con `blocked`.
- **Requiere la #17 implementada** (`done`; `depends_on` [10, 13, 17]): S12 de `CONTRATOS.md`
  ya recoge la regla de cierre de casos huérfanos (decisión 7 del humano), con este texto:
  «Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o ya no está en
  `ADVISOR_CHAT_IDS`. Un caso huérfano lo cierra cualquier asesor registrado […]; cerrarlo no es
  reasignarlo. Un caso huérfano no lo responde ni lo asigna ningún otro asesor […]», la
  salvedad en la precedencia («escalón que no se aplica a `POST /cases/{id}/close` ni a
  `authorize` con `action` = `close` sobre un caso huérfano») y el procedimiento de retirada
  («al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids»). La #14 lo
  implementa y **no** edita el contrato. Si al implementar S12 no contiene esa regla, el
  implementer para con `blocked`.
- **Conviene la #10 antes** (`done`): `Settings.advisor_ids` devuelve una lista de enteros ya
  validada (sin duplicados ni entradas no numéricas). Esta feature no valida la configuración.
- Sin dependencias nuevas.

### Punto de partida: orden fijado 10 → 11 → 12 → 13 → 17 → 14

Esta feature se implementa sobre el código que dejan la #10, la #11, la #12 y la #13 (la #17
solo cambia `contracts/`). No depende del contenido de la #11 ni de la #12, pero parte de su
estado:

- **#10:** `Settings.advisor_ids` validada; `create_app` registra `advisors_configured` (INFO) y
  `no_advisors_configured` (WARNING) (S6 de la #10); `configure_logging()` a nivel de módulo.
- **#11:** tabla `handover_requests` y métodos `add_request`/`complete_request`;
  `test_postgres_repository_connects_lazily_and_once` cuenta **3** `CREATE TABLE`;
  `open_case` envuelve `_process_handover`.
- **#12:** métodos `claim_timeout`, `release_timeout_claim`, `mark_timed_out` y
  `update_last_messages`; `FakeCaseRepository.timeout_claims`; `_SCHEMA` termina con
  `ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS timeout_claimed_at ...`;
  `tests/conftest.py` expone `make_env(advisors=None, repo=None, gateway=None)`; y
  `tests/test_timeout_races.py` llama a `assign_case`/`close_case` desde un `on_send` (T15 y T16
  de la #12) y define `HookRepository(FakeCaseRepository)`. `assign_case` y `close_case` siguen
  leyendo con `get_case` y escribiendo con `update_case`: sus carreras (riesgos (a)-(d) de la #12)
  son la D1 de la #12, que el humano resuelve con la opción (b) **en esta feature**.

Lo que añade esta feature sobre ese estado:

- **Otra** tabla (`handover_denials`) y **otro** método (`add_denial`), con su sentencia
  `CREATE TABLE` al final de `_SCHEMA`, tras el `ALTER` de la #12. El conteo de `CREATE TABLE`
  pasa de 3 a **4** (§6).
- **Tres métodos nuevos** del repositorio: `assign_if_unassigned` y `close_if_still_allowed`
  (escrituras condicionales, R37, R41, R43, R54) y `count_assigned_by_advisor` (recuento de
  huérfanos, R49). `assign_case` y `close_case` dejan de usar `update_case`.
- **Candado** `threading.Lock` en `PostgresCaseRepository._run` (R44, R45).
- **Recuento de huérfanos al arrancar** en un `lifespan` de FastAPI (R49-R52).
- No modifica la firma, el SQL ni el comportamiento de ningún método existente del repositorio,
  incluidos los de la #11 y la #12. `update_case` se conserva en el `Protocol` y en las dos
  implementaciones (lo usa `test_postgres_repository_uses_parameters_only`), aunque tras la #12
  y la #14 ningún camino de `domain.py` lo llama.
- `assign_case` y `close_case` ganan el parámetro `settings`. Las llamadas de
  `tests/test_timeout_races.py` se adaptan (§6).
- `test_postgres_repository_uses_parameters_only` (con el cambio S1 de la #12) no se ve
  afectado: no llama a los métodos nuevos. Los tests de la #11 (`tests/test_requests.py`) y de la
  #12 que no llaman a `assign_case` ni a `close_case` no cambian; `make_env(advisors=[222, 333])`
  de T14/T19/T22 es compatible con la firma de la #12.

## 2. Archivos

| Acción | Ruta | Cambio |
|---|---|---|
| modificar | `services/handover/handover/domain.py` | `AdvisorForbidden`, `Denial`, `DenialAction`, `is_registered_advisor`, `is_orphan_case`, `can_act_on_case`, `_deny`, `_resolve_lost_assignment`, `_resolve_lost_close`, `authorize_case`, `count_orphan_cases`, `log_orphan_cases`; `assign_case` y `close_case` reciben `settings`, aplican las reglas y escriben con las escrituras condicionales |
| modificar | `services/handover/handover/adapters/repository.py` | `add_denial`, `assign_if_unassigned`, `close_if_still_allowed`, `count_assigned_by_advisor` en `CaseRepository`, `FakeCaseRepository` y `PostgresCaseRepository`; `threading.Lock` en `_run`; sentencia nueva al final de `_SCHEMA` |
| modificar | `services/handover/handover/main.py` | ruta `POST /cases/{case_id}/authorize`; `post_assign`/`post_close` pasan `settings`; `lifespan` que llama a `log_orphan_cases` |
| modificar | `services/orchestrator/orchestrator/domain.py` | `AdvisorForbidden`, `CaseClosed`, `AuthorizationDenied`, `AUTHORIZE_DENIAL_CODES`, `_record_forbidden`; `reply_to_case` autoriza primero |
| modificar | `services/orchestrator/orchestrator/adapters/handover.py` | `authorize` en `HandoverClient`, `HttpHandoverClient` y `FakeHandoverClient` |
| crear | `services/handover/tests/test_authorization.py` | tests de R1-R8, R11-R20, R22, R46-R48 |
| crear | `services/handover/tests/test_assign_close_races.py` | tests de carrera de R37-R42, R54 y R55 con repositorio falso |
| modificar | `services/handover/tests/test_security.py` | entradas nuevas en `ROUTES`/`INVALID_BODIES`, aserción añadida, prueba de seguridad obligatoria |
| modificar | `services/handover/tests/test_cases.py` | un cambio de fixture (§6) |
| modificar | `services/handover/tests/test_repository.py` | conteo de `CREATE TABLE` 3 → 4 (§6) y tests nuevos de `add_denial`, escrituras condicionales, recuento y candado |
| modificar | `services/handover/tests/test_startup.py` (de la #10) | tests nuevos del recuento de huérfanos al arrancar (solo se añaden) |
| modificar | `services/handover/tests/test_timeout_races.py` (de la #12) | pasar `env.settings` a `assign_case`/`close_case` (§6) |
| crear | `services/orchestrator/tests/test_authorization.py` | tests de R23-R35 y R53 |
| modificar | `services/orchestrator/tests/test_security.py` | prueba de seguridad obligatoria |
| modificar | `services/orchestrator/tests/test_case_reply.py` | añadir `403` al parametrizado de `assign` (solo amplía) |

`main.py` del orquestador no cambia: `AdvisorForbidden` y `CaseClosed` son `DomainError` y el
manejador existente los convierte en `{"error": "forbidden" | "case_closed", ...}`.

## 3. Handover

### 3.1 Firmas nuevas (`domain.py`)

```python
from lazaro_contracts import CaseAuthorizeAction, CaseAuthorizeRequest, CaseAuthorizeResponse

DenialAction = Literal["reply", "close", "assign"]


class AdvisorForbidden(DomainError):
    code = "forbidden"
    status_code = 403


class Denial(BaseModel):
    case_id: str
    advisor_id: str
    action: DenialAction
    at: datetime


def is_registered_advisor(advisor_id: str | None, settings: Settings) -> bool:
    """R1: igualdad exacta con str(int) de algún id de ADVISOR_CHAT_IDS. None → False."""


def is_orphan_case(case: Case, settings: Settings) -> bool:
    """Caso `assigned` cuyo advisor_id (también None) no es asesor registrado. Pura."""


def can_act_on_case(
    case: Case, advisor_id: str, action: DenialAction, settings: Settings
) -> bool:
    """Caso no cerrado. Sin asignar → True. `assigned` a advisor_id → True.
    `assigned` a otro: solo action == "close" y el caso es huérfano (R46, R47). Pura."""


def authorize_case(
    case_id: str, req: CaseAuthorizeRequest, settings: Settings, adapters: Adapters
) -> CaseAuthorizeResponse: ...


def assign_case(
    case_id: str, advisor_id: str, settings: Settings, adapters: Adapters
) -> CaseAssignResponse: ...          # gana `settings`


def close_case(
    case_id: str, advisor_id: str, settings: Settings, adapters: Adapters
) -> CaseCloseResponse: ...           # gana `settings`


def count_orphan_cases(settings: Settings, adapters: Adapters) -> int:
    """Suma count_assigned_by_advisor() de los advisor_id que no son asesor registrado."""


def log_orphan_cases(settings: Settings, adapters: Adapters) -> None:
    """R49-R51: INFO orphan_cases count=n; WARNING orphan_cases_present si n > 0;
    WARNING orphan_cases_check_failed si el recuento lanza (sin ids ni texto de la excepción)."""
```

`_deny(case_id, advisor_id, action, adapters) -> NoReturn` (privada): llama a
`adapters.repository.add_denial(Denial(...))` con `at=adapters.clock()` y lanza
`AdvisorForbidden("El asesor no está autorizado para esta acción sobre el caso.")`. Si
`add_denial` lanza, la excepción sube sin capturar y el manejador genérico responde `500
internal_error` (R22); el caso no se ha tocado porque las comprobaciones van antes de escribir.

`is_registered_advisor` compara contra `{str(i) for i in settings.advisor_ids}`. Por eso
`"0111"`, `"+111"`, `" 111"`, `"111 "` o `"1.11"` **no** son el asesor `111` (R1). No se
normaliza el `advisor_id`: normalizar abriría variantes que el contrato (S6: chat_id en
decimal) no pide.

Un caso `assigned` con `advisor_id` nulo (no lo produce ninguna ruta; solo datos antiguos o
fixtures) es huérfano. *Decidido por el humano (2026-10-31), decisión 7*, y publicado en S12 por
la #17 («`advisor_id` es nulo o ya no está en `ADVISOR_CHAT_IDS`»). `is_orphan_case` devuelve
`True` para `status == "assigned"` y `not is_registered_advisor(case.advisor_id, settings)`, que
cubre `None`.

### 3.2 Orden de comprobación (R4-R7, R11-R18, R37-R42, R46-R48, R54, R55)

**Decidido por el humano (2026-10-31):** C1 de la #13 (precedencia) y las decisiones 2 y 7 de
esta feature (escrituras condicionales; casos huérfanos, publicada por la #17). Una sola
secuencia para las tres rutas; la diferencia está en los pasos 4 y 5:

| Paso | Comprobación | `authorize` | `assign` | `close` |
|---|---|---|---|---|
| 1 | `advisor_id` no registrado | `403` + denegación (`action` del cuerpo) (R4) | `403` + denegación (`assign`) (R11) | `403` + denegación (`close`) (R14) |
| 2 | caso inexistente | `404` (R5) | `404` (R14 #7) | `404` (R14 #7) |
| 3 | caso `closed` | `409` (R6) | `409` (R13 #7) | `200` sin cambios (S8, R18) |
| 4a | caso `assigned` a otro asesor **registrado** | `403` + denegación (R7) | `403` + denegación (R12) | `403` + denegación (R15) |
| 4b | caso **huérfano** (`assigned` a un id no registrado) | `reply`: `403` + denegación (R48); `close`: pasa al paso 5 (R46) | `403` + denegación (R12, R48) | pasa al paso 5 (R47) |
| 5 | permitido | `200 allowed=true` (R2, R3, R46) | `assigned` al mismo → `200` sin escribir (R13); sin asignar → `assign_if_unassigned` (R37) y, si no cambia, §3.3 | `close_if_still_allowed` con el asesor autorizado (R16, R17, R41, R47, R54); si no cambia → releer: `closed` → `200` (R42), otro estado → `403` + denegación (R55) |

- Paso 1 antes que todo: no revela si el caso existe ni su estado a quien no es asesor (C1). El
  asesor retirado recibe `403` también sobre sus propios casos (R4, T14).
- Paso 3 en `close`: un asesor registrado que cierra un caso ya cerrado recibe `200` sin
  cambios, aunque no fuera quien lo cerró ni el asignado (C2: se mantiene S8). En `authorize` con
  `action=close` sobre un caso cerrado responde `409` (C2).
- Paso 4a en `assign`: otro asesor recibe `403`; el mismo asesor `200` sin cambios (R26 de la
  #13, que estrecha S11).
- Paso 4b: cualquier asesor registrado puede **cerrar** un caso huérfano (opción C), pero nadie
  puede responderlo ni asignárselo (sin reasignación). El cierre conserva el `advisor_id` y el
  `assigned_at` del asesor retirado y registra al que cierra en `closed_by` (R47).

`authorize_case` no escribe en `cases` ni llama al gateway (R8): solo lee el caso y, si deniega,
escribe en `handover_denials`.

### 3.3 Asignación y cierre condicionales (R37-R43, R54, R55) — Decidido por el humano (2026-10-31)

Decisión 2 del humano: opción (b) de la D1 de la #12, implementada aquí. Además, una carrera no
puede cerrar un caso que ya quedó asignado a otro asesor: el cierre condicional exige en la
misma sentencia el estado o el asesor que se autorizó.

`assign_case`, tras los pasos 1-4 con el caso leído sin asignar:

```text
if repo.assign_if_unassigned(case_id, advisor_id, clock()):  → 200 (R37)
current = repo.get_case(case_id)        # _resolve_lost_assignment: alguien escribió en medio
├─ None                                 → CaseNotFound 404 (defensivo; los casos no se borran)
├─ closed                               → CaseClosed 409, sin escribir (R39)
├─ assigned a advisor_id                → 200 sin escribir (R40, como R13)
└─ assigned a otro (registrado o no)    → _deny(..., "assign") → 403 + denegación (R38)
```

«O `assigned` al mismo asesor» (texto de la decisión) se cumple sin escribir: tanto si el caso ya
estaba asignado al mismo asesor al leerlo (R13) como si lo asignó él mismo en medio (R40). Así no
cambia `assigned_at`, como exige S11.

`close_case`, tras los pasos 1-4 con el caso leído (`case`):

```text
allowed_assignee = case.advisor_id if is_orphan_case(case, settings) else advisor_id
if repo.close_if_still_allowed(case_id, advisor_id, allowed_assignee, clock()):  → 200 (R41, R47, R54)
current = repo.get_case(case_id)        # _resolve_lost_close: alguien escribió en medio
├─ None                                 → CaseNotFound 404 (defensivo; los casos no se borran)
├─ closed                               → 200 sin cambios, con el cierre que ganó (R42, S8)
└─ cualquier otro estado                → _deny(..., "close") → 403 + denegación (R55)
```

- `allowed_assignee` es el asesor con el que el cierre sigue permitido si el caso está
  `assigned` al escribir: el propio `advisor_id` de la petición (caso leído sin asignar o
  asignado a él, R41) o el `advisor_id` huérfano leído, también `None` (R54).
- El caso real de «cualquier otro estado» es «quedó `assigned` a otro asesor entre la lectura y
  la escritura» (§3.2 paso 4a: otro asesor → `403`). Con las reglas actuales no hay otro estado
  alcanzable: un caso `assigned` no vuelve a `open`/`timed_out`, un huérfano no se reasigna
  (R48) y `ADVISOR_CHAT_IDS` no cambia en caliente. Si apareciera, se falla cerrado (`403`, sin
  escribir, sin reintentar) en lugar de entrar en un bucle de reintentos.
- El `403` por carrera perdida cuenta como denegación (decisión 3, D7) y se registra con acción
  `close`.

Repositorio:

| Método | Efecto | PostgreSQL (una sentencia, `%s`, `fetch=True`) |
|---|---|---|
| `assign_if_unassigned(case_id, advisor_id, at) -> bool` | Si el caso está `open` o `timed_out`, escribe `status='assigned'`, `advisor_id`, `assigned_at` y devuelve `True`; si no, `False` sin cambiar nada | `UPDATE handover_cases SET status = %s, advisor_id = %s, assigned_at = %s WHERE case_id = %s AND status IN (%s, %s) RETURNING case_id` con `("assigned", advisor_id, at, case_id, "open", "timed_out")` |
| `close_if_still_allowed(case_id, advisor_id, allowed_assignee, at) -> bool` | Si el caso está `open` o `timed_out`, o está `assigned` con `advisor_id == allowed_assignee` (`None` = nulo), escribe `status='closed'`, `closed_by=advisor_id`, `closed_at` y devuelve `True`; si no, `False` sin cambiar nada | Con `allowed_assignee` no nulo: `UPDATE handover_cases SET status = %s, closed_by = %s, closed_at = %s WHERE case_id = %s AND (status IN (%s, %s) OR (status = %s AND advisor_id = %s)) RETURNING case_id` con `("closed", advisor_id, at, case_id, "open", "timed_out", "assigned", allowed_assignee)`. Con `allowed_assignee` nulo: la misma sentencia con `advisor_id IS NULL` en lugar de `advisor_id = %s` y sin el último parámetro |
| `count_assigned_by_advisor() -> dict[str \| None, int]` | Número de casos `assigned` por `advisor_id` | `SELECT advisor_id, COUNT(*) FROM handover_cases WHERE status = %s GROUP BY advisor_id` con `("assigned",)` |

- Dos variantes de texto SQL para el caso nulo, elegidas en Python, en lugar de
  `advisor_id IS NOT DISTINCT FROM %s`: un `NULL` sin tipo como parámetro de pg8000 obliga a
  Postgres a inferir el tipo, y la variante `IS NULL` evita esa duda sin perder la
  parametrización (opción conservadora; la alternativa queda descartada en §9).

- Se usa `RETURNING case_id` + `fetch=True` (filas no vacías = la fila cambió), el mismo patrón
  que la #12, que funciona con pg8000 y con la conexión falsa de `test_repository.py`.
- El SQL no lleva literales entre comillas: los estados van como parámetros.
- `FakeCaseRepository`: cada método comprueba y escribe sin ceder el control (atómico en un
  proceso), sustituyendo el caso por `model_copy(update=...)` con solo esos campos.
- En PostgreSQL cada `UPDATE` condicional es atómico por fila entre conexiones distintas (READ
  COMMITTED reevalúa el `WHERE`); dentro de un proceso, el candado de §3.5 serializa las
  sentencias sobre la conexión compartida.

Qué resuelve respecto a los riesgos de la #12 («Fuera de alcance»):

- (a) `assign` contra `close`: el `assign` ya no reabre un caso cerrado (R39).
- (b) `assign` contra reutilización: el `assign` ya no reescribe `last_messages` (R37).
- (c) `close` contra `assign`: el cierre ya no borra `advisor_id` ni `assigned_at` (R41) y,
  además, ya no cierra un caso que quedó asignado a otro asesor en medio: ese cierre pierde y
  recibe `403` (R55).
- Reasignación silenciosa (D10): el segundo `assign` pierde y recibe `403` (R38).
- **No** resuelve (d) (reutilización de un caso que se cierra a mitad, dentro de
  `_process_handover`) ni (e) (dos `POST /handover` simultáneos): no tocan las rutas de esta
  feature. Quedan para la #12 o una feature propia (§8, «Decisiones para el humano»).

Coherencia con los tests de carrera de la #12 (`tests/test_timeout_races.py`):

- T15 #12: `assign_case(case_id, "222", ...)` dentro del `on_send` de `check_timeouts`. El caso
  sigue `open` (la reclamación de la #12 no cambia el estado), así que `assign_if_unassigned`
  escribe; después `mark_timed_out` (`WHERE status = 'open'`) no lo toca. Resultado idéntico.
- T16 #12: `close_case` dentro del `on_send`. El caso sigue `open`, así que
  `close_if_still_allowed` escribe; `mark_timed_out` no lo toca. Resultado idéntico.
- T14 #12 (`after_list` asigna o cierra) y T17 #12: idénticos por lo mismo.
- `HookRepository(FakeCaseRepository)` de la #12 hereda los métodos nuevos sin cambios.
- Solo cambia la firma (`settings`), §6.

### 3.4 Ruta nueva y arranque (`main.py`)

```python
@app.post("/cases/{case_id}/authorize", response_model=CaseAuthorizeResponse)
def post_authorize(case_id: str, body: CaseAuthorizeRequest) -> CaseAuthorizeResponse:
    return authorize_case(case_id, body, settings, adapters)
```

El token (R9) y el `422` (R10) los dan el middleware y el manejador existentes. Ninguna ruta
existente cambia su firma HTTP.

Recuento de huérfanos al arrancar (R49-R52, procedimiento A de la decisión 7):

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(log_orphan_cases, settings, adapters)   # R49-R51
    yield

app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
```

- **D12 — Decidido por el humano (2026-10-31), decisión 4:** se hace en el `lifespan` (lo ejecuta uvicorn al arrancar) y no en
  `create_app`, porque `create_app()` corre al importar `handover.main` y no debe abrir la
  conexión (`test_import_main_does_not_connect`, R26 de la #7 y R52). Los tests que crean
  `TestClient(app)` sin `with` no ejecutan el `lifespan`, así que ningún test existente cambia;
  los tests nuevos usan `with TestClient(app)`.
- Niveles coherentes con S6 de la #10 (`advisors_configured` INFO, `no_advisors_configured`
  WARNING): `orphan_cases count=<n>` en INFO siempre y `orphan_cases_present count=<n>` en
  WARNING si `n > 0`. Sin ids de casos ni de asesores (R49, R50).
- **D13 — Decidido por el humano (2026-10-31), decisión 4:** si el recuento lanza (p. ej. la base no responde al arrancar), se registra
  `orphan_cases_check_failed` en WARNING, sin ids ni texto de la excepción, y el servicio termina
  de arrancar (R51). Hoy handover arranca sin base (la conexión es perezosa); hacer que el
  arranque dependa del recuento cambiaría eso.
- `log_orphan_cases` se ejecuta en el pool de hilos porque el repositorio es síncrono.

### 3.5 Repositorio (`adapters/repository.py`)

```python
class CaseRepository(Protocol):
    ...  # métodos existentes sin cambios
    def add_denial(self, denial: Denial) -> None: ...
    def assign_if_unassigned(self, case_id: str, advisor_id: str, at: datetime) -> bool: ...
    def close_if_still_allowed(
        self, case_id: str, advisor_id: str, allowed_assignee: str | None, at: datetime
    ) -> bool: ...
    def count_assigned_by_advisor(self) -> dict[str | None, int]: ...
```

- `FakeCaseRepository`: `self.denials: list[Denial] = []`; `add_denial` añade una copia; los
  otros tres como en §3.3.
- `PostgresCaseRepository.add_denial`:
  `INSERT INTO handover_denials (case_id, advisor_id, action, at) VALUES (%s, %s, %s, %s)`.
- Sentencia nueva al final de `_SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS handover_denials (
  id          BIGSERIAL   PRIMARY KEY,
  case_id     TEXT        NOT NULL,   -- el de la ruta; puede no existir (paso 1)
  advisor_id  TEXT        NOT NULL,
  action      TEXT        NOT NULL,   -- reply | close | assign
  at          TIMESTAMPTZ NOT NULL    -- reloj inyectado
)
```

Sin clave foránea a `handover_cases`: una denegación del paso 1 puede llevar un `case_id` que no
existe y también debe quedar registrada. Solo ids y acción; ningún texto de clientes (Ley 1581).
Sin ruta de consulta ni política de retención (como la #11: fuera de alcance).

**Candado (R44, R45) — Decidido por el humano (2026-10-31), decisión 5 (D2 de la #12):**

```python
def __init__(self, database_url, connect=None) -> None:
    ...
    self._lock = threading.Lock()

def _run(self, sql: str, params: tuple, fetch: bool = False) -> list:
    with self._lock:
        conn = self._connection()      # apertura y esquema también bajo el candado (R45)
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            rows = list(cur.fetchall()) if fetch else []
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise
```

- `threading.Lock` (no reentrante) basta: ningún método del repositorio llama a `_run` dentro de
  otro `_run`, y `_connection()` solo se llama desde `_run`.
- Serializa todo el acceso a la conexión del proceso. Con el tráfico esperado (handover recibe
  pocas peticiones por segundo) el coste es despreciable; una conexión por petición o un pool
  quedan descartados (§9).
- Se prueba con la conexión falsa de `test_repository.py`: la cursora falsa comprueba que el
  candado está tomado y mide la concurrencia máxima con dos hilos (T70, T71).

**Orquestador — fuera de esta feature:** `PostgresRepository` del orquestador tiene el mismo
patrón (una conexión pg8000 compartida, rutas síncronas y `BackgroundTasks` en el pool de hilos)
y necesita la misma protección **antes de la #16**, que multiplica el tráfico. *Decidido por el
humano (2026-10-31), decisión 6:* va en la feature #18 `candado_repositorio_orquestador` (previa
a la #16). Esta feature solo la referencia: no la implementa, no la prueba y no tiene R sobre
ella.

## 4. Orchestrator

### 4.1 Firmas nuevas (`domain.py`)

```python
AUTHORIZE_DENIAL_CODES = ("forbidden", "not_found", "case_closed")


class AdvisorForbidden(DomainError):
    code = "forbidden"
    status_code = 403


class CaseClosed(DomainError):
    code = "case_closed"
    status_code = 409


class AuthorizationDenied(Exception):
    """Interna: handover denegó la autorización; `code` ∈ AUTHORIZE_DENIAL_CODES."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
```

`AuthorizationDenied` y `ServiceUnavailable` son internas (como `InvalidAnswer`): nunca llegan
al exterior; `reply_to_case` las traduce.

### 4.2 Flujo de `reply_to_case`

```text
1. authorize(case_id, advisor_id, "reply")            # R23, siempre lo primero
   ├─ AuthorizationDenied("not_found")   → CaseNotFound 404                         (R27)
   ├─ AuthorizationDenied("forbidden")   → _record_forbidden → AdvisorForbidden 403 (R25, R29, R30)
   ├─ AuthorizationDenied("case_closed") → CaseClosed 409, sin advisor_forbidden    (R26, R53)
   └─ ServiceUnavailable                 → log authorize_failed → UpstreamError 502 (R28)
2. get_case_contact(case_id) → None ⇒ CaseNotFound 404          # R35 #7, sin cambios
3. gateway.send                → fallo ⇒ UpstreamError 502       # R36 #7, sin cambios
4. add_message("advisor") + add_event("advisor_reply")          # R32 #7
5. handover.assign             → fallo (incl. 403 por carrera perdida, R38) ⇒ assign_failed, 200   # R34 #7, R35
```

Orden «autorizar → enviar → guardar → assign», como pide la #14. Con `403`, `404`, `409` o `502`
en el paso 1 no se envía, no se guarda el mensaje, no hay `advisor_reply` y no se llama a
`assign`.

**Decidido por el humano (2026-10-31), decisión 1 (C5 de la #13):** el `409 case_closed` de
`authorize` se propaga tal cual (`CaseClosed`), no se registra `advisor_forbidden` ni hay línea
de log `advisor_forbidden` (R53). El evento `advisor_forbidden` queda solo para los `403`.

`_record_forbidden(case_id, advisor_id, adapters)` (solo para `forbidden`): busca el contacto
con `get_case_contact`; si existe, `add_event(contact.id, "advisor_forbidden",
f"case:{case_id} advisor:{advisor_id} code:forbidden", clock())` (R29); si no, solo
`logger.warning("advisor_forbidden case_id=%s advisor_id=%s", ...)` (R30). La tabla `events`
exige `contact_id` y el registro completo siempre está en handover (R19), así que no se inventa
un contacto. Ningún log incluye `req.text` (R31).

### 4.3 Cliente HTTP (`adapters/handover.py`)

```python
class HandoverClient(Protocol):
    def request(self, req: HandoverRequest) -> HandoverResponse: ...
    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...
    def authorize(
        self, case_id: str, advisor_id: str, action: CaseAuthorizeAction
    ) -> CaseAuthorizeResponse: ...
```

`HttpHandoverClient.authorize`, mismo estilo que `assign` (URL con `quote(case_id, safe='')`,
cabecera, `timeout`):

1. Error de red o de tiempo (`httpx.HTTPError`) → `ServiceUnavailable` (R34).
2. Código `403`/`404`/`409`: si el cuerpo valida como `ErrorResponse` y `error` es
   respectivamente `forbidden`/`not_found`/`case_closed` → `AuthorizationDenied(error)` (R33);
   si no → `ServiceUnavailable` (R34).
3. Código `200`: `CaseAuthorizeResponse.model_validate(...)`; si no valida (incluido `allowed`
   distinto de `true`, que el contrato hace `Literal[True]`) o `case_id` no coincide con el
   pedido → `ServiceUnavailable` (R34).
4. Cualquier otro código (`401`, `422`, `5xx`, …) → `ServiceUnavailable` (R34).

Log: `handover_authorize_error code=<tipo o status>`, sin cuerpo ni texto.

`FakeHandoverClient` gana, sin cambiar sus parámetros actuales ni sus valores por defecto:

```python
def __init__(self, status="notified", fail=False, fail_assign=False,
             authorize_error: str | None = None, fail_authorize: bool = False) -> None:
    ...
    self.authorized: list[tuple[str, str, str]] = []

def authorize(self, case_id, advisor_id, action) -> CaseAuthorizeResponse:
    self.authorized.append((case_id, advisor_id, action))
    if self.fail_authorize: raise ServiceUnavailable("Handover caído")
    if self.authorize_error: raise AuthorizationDenied(self.authorize_error)
    return CaseAuthorizeResponse(allowed=True, case_id=case_id)
```

Por defecto autoriza: los tests de la #7 del orquestador siguen igual (ver §6).

## 5. Excepciones

| Servicio | Excepción | Código | HTTP | Nueva |
|---|---|---|---|---|
| handover | `AdvisorForbidden(DomainError)` | `forbidden` | 403 | sí |
| handover | `CaseNotFound`, `CaseClosed` | `not_found`, `case_closed` | 404, 409 | no (reutilizadas) |
| orchestrator | `AdvisorForbidden(DomainError)` | `forbidden` | 403 | sí |
| orchestrator | `CaseClosed(DomainError)` | `case_closed` | 409 | sí |
| orchestrator | `CaseNotFound`, `UpstreamError` | `not_found`, `upstream_error` | 404, 502 | no (reutilizadas) |
| orchestrator | `AuthorizationDenied(Exception)` | interna | — | sí |
| orchestrator | `ServiceUnavailable` | interna | — | no |

Dos clases con el mismo nombre en dos servicios es lo esperado: un servicio nunca importa a otro
(principio 1).

## 6. Tests existentes que cambian (R36)

Regla: ningún test se elimina; ninguna aserción se relaja. Los únicos cambios son estos:

| Test | Por qué cambia | Cambio exacto | Aserciones |
|---|---|---|---|
| `services/handover/tests/test_cases.py::test_assign_already_assigned_keeps_first_advisor` | La segunda asignación la hace `"333"`, que ahora es «otro asesor» → `403` (R12) | La segunda llamada pasa de `_assign(env, "case-1", "333")` a `_assign(env, "case-1", "111")` (mismo asesor, S11/R13) | Idénticas (`200`, cuerpo, `("111", START)`). El caso «otro asesor» lo cubre el test nuevo `test_assign_assigned_case_by_other_advisor_returns_403`, que además comprueba que el caso no cambia |
| `services/handover/tests/test_repository.py::test_postgres_repository_connects_lazily_and_once` | `_SCHEMA` gana un `CREATE TABLE` (la #11 dejó 3; el `ALTER` de la #12 no cuenta) | `== 3` → `== 4` | Sigue siendo una igualdad exacta |
| `services/handover/tests/test_timeout_races.py` (de la #12): `test_assignment_during_timeout_send_is_kept` (T15 #12), `test_close_during_timeout_send_is_kept` (T16 #12) y cualquier otra llamada a `assign_case`/`close_case` del archivo | `assign_case` y `close_case` ganan el parámetro `settings` | Solo se pasa `env.settings` en esas llamadas. Los asesores que usan (`"222"` en T15) están en `ADVISORS = [111, 222, 333]` y los casos están sin asignar, así que la semántica no cambia (y las escrituras condicionales dan el mismo resultado, §3.3). Si alguna llamada usara un asesor fuera de `ADVISORS`, pasa a `"111"` y se documenta en `progress/impl_autorizacion_asesores.md` | Idénticas |
| `services/handover/tests/test_security.py` (`ROUTES`, `INVALID_BODIES`, `test_handover_routes_without_token_return_401_and_change_nothing`) | La ruta nueva hereda R24/R25 de la #7 | Entradas nuevas en las listas; una aserción añadida `env.repo.denials == []` | Solo se amplían |
| `services/orchestrator/tests/test_case_reply.py::test_http_handover_client_assign_raises_on_error_status` | `assign` puede responder `403` (R35, R38) | `[404, 409, 500]` → `[403, 404, 409, 500]` | Solo se amplía |

`services/handover/tests/test_cases.py::test_close_marks_closed_and_records_advisor` **ya no
cambia** (antes figuraba en esta tabla): crea `case-assigned` sin `advisor_id` y lo cierra
`"333"`. Con la decisión 7 ese caso es huérfano (§3.1, `advisor_id` nulo) y cualquier asesor
registrado lo puede cerrar (R47); `close_if_still_allowed` recibe `allowed_assignee=None` y
escribe (R54), así que el test pasa tal cual. El cierre por el asesor asignado (R16) lo cubre el
test nuevo T24.

`services/handover/tests/test_startup.py` (de la #10) solo **gana** tests (T72-T74); los
existentes no ejecutan el `lifespan` (no usan `with TestClient`) y no cambian.

**Asesores no registrados en tests de la #7** (acceptance de la #14):

- **Handover:** ninguno. Todos los tests usan `111`, `222` o `333`, que están en
  `ADVISORS = [111, 222, 333]` de `tests/conftest.py`. El test de la tabla cambia por las reglas
  de «otro asesor», no por el registro.
- **Orquestador:** usa `"555"`, pero el orquestador nunca lee `ADVISOR_CHAT_IDS` (principio 1):
  quien decide es el `FakeHandoverClient`, que por defecto autoriza. Ningún test del
  orquestador cambia de fixture; los casos de denegación usan `authorize_error`.
- `test_close_is_idempotent_and_keeps_first_closure` (`222` cierra un caso cerrado por `111`)
  sigue en `200` por C2 (S8). `test_assign_closed_case_returns_409`,
  `test_assign_and_close_unknown_case_return_404`, `test_assign_marks_case_assigned` y
  `test_assign_timed_out_case` no cambian.

## 7. Limitación aceptada por el humano: identidad por HTTP

La autorización por HTTP con `SERVICE_TOKEN` **no impide que un proceso que ya tenga ese token
suplante un `advisor_id` registrado**. Handover comprueba que el `advisor_id` declarado es un
asesor y que el caso le corresponde, pero no puede saber quién escribió la petición: cualquiera
que conozca `SERVICE_TOKEN` (y, por tanto, puede llamar a cualquier ruta interna) puede declarar
el id de un asesor real. Esta feature reduce el riesgo a «quien tiene el token», no a «quien
dice ser asesor». La identidad por persona llega con la #16 (el `advisor_id` es el remitente del
webhook validado con `TELEGRAM_WEBHOOK_SECRET`, nunca un id escrito en el mensaje) o con el
panel y la verificación de cuentas. Ya figura en S12 de `CONTRATOS.md` (#13, R25).

## 8. Decisiones

### 8.1 Decididas por el humano (2026-10-31) en la #13

Alineadas con `specs/contrato_autorizacion_asesores/design.md` §7 y con S12 publicado.

| Id | Decisión | Origen | Requirements |
|---|---|---|---|
| D1 | Precedencia: no registrado → `403` (antes que nada) → inexistente `404` → `closed` `409` (reply/assign; `200` en `close`) → asignado a otro `403` (salvo huérfano en `close`, D11) | C1 | R4, R5, R6, R7, R11, R14 |
| D2 | `close` mantiene S8: asesor registrado sobre caso `closed` → `200` sin cambios; `authorize` con `action=close` sobre `closed` → `409` | C2 | R6, R18 |
| D3 | El fallo cerrado reutiliza la fila `502 upstream_error` existente de `/cases/{id}/reply` | C3 | R28 |
| D4 | `assign` de otro asesor sobre `assigned` → `403`; del mismo → `200` sin cambios (S11) | R26 de la #13 | R12, R13 |
| D6 | El orquestador autoriza **antes** de buscar el vínculo caso-contacto: un no asesor recibe `403` aunque el caso no exista. R35 de la #7 sigue cumpliéndose | C6 | R23 |

### 8.2 Decididas por el humano (2026-10-31) para esta feature

**D5 — `reply` sobre un caso `closed`.** *Decidido por el humano (2026-10-31), decisión 1 (C5 de
la #13).* El orquestador propaga `409 case_closed` de `authorize` (excepción nueva `CaseClosed`
del orquestador) y no envía nada al cliente. Un `409` **no** genera `advisor_forbidden` (ni
evento ni línea de log); ese evento queda solo para los rechazos `403`. Sustituye a la versión
anterior de D5 («traducir a `403 forbidden`»), descartada por la #13 (§6 de su design).
Requirements: R26 (reescrito), R29 y R30 (reescritos: solo R25), R53 (nuevo).

**D10 — Carrera autorizar → enviar → asignar.** *Decidido por el humano (2026-10-31), decisión 2:
opción (b) de la D1 de la #12.*

- *Ventana real.* Va desde el `authorize` del orquestador, pasa por el `POST /send` al gateway
  (hasta `HTTP_TIMEOUT_SECONDS=10`) y termina en la escritura de `assign_case`. Dos asesores
  registrados que contestan al mismo aviso de un caso sin asignar dentro de esa ventana pasan los
  dos el `authorize`, y sus dos respuestas llegan al cliente.
- *Aceptado por el humano:* en esa carrera la respuesta del segundo asesor puede haber llegado
  al cliente antes de que falle su asignación; queda registrada como `assign_failed` (R35).
- *Resuelto:* asignación condicional (`WHERE status IN ('open','timed_out')` con `RETURNING`;
  el mismo asesor se resuelve sin escribir) y cierre condicional, en el repositorio falso y en
  PostgreSQL (§3.3). El `assign` de otro asesor que pierde la carrera recibe `403` sin escribir y
  deja un registro de denegación (R38). Ya no hay reasignación silenciosa.
- *Cierre contra asignación (decidido; antes duda 6 del informe de revisión):* una carrera no
  puede cerrar un caso que ya quedó asignado a otro asesor. El cierre condicional exige en la
  misma sentencia el estado o el asesor autorizado: `status IN ('open','timed_out') OR
  (status = 'assigned' AND advisor_id = <asesor de la petición>)` (R41) o, para un huérfano, el
  `advisor_id` huérfano leído, también nulo (R54), con `RETURNING`. Si no escribe, se relee y se
  responde según §3.2: ya cerrado → `200` por S8 (R42); asignado a otro → `403` + denegación
  (R55). Sustituye al `WHERE status <> 'closed'` de la versión anterior del spec.
- Requirements: R35 (resuelto), R37-R43, R54, R55.

**D7 — Qué cuenta como denegación en handover.** *Decidido por el humano (2026-10-31),
decisión 3.* Solo los `403` se registran en `handover_denials`, incluido el `403` por carrera
perdida en `assign` (R38) y en `close` (R55). `404`, `409`, `401`, `422` y `500` no son
denegaciones. Mismo criterio que el evento `advisor_forbidden` del orquestador (decisión 1).
Requirements: R19, R20, R38, R55.

**D8 — Fallo al guardar la denegación.** *Decidido por el humano (2026-10-31), decisión 3.*
Handover responde `500 internal_error` sin modificar el caso (no un `403` sin registro). Para el
orquestador un `500` de `authorize` es fallo cerrado (`502`, sin envío). Es intencionadamente la
política contraria a S2 de la #11 (allí la auditoría no bloquea). Requirements: R22.

**D9 — Denegación sin contacto vinculado en el orquestador.** *Decidido por el humano
(2026-10-31), decisión 3.* Solo queda la línea de log `advisor_forbidden` del orquestador (y el
registro de handover); no se inventa un contacto (`events.contact_id` es obligatorio).
Requirements: R30.

**D12 — Dónde se cuentan los huérfanos.** *Decidido por el humano (2026-10-31), decisión 4.* En
el `lifespan` (arranque del servidor), no en `create_app`, que corre al importar
`handover.main` y no debe abrir la conexión (§3.4). Requirements: R49, R52.

**D13 — Fallo del recuento al arrancar.** *Decidido por el humano (2026-10-31), decisión 4.*
Log `WARNING orphan_cases_check_failed` sin ids ni texto de la excepción, y el servicio arranca
igual (§3.4). Requirements: R51.

**Conexión compartida.** *Decidido por el humano (2026-10-31), decisión 5 (D2 de la #12):*
`threading.Lock` alrededor de `_run` en `PostgresCaseRepository` de handover, en esta feature
(§3.5). Requirements: R44, R45.

**Candado del orquestador.** *Decidido por el humano (2026-10-31), decisión 6:* el
`PostgresRepository` del orquestador recibe la misma protección en la feature #18
`candado_repositorio_orquestador`, previa a la #16. Aquí solo se referencia; sin R ni tasks.

**D11 — Casos `assigned` de un asesor retirado de `ADVISOR_CHAT_IDS`.** *Decidido por el humano
(2026-10-31), decisión 7: opción C + procedimiento A de
`progress/specreview_conversacion_cliente_asesor.md` §6, publicada por la #17 en S12.*

- Caso huérfano: `assigned` con `advisor_id` nulo o fuera de `ADVISOR_CHAT_IDS` (texto de S12).
- Cualquier asesor registrado puede **cerrar** un caso huérfano: `authorize(close)` responde
  `200` (R46) y `close` lo cierra conservando el `advisor_id` del retirado (R47), con la
  escritura condicional de R54.
- Nadie puede responderlo ni asignárselo: `authorize(reply)` y `assign` → `403` (R48, R12).
- El asesor retirado recibe `403` en todo (paso 1, R4, T14).
- Procedimiento A: antes de retirar a un asesor, este cierra sus casos; handover registra al
  arrancar cuántos casos huérfanos hay, sin ids (R49-R52).
- La #14 no edita `contracts/`.
- Requirements: R7 y R15 (reescritos para excluir al huérfano), R46-R52, R54.

### 8.3 Pendientes del humano — REVISAR

Ninguna. D7, D8, D9, D12 y D13 pasan a §8.2 como decididas por el humano (2026-10-31).

### 8.4 Dudas abiertas (no tomadas; no se inventan)

1. **Riesgos (d) y (e) de la #12** (reutilización de un caso que se cierra a mitad, dentro de
   `_process_handover`; dos `POST /handover` simultáneos del mismo contacto): no los resuelve
   esta feature ni tocan sus rutas. Falta decidir si van en la #12 o en una feature propia.

Ninguna duda de `docs/proyecto.md` §12 se toca; no hay variables de entorno nuevas.

### 8.5 Qué deben reflejar otras features (no se editan aquí)

- **#12 (`vencimiento_automatico`):** su D1 queda resuelta con la opción (b) en la #14 (riesgos
  (a), (b) y (c) y la reasignación silenciosa; §3.3); su D2 queda resuelta para handover con el
  candado de la #14 (riesgo (f) en handover) y para el orquestador con la #18. La frase
  «`update_case` se mantiene (lo usan `assign_case` y `close_case`)» deja de ser cierta tras la
  #14 (se mantiene, pero sin uso en `domain.py`). T15/T16 de la #12 siguen válidos con las
  escrituras condicionales; la #14 solo les añade `env.settings` (T7b). Los riesgos (d) y (e)
  siguen abiertos.
- **#16 (`conversacion_cliente_asesor`):** con C5, `reply_to_case` lanza `CaseClosed` (`409
  case_closed`) para un caso cerrado, no `AdvisorForbidden`; el manejador de `/responder` debe
  tratarlo aparte y **no** registrar `advisor_forbidden` por un `409` (R14, Rec. 2, D6, T24 y
  T33 de la #16; `specs/contrato_autorizacion_asesores/design.md` §9). `FakeHandoverClient`
  con `authorize_error="case_closed"` produce ahora `CaseClosed`. `/cerrar` debe permitir a
  cualquier asesor registrado cerrar un caso huérfano (R46, R47). `POST /cases/{id}/close` puede
  responder `403` a un cierre que pierde la carrera contra una asignación ajena (R55). El
  candado del `PostgresRepository` del orquestador llega con la #18 (previa a la #16). La
  diferencia de `/cerrar` sobre un caso `closed` respecto a `POST /cases/{id}/close` (S8) sigue
  siendo trabajo de la #16 (`progress/specreview_conversacion_cliente_asesor.md`, cambio 3).
- **#17 (`contrato_cierre_casos_huerfanos`, `done`):** S12 ya recoge lo que implementan R46-R48,
  el `advisor_id` nulo y el procedimiento A con el recuento de R49-R50. Nada pendiente.
- **#18 (`candado_repositorio_orquestador`):** mismo patrón que §3.5 (R44, R45) en el
  orquestador; la #14 no la toca.

## 9. Alternativas descartadas

- **Que el orquestador lea `ADVISOR_CHAT_IDS` y el estado del caso y decida él.** Descartada:
  principio 1 de `docs/architecture.md` §3; handover es el único dueño de los casos y de la lista
  de asesores. Además habría dos copias de la lista que pueden divergir.
- **Fallar abierto (enviar la respuesta si handover no contesta).** Descartada: decisión del
  humano (falla cerrado) y abriría la puerta a saltarse la autorización tumbando handover.
- **Autorizar y asignar en una sola llamada, o asignar antes de enviar (opción (c) de la
  carrera).** Descartada por el humano (decisión 2 eligió la (b)): cambiaría la semántica de una
  ruta que la #13 define como consulta y el orden de la #7 (R33), y si `POST /send` falla el caso
  quedaría asignado sin respuesta.
- **`SELECT ... FOR UPDATE` o versión optimista para la asignación.** Descartadas: la primera
  mantiene una transacción abierta entre lectura y escritura y no se reproduce con el repositorio
  falso; la segunda cambia `Case`, `_CASE_COLUMNS` y todos los tests de filas (mismos motivos que
  las alternativas 3 y 4 de la #12).
- **Cierre condicional con solo `WHERE status <> 'closed'`** (versión anterior de este spec).
  Descartada por el humano (decisión 2, 2026-10-31): en la ventana entre lectura y escritura
  dejaba cerrar un caso que ya había quedado asignado a otro asesor.
- **`advisor_id IS NOT DISTINCT FROM %s` en una sola variante de SQL.** Descartada por
  prudencia: con un `None` como parámetro pg8000 envía un `NULL` sin tipo y Postgres tiene que
  inferirlo; dos variantes de texto (`= %s` / `IS NULL`) elegidas en Python son igual de
  parametrizadas y no dependen de esa inferencia.
- **Reintentar el cierre si la relectura muestra un estado permitido.** Descartada: con las
  reglas actuales ese estado no es alcanzable (§3.3) y un reintento abre la puerta a bucles; se
  falla cerrado con `403` (R55).
- **Una conexión por petición o un pool en lugar del candado.** Descartadas: más código y
  dependencias para un tráfico bajo; el humano eligió el candado (D2 de la #12).
- **Contar los huérfanos en `create_app`.** Descartada: abriría la conexión al importar
  `handover.main` (R52).
- **Registrar las denegaciones en la tabla `handover_notifications` o en la de la #11.**
  Descartada: mezcla conceptos (avisos y solicitudes de traspaso) y crearía una dependencia con
  la #11, que el leader pidió evitar.
- **Normalizar `advisor_id` (quitar ceros o espacios) antes de comparar.** Descartada: S6 fija el
  chat_id en decimal; aceptar variantes amplía lo que pasa por «asesor» sin necesidad.

## 10. Dependencias

Ninguna nueva. `lazaro_contracts` con los modelos de la #13 (y S12 de la #17); `httpx`,
`pydantic`, `pg8000` y `fastapi` ya están en los `requirements.txt` de ambos servicios;
`threading` y `contextlib` son de la biblioteca estándar.

**Reutilización de código externo:** ninguna. Lo que hace falta (comprobaciones puras, `UPDATE
... RETURNING` condicional, `threading.Lock`, `lifespan` de FastAPI) es poco código y sigue
patrones que ya existen en el repo (#11, #12). Helpdock (AGPL-3.0) se descartó como base
(`docs/proyecto.md` §4, D3) y `docs/architecture.md` prohíbe copiarlo o adaptarlo de cerca: no
se toma nada de él. No se propone reutilizar código MIT/Apache.
