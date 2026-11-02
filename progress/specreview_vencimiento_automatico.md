# Spec review — vencimiento_automatico (feature #12)

**Veredicto:** SPEC_CHANGES_REQUESTED

Revisión pedida por el leader con la feature en `blocked` (decisión del humano). No se toca
`feature_list.json` ni `specs/`.

## Cobertura del acceptance
- [x] A1 (script de llamada única: `HANDOVER_URL`, `SERVICE_TOKEN`, salida 0 con 200 y ≠ 0 si no) → R1-R5.
- [x] A2 (`--intervalo`, por defecto `CHECK_TIMEOUTS_INTERVAL_SECONDS`; fallo con código en el log y el bucle sigue) → R6-R10.
- [x] A3 (token nunca en log ni salida) → R11.
- [x] A4 (`timeouts_worker` sin puertos; variables nuevas en `.env.example`) → R13-R16.
- [x] A5 (`open` → `timed_out` condicional; no se pierde asignación ni asesor) → R17, R19-R22, R27.
- [x] A6 (dos ejecuciones simultáneas no envían dos veces) → R17, R18, R24, R27, R28.
- [x] A7 (reutilización simultánea con asignación no la deshace) → R25, R26.
- [x] A8 (humano: 60 s configurable) → R7, R16.
- [x] A9 (humano: Render PENDIENTE; no se despliega) → design «Alcance»; ninguna task toca `.github/` ni crea `render.yaml`.
- [x] A10 (tests listados) → T23-T26 (única OK/fallida, 401), T32 (bucle tras fallo, sueño inyectado, `max_rounds`), T33 (token), T15-T17 (asignación-vencimiento), T20-T21 (asignación-reutilización), T13 (dos vencimientos).

## Fidelidad a las decisiones del humano (2026-10-31)
- [x] Intervalo 60 s configurable; script + servicio de Compose; nada de Render. El design (líneas 10-11, 287-299, 319) deja Render como PENDIENTE y no propone ninguna opción.
- [x] Las decisiones no tomadas por el humano están marcadas «SUPUESTO (no decidido)» (design líneas 310-319): timeout HTTP del script, caducidad de la reclamación, `restart: unless-stopped`, sin reintento rápido.

## Carreras y coherencia con la #7
- [x] **Las transiciones condicionales resuelven las carreras del acceptance.** Reclamar con `UPDATE … WHERE status = %s AND (timeout_claimed_at IS NULL OR timeout_claimed_at <= %s) RETURNING case_id` antes de enviar impide el doble envío entre ejecuciones sanas (R18, T13); `mark_timed_out` con `WHERE status = 'open'` no pisa una asignación o cierre hecho durante el envío (R20-R22, T15-T17); `update_last_messages` no reescribe `status`/`advisor_id` en la reutilización (R25, T20) y la rama `no_advisors` usa `mark_timed_out` (R26, T21).
- [x] **Coherente con la #7 (si el envío falla, el caso queda `open`).** Durante el envío el caso sigue `open`; si `send` falla, `release_timeout_claim` deja el caso `open` y sin marca (R23) y el test existente `test_check_timeouts_send_failure_keeps_case_open` sigue pasando sin cambios (T11, T18).
- [x] La garantía «como mucho una vez» se limita honestamente a ejecuciones sanas; la reclamación huérfana (proceso muerto) se retoma tras `HANDOVER_TIMEOUT_SECONDS` (R24) con posible segundo aviso, documentado como «al menos una vez» (design líneas 218-222).
- [x] Tests de carrera deterministas, sin hilos, con `HookGateway`/`HookRepository` y reloj inyectado.

## Script y `SERVICE_TOKEN`
- [x] El token solo va en el encabezado; los logs usan el código HTTP, el campo `error` del cuerpo o el nombre de la clase de excepción, nunca `str(exc)` ni la petición (design líneas 89-106). T33 cubre llamada única, bucle, error de red con el token en el mensaje e intervalo inválido, con `caplog` a DEBUG y `capsys`.
- [x] `logging` en lugar de `print`; sin `lazaro_contracts`; `httpx` ya está en `services/handover/requirements.txt`; `.dockerignore` no excluye `scripts/`, así que el `COPY` de R15 funciona.

## `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS`
- [x] **Justificada.** Sin ella, `httpx` usa 5 s por defecto, menos que un solo envío al gateway (`HTTP_TIMEOUT_SECONDS=10`): con un par de casos vencidos el script marcaría fallos espurios. Reutilizar `HTTP_TIMEOUT_SECONDS` no sirve (es el timeout por salto que comparten todos los servicios y vale 10). Un valor fijo en el código violaría `docs/architecture.md` §3.5. El acceptance A4 prevé variables nuevas. Además, gracias a la reclamación, un timeout del cliente no provoca dobles envíos aunque handover siga procesando. Está marcada SUPUESTO (120 s).
- [ ] **Comportamiento sin requirement:** el design (líneas 87-88) dice que un valor no numérico o ≤ 0 de esta variable termina «con la misma salida que R8», pero ningún `R<n>` ni test lo cubre (R8 solo habla del intervalo). Ver cambio 2.

## Las dos carreras fuera de alcance (`assign` contra `close`, `assign` que reescribe `last_messages`)
- [x] **No deben entrar en esta feature sin que el humano amplíe el acceptance.** A5-A7 solo piden proteger la asignación frente al vencimiento y a la reutilización; hacer condicionales `assign_case` y `close_case` sería añadir comportamiento no pedido. El spec hace bien en dejarlas fuera y señalarlas.
- [ ] **Pero la lista de riesgos residuales está incompleta** (design líneas 287-299). Falta, al menos:
  - (c) `close` contra `assign`: `close_case` lee el caso `open`, un `assign` simultáneo escribe `assigned`, y `close_case` reescribe el caso entero con su lectura antigua (`domain.py` líneas 161-170): queda `closed` **sin `advisor_id` ni `assigned_at`**, se pierde quién lo atendió.
  - Reutilización de un caso que se cierra entre `find_active_case` y `update_last_messages`: se escriben mensajes en un caso `closed` y se avisa a los asesores con el `case_id` de un caso cerrado (la respuesta es `notified`).
  - La conexión Postgres compartida: `PostgresCaseRepository` usa una sola conexión pg8000 por proceso (`repository.py` líneas 129-142) y las rutas síncronas de FastAPI corren en un pool de hilos. `pg8000.dbapi.threadsafety` es `1` (comprobado en el `.venv`): la conexión no se puede compartir entre hilos. Con el worker llamando cada 60 s, `check-timeouts` coincidirá con `assign`/`close`/`handover` en el mismo proceso. La atomicidad que argumenta el design (líneas 172-176, «dos transacciones concurrentes») supone conexiones distintas. El riesgo existía en la #7 y no rompe la garantía de no-doble-envío (un error de protocolo acaba en `500`, no en un envío), pero la #12 lo hace frecuente y debe quedar escrito. Ver cambio 4.

## EARS estricto
- [x] Un solo `DEBE`/`NO DEBE` por requirement. R12-R16, R27-R28 usan sujeto concreto (`El script DEBE`, `docker-compose.yml DEBE`, `PostgresCaseRepository DEBE`), aceptado por precedente (#1, #9).
- [ ] **R8 ambiguo** (`requirements.md` líneas 48-51): «el intervalo (de la opción o de `CHECK_TIMEOUTS_INTERVAL_SECONDS`)» no dice si una variable inválida hace fallar también la **llamada única**, donde el intervalo no se usa (p. ej. un futuro Render Cron Job con la variable mal puesta). T30 prueba «por variable» sin precisar el modo. Ver cambio 3.

## Verificable
- [x] Cada R1-R28 tiene test nombrado (T5-T7, T12-T21, T23-T34, T38-T41), salvo el hueco del cambio 2.

## Diseño
- [x] Capas: decisiones en `domain.py` (`check_timeouts`, `open_case`), SQL en `adapters/repository.py`; el script es un cliente HTTP con transporte y sueño inyectables.
- [x] SQL parametrizado: cada escritura condicional es un único `UPDATE` con `%s` y el estado como parámetro (R27, T5). Reloj inyectado para `now` y `stale_before`.
- [x] Sin contratos nuevos (la ruta y su respuesta no cambian), sin dependencias nuevas.
- [x] Proceso nuevo justificado según `docs/architecture.md` §1 (design líneas 111-139): sin puertos, sin paquete, misma imagen.
- [x] 6 alternativas descartadas con motivo (líneas 267-285).
- [ ] **Cambio de un test de la #7 no declarado como tal.** T4 modifica `test_postgres_repository_uses_parameters_only` (`test_repository.py` líneas 60-83). El cambio es inevitable: la sentencia `ALTER TABLE … ADD COLUMN IF NOT EXISTS` no lleva parámetros y fallaría el `assert params` de la línea 81 si no se filtra; además cambia el `len(statements) == 6` de la línea 76. No lo debilita si solo se excluye el DDL, pero el acceptance de la #12 (a diferencia del de la #10) no autoriza cambiar tests de la #7. Debe figurar en «Supuestos a confirmar» con el cambio exacto (filtro y nuevo recuento), como hizo la #10. Ver cambio 5.

## Coherencia con #10 y #11 (orden 10 → 11 → 12)
- [ ] **Referencias desfasadas respecto a la #11.** El design (líneas 227-235) y T9 modifican «`open_case`», y la «Nota de coordinación con la #11» (líneas 301-308) dice que «la #11 no debe volver a usar `update_case` en la reutilización», como si la #11 fuera después. Con el orden 10 → 11 → 12, cuando se implemente la #12 la lógica de reutilización y de `no_advisors` vivirá en `_process_handover` (design de la #11, líneas 101-106 y 152-154), y `open_case` será el envoltorio del registro. Ver cambio 1.
- [x] `_SCHEMA` final: `CREATE handover_cases`, `CREATE handover_notifications`, `CREATE handover_requests` (#11), `ALTER handover_cases` (#12). T7 («después de los `CREATE TABLE`») es compatible; `test_postgres_repository_connects_lazily_and_once` cuenta solo `CREATE TABLE` (3 tras la #11; el `ALTER` no lo altera).
- [x] `conftest.make_env(advisors, repo, gateway)` (T10) no rompe la #10 (su T18 construye `Settings` a mano) ni la #11 (usa `env`/`env_no_advisors`).
- [x] Sin colisión de nombres de archivo de test: `test_startup.py` (#10), `test_requests.py` (#11), `test_timeout_races.py`, `test_vencer_casos.py`, `test_worker_compose.py` (#12).
- [x] La #10 no afecta al worker: el script lee `os.environ` y no importa `handover.config`. Si `ADVISOR_CHAT_IDS` es inválida, handover no arranca y el worker solo registrará `ConnectError` cada 60 s (R9/R10), sin exponer nada.

## Tasks
- [x] T1-T42 en `[ ]`, en orden (repositorio → dominio → carreras → script → compose/config → cierre), cada una con sus `R<n>`; entre todas cubren R1-R28.

## Nada peligroso
- [x] No borra datos (el `ALTER` solo añade una columna nullable), no usa la red en tests, no toca archivos fuera del repo, no despliega.

## Cambios requeridos
1. **Alinear con la #11.** En design «`open_case` (domain.py)» y en T9, cambiar el punto de modificación a `_process_handover` (tal como lo deja la #11); reescribir la «Nota de coordinación con la #11» para el orden 10 → 11 → 12 (la #12 llega segunda: suma su `ALTER` a `_SCHEMA` tras el `CREATE` de `handover_requests`); añadir `tests/test_requests.py` a la lista de T11 de tests que deben pasar sin cambios.
2. **Cubrir `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` inválida** con un requirement propio (p. ej. «SI `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` no es un número mayor que 0 ENTONCES el script DEBE terminar con un código de salida distinto de 0 sin enviar ninguna petición.») y su test (ampliar T34 o uno nuevo), o quitar ese comportamiento del design.
3. **Precisar R8**: decir si `CHECK_TIMEOUTS_INTERVAL_SECONDS` inválida hace fallar solo el modo bucle o también la llamada única, y ajustar T30. Recomiendo que solo afecte al modo bucle (la llamada única no usa el intervalo).
4. **Completar «Fuera de alcance (riesgos residuales)»** con la carrera `close` contra `assign` (se pierden `advisor_id` y `assigned_at`), la reutilización de un caso que se cierra a mitad, y la conexión pg8000 compartida entre hilos (`threadsafety = 1`). Corregir la frase de las líneas 172-176 para que diga que la atomicidad descrita se da entre conexiones distintas.
5. **Declarar el cambio del test de la #7** `test_postgres_repository_uses_parameters_only` en «Supuestos a confirmar»: qué filtro cambia (`not sql.startswith(("CREATE", "ALTER"))`), el nuevo recuento y que el resto de aserciones (`%s` = parámetros, `params` no vacío, sin literales entre comillas, texto de cliente solo en parámetros) se mantiene.

## Decisiones para el humano
- **Carreras de `assign_case`/`close_case`** (`assign` contra `close`, `close` contra `assign`, `assign` que reescribe `last_messages`): no entran en la #12 sin ampliar su acceptance. Opciones: (a) ampliar la #12 (mismo patrón y la misma infraestructura de tests: `assign` con `WHERE status IN ('open','timed_out')` y `close` con `WHERE status <> 'closed'`, escribiendo solo sus campos; es poco código y elimina `update_case` del dominio); (b) incluirlas en la #14, que reescribe las reglas de asignación y cierre; (c) feature propia. Recomiendo (a) o (b) antes de la #16, porque con la conversación por Telegram las asignaciones y cierres simultáneos serán habituales.
- **Conexión pg8000 compartida entre hilos** (riesgo que viene de la #7): decidir si se protege (candado en `_run` o una conexión por petición) en esta feature o en una aparte.
- **`CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`**: variable nueva y valor por defecto (SUPUESTO).
- **Caducidad de la reclamación = `HANDOVER_TIMEOUT_SECONDS`**: exige que sea mayor que `HTTP_TIMEOUT_SECONDS`; sin variable propia.
- **`restart: unless-stopped`** y **sin reintento rápido** tras un fallo.
- **Render**: sigue PENDIENTE; el script admite llamada única para un Cron Job o GitHub Actions y bucle para un worker.

## Segunda vuelta (2026-10-31)

**Veredicto:** SPEC_APPROVED (solo quedan decisiones del humano)

### Cambios requeridos de la primera vuelta
- [x] **Cambio 1 (alinear con la #11).** «Precondición de orden» (design l.34-46) y `tasks.md` l.3; design «`_process_handover` (domain.py, tal como lo deja la #11)» (l.256-267); T9 modifica `_process_handover` y prohíbe tocar `open_case`, `_start_request`, `_finish_request` y `tally`; la nota de coordinación (l.357-372) describe el orden 10 → 11 → 12 y el orden final de `_SCHEMA`; T11 incluye `tests/test_requests.py`.
- [x] **Cambio 2 (`CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` inválida).** R29 (l.70-73) y T34b (parametrizado `0`, `-1`, `abc`, en los dos modos, cero peticiones, el log nombra la variable). T33 añade ese caso para el token.
- [x] **Cambio 3 (precisar R8).** R8 limitado al modo bucle; R30 nueva (la llamada única no valida el intervalo); T30 precisa el modo y añade `--intervalo 30` con la variable inválida; T30b cubre R30. Design l.100-104 coherente.
- [x] **Cambio 4 (riesgos residuales).** Design l.319-355: añadidos (c) `close` contra `assign`, (d) reutilización de un caso que se cierra a mitad y (f) conexión pg8000 compartida (`threadsafety = 1`). La frase de atomicidad (l.197-205) dice ahora «entre conexiones distintas».
- [x] **Cambio 5 (test de la #7).** S1 (l.379) declara el cambio exacto de `test_postgres_repository_uses_parameters_only` (filtro, cuatro llamadas añadidas, 6 → 10) y las aserciones que no cambian; T4 lo aplica «exactamente y nada más»; T42 lo documenta.

### Decisiones del humano no tomadas en silencio
- [x] D1-D6 marcadas **REVISAR (pendiente del humano)** con recomendación (l.381-413). La #12 no se amplía con las carreras de `assign`/`close` ni con el candado de pg8000: quedan como opciones, no como trabajo de esta feature.
- [x] S1 (cambio del test de la #7) marcado REVISAR.
- [x] Render sigue PENDIENTE; ninguna task toca `.github/` ni crea `render.yaml`.

### Nada inventado, sin conflictos
- [x] R29 y R30 cierran comportamiento que ya estaba en el design (lo pidieron los cambios 2 y 3).
- [x] Con la #10 y la #11: ver nota de coordinación; `test_postgres_repository_connects_lazily_and_once` sigue en 3 (el `ALTER` no cuenta).
- [x] Con la #14: la #12 no toca `assign_case`/`close_case` ni `update_case`; la #14 (posterior) los reescribe. La recomendación de D1 (meter las carreras en la #14) no choca con lo que la #14 ya especifica; si el humano la elige, el cambio es de la #14.

### EARS, trazabilidad y tasks
- [x] R1-R30: un `DEBE`/`NO DEBE` cada una; R29 no deseado, R30 de estado.
- [x] Cada R con test (R29 → T34b; R30 → T30b). T1-T42 (con T30b y T34b) en `[ ]`, en orden; T22 cubre R29 y R30; T42 mapea R1-R30.

### Decisiones para el humano (siguen abiertas)
1. D1 — carreras de `assign_case`/`close_case` (a)-(d): ampliar la #12, meterlas en la #14 o feature propia.
2. D2 — conexión pg8000 compartida entre hilos: candado en `_run`, conexión por petición o pool; en esta feature o aparte.
3. D3 — variable nueva `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`.
4. D4 — caducidad de la reclamación = `HANDOVER_TIMEOUT_SECONDS`.
5. D5 — `restart: unless-stopped` y sin reintento rápido.
6. D6 — Render (sigue PENDIENTE).
7. S1 — cambio acotado de `test_postgres_repository_uses_parameters_only` (test de la #7).

## Tercera vuelta (2026-11-01)

**Veredicto:** SPEC_CHANGES_REQUESTED

Revisión del spec contra el código actual de `services/handover` tras la #10, la #11 y la #14
(`done`). El fondo del spec sigue siendo válido e implementable: los métodos nuevos
(`claim_timeout`, `release_timeout_claim`, `mark_timed_out`, `update_last_messages`) no chocan con
`assign_if_unassigned`/`close_if_still_allowed` de la #14; `check_timeouts` (domain.py l.384-398) y
`_process_handover` (l.241-288) siguen usando `update_case` en los tres puntos que la #12 cambia
(l.248, l.286, l.396); el `RETURNING case_id` + `fetch=True` sigue encajando con `_run`, que ahora
toma `self._lock` (repository.py l.237-248); S1 sigue siendo exacto (hoy `len(statements) == 6`,
test_repository.py l.78 → 10). EARS, trazabilidad R1-R30 ↔ T1-T42, acceptance y «nada peligroso»
siguen como en la segunda vuelta. Pero el spec describe un estado del código anterior a la #14 y
contiene datos falsos que confundirían al writer. Cambios bloqueantes (solo texto del spec):

1. **Recuento de `CREATE TABLE`: 3 → 4.** `_SCHEMA` tiene hoy cuatro tablas (`handover_cases`,
   `handover_notifications`, `handover_denials` de la #14, `handover_requests`; repository.py
   l.157-174) y `test_postgres_repository_connects_lazily_and_once` cuenta 4 (test_repository.py
   l.97). Corregir design «Precondición de orden» (l.42-43), «Nota de coordinación» (l.362-367:
   orden final de `_SCHEMA` con `handover_denials` y el `ALTER` al final) y T3/T4 (`sigue en 3` →
   `sigue en 4`; el `ALTER` va tras el último `CREATE TABLE`, no «tras `handover_requests`» como
   única referencia).
2. **Precondición de orden incluye la #14.** Design l.34-46 y `tasks.md` l.3: el código de partida
   es el que deja la #14 (escrituras condicionales en `assign_case`/`close_case`, `threading.Lock`
   en `_run`, tabla `handover_denials`). Añadir que los tests de la #14
   (`test_assign_close_races.py`, `test_authorization.py`, `test_cases.py`) deben pasar sin cambios
   en T11.
3. **D1 y D2 resueltas, no pendientes.** Design l.386-397: marcar D1 como RESUELTA por la #14
   (opción (b); `specs/autorizacion_asesores/design.md` §3.3 y §8.5) y D2 como RESUELTA en handover
   por el candado de la #14 (y en el orquestador por la #18). En «Fuera de alcance» (l.319-355):
   (a), (b), (c) y (f) pasan a «resueltos por la #14»; siguen abiertos solo (d), (e), (g) y (h).
   Quitar la frase de l.321-322 («`assign_case` y `close_case` siguen usando `update_case`») y
   ajustar l.202-205 (la conexión compartida ya está serializada por `_lock`).
4. **Justificación de `update_case` (design l.215).** «se mantiene (lo usan `assign_case` y
   `close_case`)» es falso: tras la #14 no lo usan. Decir que se mantiene en el `Protocol` y en
   las dos implementaciones (lo usa el test de la #7 `test_postgres_repository_uses_parameters_only`,
   l.68) y que tras la #12 queda sin uso en `domain.py`.
5. **`conftest.make_env` ya existe con `repo`/`gateway`** (conftest.py l.81-98, y el fixture
   `env_factory` l.106-109, ambos de la #14). Design l.68-69 y T10: no hay que crearlo; T10 pasa a
   «usar `make_env`/`env_factory` existentes sin modificarlos» (o se elimina, conservando sus R en
   otras tasks: R18/R19/R21/R25/R26 ya están en T13-T21).
6. **Firmas de `assign_case`/`close_case` con `settings` (absorbe T7b de la #14).** Hoy son
   `assign_case(case_id, advisor_id, settings, adapters)` y `close_case(case_id, advisor_id,
   settings, adapters)` (domain.py l.305, l.337). En la sección «Cómo se prueban las carreras» y en
   T14, T15, T16, T20 escribir la llamada completa con `env.settings`, `env.adapters`, y con
   asesores ∈ `ADVISORS` (`111`/`222`/`333`; si no, `_deny` → `AdvisorForbidden`). Añadir que con
   esto la T7b de `specs/autorizacion_asesores/tasks.md` queda cumplida al crear
   `test_timeout_races.py` y que se anote en `progress/impl_vencimiento_automatico.md` (T42).
7. **T21 incompatible con la #14.** Con `make_env(advisors=[])`, `assign_case(..., "222", ...)`
   dentro del `after_find` falla con `403` (`is_registered_advisor` es falso; domain.py l.309-310).
   T21 debe asignar en el `after_find` con el repositorio (`repo.assign_if_unassigned(case_id,
   "222", at)`) o con un `make_env` cuyos asesores incluyan `222` y un gateway que falle todos los
   avisos (para llegar a `no_advisors`). Precisar cuál en T21 y en el design.

No se piden cambios en requirements.md (R1-R30 siguen correctos y verificables) ni en el alcance.
D3-D6 y S1 siguen como en la segunda vuelta.

## Cuarta vuelta (2026-11-01)

**Veredicto:** SPEC_CHANGES_REQUESTED

### Cambios de la tercera vuelta
- [x] **1 (recuento 3 → 4).** Design l.50-52, l.387-394; T3 y T4 («sigue en 4», `ALTER` tras el último `CREATE TABLE`). Coincide con repository.py l.158-169 y test_repository.py l.97, l.315, l.397.
- [x] **2 (precondición incluye la #14).** Design l.34-55, tasks.md l.3; T11 lista `test_requests.py`, `test_assign_close_races.py`, `test_authorization.py`, `test_cases.py`.
- [x] **3 (D1/D2 resueltas).** Design l.350-379 (a, b, c, f resueltos; d, e, g, h abiertos), l.208-218 (serialización por `_lock`), l.410-421.
- [x] **4 (`update_case`).** Design l.228-231; el uso en test_repository.py l.68 es real; domain.py solo lo usa en l.248, l.286, l.396, los tres que cambia la #12.
- [x] **5 (`make_env` existente).** Design l.84-86, T10; conftest.py l.81-114 coincide.
- [x] **6 (firmas con `settings`).** Design l.292-311, tasks.md l.29, T14-T16, T20; asesor `"222"` ∈ `ADVISORS` (conftest.py l.19); T7b de la #14 anotada en T42.
- [x] **7 (T21).** Design l.304-308 y T21: `repo.assign_if_unassigned(case_id, "222", env.clock())` coincide con la firma (repository.py l.98); con `advisors=[]` el bucle de avisos de `_process_handover` (domain.py l.264) no envía y se llega a `no_advisors`.

### Nuevo hallazgo bloqueante (contra el código actual)
- [ ] **S1/T4 no es el único cambio necesario en `test_repository.py`.** El helper `_statements` de la #14 (test_repository.py l.169-170) filtra solo `not sql.startswith("CREATE")`, y `_connection` ejecuta todo `_SCHEMA` con el cursor falso (repository.py l.231-232; el cursor lo registra en `conn.log`, test_repository.py l.27-28). Con el `ALTER` en `_SCHEMA`, estos tests de la #14 y la #11 fallan:
  - `test_postgres_repository_add_denial_uses_parameters_only` (l.182-187): `len(statements) == 1` pasa a 2 y `statements[0]` es el `ALTER` (sin parámetros, falla `params == (...)`).
  - `test_postgres_request_methods_use_parameters_only` (l.433-436 y l.444-445): `len == 1` / `len == 2` pasan a 2 / 3, y `statements[0]` deja de ser el `INSERT`.
  Los que usan `_statements(conn)[-1]` (l.206, l.224, l.361, l.374) no fallan.
  S1 dice «Cambio exacto y único», T4 dice «y nada más» y design l.396-398 / T11 exigen que los tests de la #11 y la #14 pasen sin cambios: el writer se encontraría con tests rojos y una prohibición contradictoria.

### Cambio requerido
1. En design S1 (l.406), T4 y T42, declarar también el cambio del helper `_statements` (test_repository.py l.169-170) a `not sql.startswith(("CREATE", "ALTER"))`, indicando que con él los tests de la #14 y la #11 que lo usan pasan sin tocar sus aserciones. Ajustar la frase «Cambio exacto y único» y la de l.396-398 en consecuencia (alternativa válida: un helper común usado por ambos filtros). No cambia requirements.md ni el alcance.

D3-D6 y S1 siguen pendientes del humano como en la segunda vuelta.

## Quinta vuelta (2026-11-01)

**Veredicto:** SPEC_APPROVED

### Cambio de la cuarta vuelta
- [x] **S1 parte (B), helper `_statements`.** Design l.411 (S1, ahora «Cambios exactos, en dos puntos»: (A) test de la #7, (B) filtro de `_statements` a `not sql.startswith(("CREATE", "ALTER"))` o helper común) y l.397-403 (los tests de la #11/#14 que usan `_statements` pasan sin tocar aserciones; único cambio en código de test de la #11/#14). T4 incluye (B) y ya no dice «y nada más»; T11 sustituye «sin cambios» por «con el único ajuste del helper `_statements` de T4 (S1 B)» para `test_repository.py`; T42 documenta (A) y (B). Coincide con el helper actual (test_repository.py l.169-170).

### Regresiones
- Ninguna: T3 (orden de `_SCHEMA`), recuento de `CREATE TABLE` en 4, precondición #14 y T7 (comprueba el `ALTER`, que debe leer `conn.log` directamente, no `_statements`) siguen coherentes. Las 44 tasks siguen en `[ ]`; requirements.md no cambia.

D3-D6 y S1 siguen marcados para revisión del humano, como en la segunda vuelta; no bloquean.
