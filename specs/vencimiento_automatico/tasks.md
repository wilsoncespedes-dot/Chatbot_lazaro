# Tasks — vencimiento_automatico

Precondición: la #10, la #11 y la #14 están `done` (orden 10 → 11 → 14 → 12, ver design «Precondición de orden»). El código de partida es el que deja la #14: escrituras condicionales en `assign_case`/`close_case` (firma `(case_id, advisor_id, settings, adapters)`), `threading.Lock` en `_run` y tabla `handover_denials` (cuatro `CREATE TABLE` en `_SCHEMA`). Si alguna no lo está, parar y reportarlo.

Orden: handover (repositorio → dominio → carreras), script, compose y configuración. Cada test
lleva en su docstring el `R<n>`. Sin red, sin Postgres, sin Docker: `httpx.MockTransport`,
repositorio y gateway falsos, reloj y sueño inyectados. No se edita `contracts/` ni
`feature_list.json`. No hay tareas de despliegue (Render PENDIENTE).

## handover: repositorio

- [x] T1 — En `handover/adapters/repository.py`, añadir a `CaseRepository` `claim_timeout`, `release_timeout_claim`, `mark_timed_out` y `update_last_messages` (firmas del design). `update_case` se mantiene. Cubre: R17, R20, R23, R25.
- [x] T2 — Implementarlos en `FakeCaseRepository` con `timeout_claims: dict[str, datetime]` (comprobar y escribir sin ceder el control; `mark_timed_out` borra la reclamación; `release_timeout_claim` solo si el caso sigue `open`). Cubre: R17, R18, R20, R23, R24, R25.
- [x] T3 — Implementarlos en `PostgresCaseRepository` con una sola sentencia `UPDATE` parametrizada cada uno y `RETURNING case_id` donde devuelven `bool`; añadir al final de `_SCHEMA` (tras el último `CREATE TABLE`; hoy, el de `handover_requests`, después de `handover_cases`, `handover_notifications` y `handover_denials`) `ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS timeout_claimed_at TIMESTAMPTZ NULL` (sin tocar `_CASE_COLUMNS` ni `Case`). Cubre: R27, R28.
- [x] T4 — En `tests/test_repository.py`, aplicar a `test_postgres_repository_uses_parameters_only` (test de la #7) exactamente el cambio S1 (A) del design: filtro `not sql.startswith(("CREATE", "ALTER"))`, llamadas añadidas a `claim_timeout`, `release_timeout_claim`, `mark_timed_out` y `update_last_messages`, y recuento de 6 a 10. Las demás aserciones (comprobaciones de `CREATE TABLE`, identificadores y `SECRET` fuera del SQL, `%s` = nº de parámetros, `params` no vacío, texto de cliente solo en parámetros, sin literales entre comillas) no se tocan. `test_postgres_repository_connects_lazily_and_once` no se toca (sigue en 4). Aplicar también el cambio S1 (B): en el helper `_statements` de la #14 (`test_repository.py` ≈l.169-170), el filtro pasa de `not sql.startswith("CREATE")` a `not sql.startswith(("CREATE", "ALTER"))` (o un helper común usado por ambos filtros). No se toca ninguna aserción de `test_postgres_repository_add_denial_uses_parameters_only`, `test_postgres_request_methods_use_parameters_only` ni de los que usan `_statements(conn)[-1]`; con el helper ajustado pasan tal cual. Ningún otro cambio en tests existentes. Cubre: R27.
- [x] T5 — Test `test_postgres_conditional_updates_filter_status_in_where` en `tests/test_repository.py`: con la conexión falsa, `claim_timeout`, `release_timeout_claim` y `mark_timed_out` emiten un único `UPDATE` cada uno, con la condición de estado en el `WHERE`, `'open'` como parámetro (no literal) y `RETURNING` en los que devuelven `bool`; con `rows=[]` devuelven `False` y con una fila `True`. Cubre: R27.
- [x] T6 — Test `test_postgres_update_last_messages_writes_only_last_messages` en `tests/test_repository.py`: el `UPDATE` solo contiene `SET last_messages` (no `status`, `advisor_id`, `assigned_at`, `closed_at`, `closed_by`). Cubre: R25.
- [x] T7 — Test `test_postgres_schema_adds_claim_column_if_not_exists` en `tests/test_repository.py`: el primer uso ejecuta el `ALTER TABLE ... ADD COLUMN IF NOT EXISTS timeout_claimed_at` una sola vez, después de los `CREATE TABLE`. Cubre: R28.

## handover: dominio

- [x] T8 — En `domain.py`, `check_timeouts`: reclamar antes de enviar, liberar si falla el envío, `mark_timed_out` condicional y log `timeout_superseded` si devuelve `False` (pseudocódigo del design). Cubre: R17, R18, R19, R20, R21, R22, R23, R24.
- [x] T9 — En `domain.py`, `_process_handover` (tal como lo deja la #11): reutilización con `update_last_messages` y rama `no_advisors` con `mark_timed_out`. No tocar `open_case`, `_start_request`, `_finish_request` ni el uso de `tally`. Cubre: R25, R26.
- [x] T10 — Usar en `tests/test_timeout_races.py` el `make_env(advisors=None, repo=None, gateway=None)` y el fixture `env_factory` que ya existen en `tests/conftest.py` (#14) para inyectar `HookRepository`/`HookGateway`, **sin modificar** `conftest.py`. Cubre: R18, R19, R21, R25, R26.
- [x] T11 — Ejecutar la suite de handover: los tests de la #7 (`test_timeouts.py`, `test_handover.py`), de la #11 (`test_requests.py`) y de la #14 (`test_assign_close_races.py`, `test_authorization.py`, `test_cases.py`) pasan sin cambios, incluido `test_check_timeouts_send_failure_keeps_case_open`; en `test_repository.py`, los de la #11 y la #14 pasan con el único ajuste del helper `_statements` de T4 (S1 B). Cubre: R20, R23.

## handover: carreras (`tests/test_timeout_races.py`, con `HookGateway` y `HookRepository` del design)

Toda llamada a `assign_case`/`close_case` de este archivo usa la firma completa de la #14 con `env.settings` y `env.adapters`, y un asesor de `ADVISORS` (`111`/`222`/`333`; se usa `"222"`); con otro asesor, `_deny` lanza `AdvisorForbidden`.

- [x] T12 — `test_check_timeouts_claims_case_before_sending`: dentro de `send`, `repo.timeout_claims[case_id]` es el `now` del reloj y el caso sigue `open`. Cubre: R17.
- [x] T13 — `test_two_simultaneous_check_timeouts_send_once`: el `on_send` ejecuta `check_timeouts` anidado; un solo envío de `HANDOVER_TIMEOUT_REPLY`, la ejecución anidada devuelve `[]`, la externa `[case_id]` y el caso queda `timed_out`. Cubre: R18.
- [x] T14 — `test_check_timeouts_skips_case_assigned_or_closed_before_claim` (parametrizado `assigned`/`closed`): el `after_list` llama a `domain.assign_case(case_id, "222", env.settings, env.adapters)` o a `domain.close_case(case_id, "222", env.settings, env.adapters)`; no hay envío, el caso queda igual que tras la operación rival y no aparece en `timed_out_cases`. Cubre: R19.
- [x] T15 — `test_assignment_during_timeout_send_is_kept`: el `on_send` llama a `domain.assign_case(case_id, "222", env.settings, env.adapters)`; al final el caso sigue `assigned` con `advisor_id="222"` y su `assigned_at`. Cubre: R20, R21.
- [x] T16 — `test_close_during_timeout_send_is_kept`: el `on_send` llama a `domain.close_case(case_id, "222", env.settings, env.adapters)`; el caso sigue `closed` con `closed_by="222"` y `closed_at`. Cubre: R21.
- [x] T17 — `test_case_changed_during_send_not_listed`: en T15 y T16, `timed_out_cases == []`. Cubre: R22.
- [x] T18 — `test_send_failure_releases_claim_and_retries_immediately`: con el gateway fallando, tras la llamada no hay reclamación (`case_id not in repo.timeout_claims`), el caso sigue `open`, y una segunda llamada con el mismo reloj envía y lo marca `timed_out`. Cubre: R23.
- [x] T19 — `test_stale_claim_is_reclaimed`: con una reclamación de hace ≥ `HANDOVER_TIMEOUT_SECONDS` el caso se envía y se marca; con una de hace `HANDOVER_TIMEOUT_SECONDS - 1` no se envía. Cubre: R24, R18.
- [x] T20 — `test_reuse_concurrent_with_assignment_keeps_assignment`: el `after_find` llama a `domain.assign_case(case_id, "222", env.settings, env.adapters)` entre la lectura y la escritura de la reutilización; al final el caso es `assigned` con su asesor y con los `last_messages` nuevos. Cubre: R25.
- [x] T21 — `test_no_advisors_reuse_concurrent_with_assignment_keeps_assignment`: con `make_env(advisors=[], repo=HookRepository(...))`, el `after_find` asigna **directamente con el repositorio** (`repo.assign_if_unassigned(case_id, "222", env.clock())`, no con `assign_case`, que fallaría con `403` porque con `advisors=[]` el `222` no está registrado); la respuesta es `no_advisors` y el caso sigue `assigned` con `advisor_id="222"` y su `assigned_at`. Cubre: R26.

## Script `scripts/vencer_casos.py`

- [x] T22 — Crear `scripts/vencer_casos.py` con `main(argv, client, sleep, max_rounds)` y `_call_once` según el design (logging, sin `print`, sin `lazaro_contracts`; intervalo validado solo en modo bucle; `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` validada en ambos modos antes de cualquier petición). Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R29, R30.
- [x] T23 — En `services/handover/tests/test_vencer_casos.py` (carga del script como `test_cargar_manual.py`, `monkeypatch` para el entorno), `test_single_call_posts_check_timeouts_with_token`: una sola petición, URL `{HANDOVER_URL}/cases/check-timeouts` (también con `/` final en la URL base), cuerpo `{}` y encabezado. Cubre: R1.
- [x] T24 — `test_single_call_exits_zero_on_200`. Cubre: R2.
- [x] T25 — `test_single_call_exits_nonzero_on_401_and_500` (parametrizado `401`, `500`, `503`). Cubre: R3.
- [x] T26 — `test_single_call_exits_nonzero_on_network_error` (`httpx.ConnectError` y `httpx.ReadTimeout`). Cubre: R4.
- [x] T27 — `test_missing_env_exits_nonzero_without_request` (falta o vacía `HANDOVER_URL`; falta o vacío `SERVICE_TOKEN`; cero peticiones). Cubre: R5.
- [x] T28 — `test_loop_repeats_and_sleeps_interval`: `--intervalo 30`, `max_rounds=3` → 3 peticiones y `sleep` llamado con `[30, 30]`. Cubre: R6.
- [x] T29 — `test_loop_interval_defaults_to_env_then_60`: `--intervalo` sin valor usa `CHECK_TIMEOUTS_INTERVAL_SECONDS=45`; sin la variable, 60. Cubre: R7.
- [x] T30 — `test_invalid_interval_exits_nonzero_without_request`, en modo bucle: `--intervalo 0`, `--intervalo -5`, `--intervalo abc`, y `--intervalo` sin valor con `CHECK_TIMEOUTS_INTERVAL_SECONDS` = `0`, `-5`, `abc`; `SystemExit` con código ≠ 0 o retorno ≠ 0; cero peticiones. Además `--intervalo 30` con `CHECK_TIMEOUTS_INTERVAL_SECONDS=abc` y `max_rounds=1` no falla (la variable no se usa). Cubre: R8.
- [x] T30b — `test_single_call_ignores_invalid_interval_env`: sin `--intervalo`, con `CHECK_TIMEOUTS_INTERVAL_SECONDS` = `0`, `-5`, `abc` y handover respondiendo `200`, el script hace una petición y termina con 0. Cubre: R30.
- [x] T31 — `test_loop_logs_failure_code`: con `caplog`, una vuelta `401`, una `500` y una `ConnectError` dejan en el log `status=401`, `status=500` y `ConnectError`. Cubre: R9.
- [x] T32 — `test_loop_continues_after_failures`: respuestas `ConnectError`, `500`, `401`, `200` con `max_rounds=4` → 4 peticiones, 3 esperas y retorno 0. Cubre: R10.
- [x] T33 — `test_token_never_in_logs_or_output`: con `SERVICE_TOKEN="TOKEN-SECRETO-XYZ"` y `caplog` a `DEBUG` + `capsys`, recorrer llamada única `200`, `401`, `500`, error de red (con el token en el mensaje de la excepción falsa), modo bucle , intervalo inválido y `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` inválida; el token no aparece en `caplog.text`, `out` ni `err`. Cubre: R11.
- [x] T34 — `test_request_uses_http_timeout_from_env`: `request.extensions["timeout"]` refleja `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=7`; sin la variable, 120. Cubre: R12.
- [x] T34b — `test_invalid_http_timeout_exits_nonzero_without_request` (parametrizado `0`, `-1`, `abc`, en llamada única y en modo bucle con `--intervalo 30`): retorno ≠ 0, cero peticiones, y el log nombra la variable `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS`. Cubre: R29.

## Compose, imagen y configuración

- [x] T35 — Añadir `COPY scripts/vencer_casos.py ./vencer_casos.py` a `services/handover/Dockerfile` (sin cambiar su `CMD`). Cubre: R15.
- [x] T36 — Añadir el servicio `timeouts_worker` a `docker-compose.yml` (bloque del design: `build` con el Dockerfile de handover, `env_file: [.env]`, `command` con `vencer_casos.py --intervalo`, `depends_on: [handover]`, `restart: unless-stopped`, sin `ports`). Cubre: R13, R14.
- [x] T37 — Añadir a `.env.example`, en una sección `# timeouts_worker`, `CHECK_TIMEOUTS_INTERVAL_SECONDS=60` y `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`. Cubre: R16.
- [x] T38 — En `services/handover/tests/test_worker_compose.py` (lectura de texto con el mismo helper `_block` que `test_handover_app.py`), `test_compose_has_timeouts_worker_running_script_in_loop`: existe el bloque, `env_file` incluye `.env`, `command` contiene `vencer_casos.py` y `--intervalo`, `build` usa `services/handover/Dockerfile`. Cubre: R13.
- [x] T39 — `test_timeouts_worker_publishes_no_ports`: el bloque no tiene clave `ports`. Cubre: R14.
- [x] T40 — `test_handover_dockerfile_copies_worker_script` y que el `CMD` de uvicorn sigue igual. Cubre: R15.
- [x] T41 — `test_env_example_declares_worker_variables`: líneas `CHECK_TIMEOUTS_INTERVAL_SECONDS=60` y `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=<valor>`. Cubre: R16.

## Cierre

- [x] T42 — `python -m pytest` completo en verde; documentar en `progress/impl_vencimiento_automatico.md` la trazabilidad R1-R30 → tests y el ajuste exacto de T4 (S1 A) sobre el test de la #7 y el de T4 (S1 B) sobre el helper `_statements` de la #14, indicando que los tests de la #11 y la #14 que lo usan pasan sin cambiar sus aserciones; anotar que la T7b de `specs/autorizacion_asesores/tasks.md` queda cumplida al crear `tests/test_timeout_races.py` (llamadas a `assign_case`/`close_case` con `env.settings` y asesores de `ADVISORS`). Cubre: R1-R30.
