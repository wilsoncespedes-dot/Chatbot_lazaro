# Tasks — autorizacion_asesores (feature #14)

> Requisitos previos: la #13 (`contrato_autorizacion_asesores`) y la #17
> (`contrato_cierre_casos_huerfanos`) en `done`. Si `lazaro_contracts` no exporta
> `CaseAuthorizeRequest`, `CaseAuthorizeResponse` y `CaseAuthorizeAction`, o si S12 de
> `contracts/CONTRATOS.md` no recoge la regla de cierre de casos huérfanos (la #17 ya la publicó,
> incluido el `advisor_id` nulo), parar con `blocked`.
> Orden de implementación supuesto: 10 → 11 → 12 → 13 → 17 → 14 (`design.md` §1).
> **Orden de ejecución de las tasks (obligatorio; los ids no siguen el orden del archivo):**
> T1, T2, T54, T55, T56, T3, T4, T5, T57, T6, T58, T7-T10, T7b, T11-T32, T59-T74, T76-T79,
> T33-T51, T75, T52, T53. La verificación final (T52, T53) va siempre en último lugar y está al
> final del archivo.
> Cada test nuevo lleva en su docstring el `R<n>` con prefijo `autorizacion_asesores`
> (p. ej. `"""autorizacion_asesores R4: ..."""`). Tests sin red ni Postgres, con los fakes y el
> reloj inyectado de cada `conftest.py`. Ningún test existente se elimina ni se relaja: los
> únicos cambios son los de `design.md` §6. Ids estables: las tasks nuevas van al final (T54+;
> T76-T79 de la decisión 2 ampliada). Las decisiones del humano citadas por número siguen la
> lista del 2026-10-31 (`requirements.md`, cabecera).

## Handover — código

- [x] T1 — `domain.py`: añadir `DenialAction`, `AdvisorForbidden`, `Denial` e `is_registered_advisor` (`design.md` §3.1; `None` → `False`). Cubre: R1.
- [x] T2 — `adapters/repository.py`: `add_denial` en `CaseRepository`, `FakeCaseRepository` (`denials`) y `PostgresCaseRepository`; sentencia `CREATE TABLE IF NOT EXISTS handover_denials` al final de `_SCHEMA` (`design.md` §3.5). Cubre: R21.
- [x] T3 — `domain.py`: `_deny` y `authorize_case` con el orden de `design.md` §3.2 (incluido el paso 4b). Cubre: R2, R3, R4, R5, R6, R7, R8, R19, R22, R46, R48.
- [x] T4 — `domain.py`: `assign_case(case_id, advisor_id, settings, adapters)` aplica los pasos 1-5 de §3.2 antes de escribir y escribe con `assign_if_unassigned`; si no cambia, `_resolve_lost_assignment` (§3.3). Sin `update_case`. Cubre: R11, R12, R13, R19, R37, R38, R39, R40, R48.
- [x] T5 — `domain.py`: `close_case(case_id, advisor_id, settings, adapters)` aplica los pasos 1-5 de §3.2 antes de escribir y escribe con `close_if_still_allowed(case_id, advisor_id, allowed_assignee, clock())`, con `allowed_assignee` = `advisor_id` huérfano leído (también `None`) si el caso es huérfano y, si no, el `advisor_id` de la petición; si no cambia, `_resolve_lost_close` relee: `closed` → `200` sin cambios (R42), `None` → `404`, cualquier otro estado → `_deny(..., "close")` → `403` (R55) (§3.3). Sin `update_case`. Cubre: R14, R15, R16, R17, R18, R19, R41, R42, R47, R54, R55.
- [x] T6 — `main.py`: ruta `POST /cases/{case_id}/authorize` (§3.4); `post_assign` y `post_close` pasan `settings`. Cubre: R2, R9, R10.

## Handover — cambios en tests existentes (`design.md` §6)

- [x] T7 — `tests/test_cases.py::test_assign_already_assigned_keeps_first_advisor`: la segunda llamada usa `"111"` en lugar de `"333"`; aserciones idénticas. Cubre: R13, R36.
- [x] T8 — `tests/test_cases.py::test_close_marks_closed_and_records_advisor`: **sin cambios**. Comprobar que pasa tal cual: su `case-assigned` sin `advisor_id` es huérfano y `"333"` lo puede cerrar (R47, `design.md` §6). Si no pasa, parar y documentarlo en `progress/impl_autorizacion_asesores.md` (no modificar el test). Cubre: R17, R36, R47, R54.
- [x] T7b — Cumplida al implementar la #12 (ver `progress/impl_vencimiento_automatico.md`). — `tests/test_timeout_races.py` (de la #12): en `test_assignment_during_timeout_send_is_kept`, `test_close_during_timeout_send_is_kept` y cualquier otra llamada a `assign_case`/`close_case` del archivo, pasar `env.settings` como nuevo argumento; aserciones idénticas. Comprobar que el asesor usado está en `ADVISORS` (`"222"` lo está); si alguno no lo estuviera, pasa a `"111"` y se documenta (`design.md` §6). Con las escrituras condicionales el resultado es el mismo (`design.md` §3.3, «Coherencia con los tests de carrera de la #12»). Cubre: R36, R37, R41.
- [x] T9 — `tests/test_repository.py::test_postgres_repository_connects_lazily_and_once`: conteo de `CREATE TABLE` `3` (el que deja la #11; el `ALTER` de la #12 no cuenta) → `4`. Cubre: R21, R36.
- [x] T10 — `tests/test_security.py`: añadir `("/cases/case-x/authorize", {"advisor_id": "111", "action": "reply"})` a `ROUTES`; añadir a `INVALID_BODIES` `("/cases/case-x/authorize", {"advisor_id": "111"})`, `("/cases/case-x/authorize", {"action": "reply"})` y `("/cases/case-x/authorize", {"advisor_id": "111", "action": "assign"})`; añadir `assert env.repo.denials == []` en `test_handover_routes_without_token_return_401_and_change_nothing`. Cubre: R9, R10, R36.

## Handover — tests nuevos (`tests/test_authorization.py` salvo indicación)

- [x] T11 — `test_registered_advisor_matches_decimal_id_exactly`: con `ADVISOR_CHAT_IDS="111,-1003"`, `is_registered_advisor` es `True` para `"111"` y `"-1003"` y `False` para `"999"`, `"0111"`, `"+111"`, `" 111"`, `"111 "`, `"1.11"`, `"-111"` y `None`. Cubre: R1.
- [x] T12 — `test_authorize_unassigned_case_allows_any_registered_advisor` (parametrizado: estado `open`/`timed_out` × `action` `reply`/`close` × asesor `111`/`222`/`333`): `200` y `{"allowed": true, "case_id": ...}` validado con `CaseAuthorizeResponse`. Cubre: R2.
- [x] T13 — `test_authorize_assigned_case_allows_assigned_advisor` (ambas `action`): caso `assigned` a `"222"`, pide `"222"` → `200`. Cubre: R3.
- [x] T14 — `test_authorize_unregistered_advisor_returns_403_before_checking_case` (parametrizado: caso `open`, `timed_out`, `assigned` a `"999"`, `closed`, inexistente): `"999"` recibe `403 forbidden`, nunca `404` ni `409`; incluye un asesor `"111"` asignado y luego retirado de `ADVISOR_CHAT_IDS` (`make_env(advisors=[222, 333])`) → `403` con ambas `action`. Cubre: R4.
- [x] T15 — `test_authorize_unknown_case_returns_404`: asesor registrado, caso inexistente → `404 not_found`. Cubre: R5.
- [x] T16 — `test_authorize_closed_case_returns_409` (ambas `action`, también si el caso estuvo asignado a quien pregunta) → `409 case_closed`. Cubre: R6.
- [x] T17 — `test_authorize_assigned_case_rejects_other_advisor` (ambas `action`): caso asignado a `"111"` (registrado), pide `"222"` → `403 forbidden`. Cubre: R7.
- [x] T18 — `test_authorize_never_modifies_cases_nor_sends`: tras una petición de cada resultado (`200`, `200` de `close` sobre un huérfano, `403`, `404`, `409`), `env.repo.cases` es igual a la copia previa y `env.gateway.sent == []`. Cubre: R8.
- [x] T19 — `test_assign_unregistered_advisor_returns_403_and_keeps_case` (parametrizado: `open`, `timed_out`, `assigned`, `closed`, inexistente): `403 forbidden`, casos idénticos a la copia previa. Cubre: R11.
- [x] T20 — `test_assign_assigned_case_by_other_advisor_returns_403`: caso asignado a `"111"`; `"333"` asigna → `403 forbidden`; `advisor_id` y `assigned_at` siguen `("111", START)`. Cubre: R12.
- [x] T21 — `test_assign_assigned_case_by_same_advisor_keeps_it`: `"111"` reasigna su propio caso tras avanzar el reloj → `200`, `advisor_id`/`assigned_at` sin cambios. Cubre: R13.
- [x] T22 — `test_close_unregistered_advisor_returns_403_and_keeps_case` (mismos estados que T19): `403 forbidden`, casos sin cambios (también un caso `closed`: no recibe `200`). Cubre: R14.
- [x] T23 — `test_close_assigned_case_by_other_advisor_returns_403`: caso asignado a `"111"` (registrado); `"222"` cierra → `403`; el caso sigue `assigned` sin `closed_at`/`closed_by`. Cubre: R15.
- [x] T24 — `test_close_assigned_case_by_assigned_advisor`: `"111"` cierra su caso → `200`, `("closed", "111", clock())`, `advisor_id` y `assigned_at` sin cambios. Cubre: R16, R41.
- [x] T25 — `test_close_unassigned_case_by_any_registered_advisor` (parametrizado `open`/`timed_out` × `111`/`222`/`333`): `200` y `closed` con ese asesor. Cubre: R17.
- [x] T26 — `test_close_closed_case_by_registered_advisor_keeps_first_closure`: caso asignado a `"111"` y cerrado por `"111"`; `"222"` cierra → `200`, `closed_by`/`closed_at` sin cambios, ningún registro de denegación. Cubre: R18, R20.
- [x] T27 — `test_denials_are_recorded_with_case_advisor_action_and_date`: una denegación por `authorize` (`reply`), `authorize` (`close`), `assign` y `close`, más una sobre un caso inexistente; `env.repo.denials` contiene exactamente esos `Denial(case_id, advisor_id, action, at=clock())` con `action` `reply`, `close`, `assign`, `close`. Cubre: R19.
- [x] T28 — `test_no_denial_recorded_for_allowed_or_other_errors`: respuestas `200` (incluido el cierre de un huérfano), `404`, `409` (y `422` de cuerpo inválido) en las tres rutas → `env.repo.denials == []`. Cubre: R20.
- [x] T29 — `test_denial_record_failure_returns_500_and_keeps_case` (cliente con `raise_server_exceptions=False`; `monkeypatch.setattr(env.repo, "add_denial", boom)`): `authorize`, `assign` y `close` denegados → `500 internal_error`, casos sin cambios. Cubre: R22.
- [x] T30 — En `tests/test_repository.py`: `test_postgres_repository_add_denial_uses_parameters_only`: con la conexión falsa, `add_denial` con un `case_id` malicioso (`"'; DROP TABLE x; --"`) ejecuta una sentencia con `%s` igual al número de parámetros, sin el valor en el SQL, y el esquema contiene `CREATE TABLE IF NOT EXISTS handover_denials`. Cubre: R21.
- [x] T31 — En `tests/test_repository.py`: `test_fake_repository_add_denial_stores_copy`: `FakeCaseRepository().add_denial(d)` deja `denials == [d]`. Cubre: R21.
- [x] T32 — **Prueba de seguridad obligatoria (handover)**, en `tests/test_security.py`: `test_security_unregistered_or_forged_advisor_ids_cannot_act`, parametrizada con `advisor_id` ∈ `["999", "0111", "+111", " 111", "111 ", "1.11", "111,222"]` y con las rutas `authorize` (`reply`), `authorize` (`close`), `assign` y `close` sobre un caso `open`: siempre `403 forbidden`, caso idéntico a la copia previa, `env.gateway.sent == []` y una denegación registrada con ese `advisor_id`. Cubre: R1, R4, R11, R14, R19.

## Orchestrator — código

- [x] T33 — `domain.py`: `AUTHORIZE_DENIAL_CODES`, `AdvisorForbidden`, `CaseClosed` (`case_closed`, `409`), `AuthorizationDenied` (`design.md` §4.1). Cubre: R25, R26, R33.
- [x] T34 — `adapters/handover.py`: `authorize` en `HandoverClient`, `HttpHandoverClient` (§4.3) y `FakeHandoverClient` (`authorize_error`, `fail_authorize`, `authorized`; valores por defecto que autorizan). Cubre: R32, R33, R34.
- [x] T35 — `domain.py`: `_record_forbidden` (solo `forbidden`) y `reply_to_case` con el flujo de `design.md` §4.2 (`case_closed` → `CaseClosed`, sin `advisor_forbidden`); ningún log con `req.text`. Cubre: R23, R24, R25, R26, R27, R28, R29, R30, R31, R35, R53.

## Orchestrator — cambios en tests existentes (`design.md` §6)

- [x] T36 — `tests/test_case_reply.py::test_http_handover_client_assign_raises_on_error_status`: parametrizado `[404, 409, 500]` → `[403, 404, 409, 500]`. Cubre: R35, R36.

## Orchestrator — tests nuevos (`tests/test_authorization.py` salvo indicación)

- [x] T37 — `test_reply_authorizes_before_lookup_send_and_store`: se sustituye `env.handover.authorize` por un envoltorio que guarda, en el momento de la llamada, `len(env.gateway.sent)`, `len(env.repo.messages)`, `len(env.repo.events)` y `env.handover.assigned`; tras un `reply` permitido, `env.handover.authorized == [("case-1", "555", "reply")]` y los valores capturados son los previos al `reply`. Cubre: R23.
- [x] T38 — `test_reply_forbidden_for_unknown_case_returns_403_not_404`: `authorize_error="forbidden"` y caso no vinculado → `403 forbidden` (no `404`). Cubre: R23, R25.
- [x] T39 — `test_reply_allowed_follows_authorize_send_store_assign_order`: con un registro de llamadas compartido (envoltorios sobre `authorize`, `gateway.send`, `repo.add_message` y `handover.assign`) el orden es `authorize`, `send`, `add_message`, `assign`; respuesta `200 {"sent": true}`. Cubre: R24.
- [x] T40 — `test_reply_forbidden_returns_403_without_sending_or_storing`: `authorize_error="forbidden"` → `403 forbidden`; `gateway.sent`, mensajes y `handover.assigned` iguales que antes; no hay evento `advisor_reply`. Cubre: R25.
- [x] T41 — `test_reply_closed_case_returns_409_without_sending` (renombrado; antes `..._returns_403_...`): `authorize_error="case_closed"` → `409` con `{"error": "case_closed", ...}`; `gateway.sent`, mensajes y `handover.assigned` iguales que antes; no hay evento `advisor_reply`. Cubre: R26.
- [x] T42 — `test_reply_case_unknown_in_handover_returns_404_without_sending`: `authorize_error="not_found"` con el caso vinculado localmente → `404 not_found`, `_snapshot` sin cambios. Cubre: R27.
- [x] T43 — `test_reply_authorize_unavailable_returns_502_without_sending`: `fail_authorize=True` → `502 upstream_error`, `_snapshot` (mensajes, eventos, envíos, `assigned`) sin cambios. Cubre: R28.
- [x] T44 — `test_reply_forbidden_records_advisor_forbidden_event` (ya **no** parametrizado con `case_closed`): con caso vinculado y `authorize_error="forbidden"`, `env.events()` gana exactamente `("advisor_forbidden", "case:case-1 advisor:555 code:forbidden")` con `at == FIXED_NOW` y en el contacto del caso. Cubre: R29.
- [x] T45 — `test_reply_forbidden_unlinked_case_logs_without_event` (`caplog`): caso no vinculado y `authorize_error="forbidden"` → ningún evento nuevo y una línea de log con `advisor_forbidden`, el `case_id` y el `advisor_id`. Cubre: R30.
- [x] T46 — `test_reply_denied_or_failed_logs_do_not_contain_text` (`caplog`, parametrizado `forbidden`/`case_closed`/`not_found`/`fail_authorize`): el `text` único de la petición no aparece en ningún registro de log. Cubre: R31.
- [x] T47 — `test_reply_assign_forbidden_after_send_records_assign_failed`: `env.handover.assign` sustituido por una función que lanza `ServiceUnavailable` (como hace el cliente HTTP con el `403` de una carrera perdida, R38) → `200 {"sent": true}`, evento `assign_failed`, un mensaje `advisor`. Cubre: R35.
- [x] T48 — `test_http_handover_client_authorize_posts_to_authorize_route` (transporte falso como el fixture `captured` de `test_case_reply.py`): URL `/cases/a%20b/authorize`, cabecera `X-Service-Token`, cuerpo `{"advisor_id": "555", "action": "reply"}`, `timeout` recibido; un `200` válido devuelve `CaseAuthorizeResponse`. Cubre: R32.
- [x] T49 — `test_http_handover_client_authorize_maps_denials` (parametrizado `(403, "forbidden")`, `(404, "not_found")`, `(409, "case_closed")`): lanza `AuthorizationDenied` con ese `code`. Cubre: R33.
- [x] T50 — `test_http_handover_client_authorize_fails_closed` (parametrizado): `401`, `422`, `500`, `502`, `403` con `error="otro"`, `404` con cuerpo no JSON, `200` con `{"allowed": false, ...}`, `200` con otro `case_id`, `200` no JSON y `httpx.ConnectError`/`httpx.ReadTimeout` → `ServiceUnavailable`. Cubre: R34.
- [x] T51 — **Prueba de seguridad obligatoria (orchestrator)**, en `tests/test_security.py`: `test_security_unregistered_advisor_reply_is_never_sent`: app del orquestador con el `HttpHandoverClient` **real** sobre un transporte HTTP falso que responde `403 {"error": "forbidden", ...}` a `/authorize` y falla el test si recibe `/assign`; con un caso vinculado, `POST /cases/{id}/reply` de `"999"` → `403 forbidden`, `env.gateway.sent == []`, ningún mensaje `advisor`, ningún `advisor_reply`, evento `advisor_forbidden` registrado. Repetir con el transporte devolviendo `200 {"allowed": false}` y con `httpx.ConnectError` → `502` y `env.gateway.sent == []`. Cubre: R25, R28, R29, R33, R34.

## Handover — código nuevo (decisiones del humano 2026-10-31)

- [x] T54 — `domain.py`: `is_orphan_case(case, settings)` y `can_act_on_case(case, advisor_id, action, settings)` puras (`design.md` §3.1, paso 4b de §3.2). Cubre: R7, R15, R46, R47, R48.
- [x] T55 — `adapters/repository.py`: `assign_if_unassigned`, `close_if_still_allowed` y `count_assigned_by_advisor` en `CaseRepository`, `FakeCaseRepository` (comprueban y escriben sin ceder el control; solo cambian sus campos) y `PostgresCaseRepository` (SQL de `design.md` §3.3, `RETURNING case_id` + `fetch=True`; en `close_if_still_allowed`, variante `advisor_id = %s` o `advisor_id IS NULL` según `allowed_assignee`). Cubre: R37, R41, R43, R49, R54.
- [x] T56 — `adapters/repository.py`: `self._lock = threading.Lock()` en `PostgresCaseRepository.__init__` y `_run` entero (incluido `_connection()`, `execute`, `fetchall`, `commit`/`rollback`) dentro de `with self._lock` (`design.md` §3.5). Cubre: R44, R45.
- [x] T57 — `domain.py`: `count_orphan_cases(settings, adapters)` y `log_orphan_cases(settings, adapters)` (INFO `orphan_cases count=<n>`; WARNING `orphan_cases_present count=<n>` si `n > 0`; WARNING `orphan_cases_check_failed` si el recuento lanza, sin ids ni texto de la excepción). Cubre: R49, R50, R51.
- [x] T58 — `main.py`: `lifespan` que ejecuta `log_orphan_cases` en el pool de hilos al arrancar (`design.md` §3.4); `create_app` no cuenta huérfanos. Cubre: R49, R52.

## Handover — tests nuevos (decisiones del humano 2026-10-31)

- [x] T59 — `test_authorize_close_orphan_case_allowed_for_any_registered_advisor` (en `test_authorization.py`; parametrizado `111`/`222`/`333`): con `make_env(advisors=[111, 222, 333])` y un caso `assigned` a `"999"` (no registrado), `authorize` con `action="close"` → `200 {"allowed": true, ...}`; también con un caso `assigned` sin `advisor_id`. Cubre: R46.
- [x] T60 — `test_close_orphan_case_by_any_registered_advisor` (en `test_authorization.py`): caso `assigned` a `"999"` con `assigned_at=START`; `"222"` cierra tras avanzar el reloj → `200`, `(status, closed_by, closed_at) == ("closed", "222", clock())` y `(advisor_id, assigned_at) == ("999", START)`; ningún registro de denegación. Cubre: R47, R54.
- [x] T61 — `test_orphan_case_cannot_be_replied_or_assigned_by_other_advisor` (en `test_authorization.py`; parametrizado `authorize` `reply` y `assign`): caso `assigned` a `"999"`; `"222"` → `403 forbidden`, caso idéntico a la copia previa y una denegación con acción `reply` o `assign`. Cubre: R48, R12, R19.
- [x] T62 — En `tests/test_assign_close_races.py` (nuevo; define `RaceRepository(FakeCaseRepository)` con un gancho `before_write` que se ejecuta una sola vez al empezar `assign_if_unassigned`/`close_if_still_allowed`, inyectado como repositorio del env): `test_assign_loses_race_to_other_advisor_returns_403`: caso `open`; el gancho llama a `assign_case(case_id, "111", env.settings, env.adapters)`; después `POST /cases/{id}/assign` de `"222"` → `403 forbidden`; el caso queda `assigned` a `"111"` con el `assigned_at` del gancho; `env.repo.denials` contiene `Denial(case_id, "222", "assign", ...)`. Cubre: R38, R37, R19.
- [x] T63 — `test_assign_loses_race_to_close_returns_409` (en `test_assign_close_races.py`): el gancho cierra el caso con `"111"`; el `assign` de `"222"` → `409 case_closed`; el caso sigue `closed` por `"111"` sin `advisor_id`; ninguna denegación. Cubre: R39.
- [x] T64 — `test_assign_race_with_same_advisor_keeps_first_assignment` (en `test_assign_close_races.py`): el gancho asigna con `"222"`; se avanza el reloj; el `assign` de `"222"` → `200`; `assigned_at` es el del gancho; ninguna denegación. Cubre: R40.
- [x] T65 — `test_close_loses_race_to_other_advisor_assignment_returns_403` (en `test_assign_close_races.py`; reescrito y renombrado, antes `test_close_during_assign_race_keeps_advisor`, por la decisión 2 ampliada): caso `open`; el gancho de `close_if_still_allowed` asigna con `"222"`; el `close` de `"111"` → `403 forbidden`; el caso queda `assigned` a `"222"` con el `assigned_at` del gancho y sin `closed_by`/`closed_at`; `env.repo.denials` contiene exactamente `Denial(case_id, "111", "close", at=clock())`. Cubre: R55, R41, R19.
- [x] T66 — `test_close_loses_race_to_other_close_keeps_first_closure` (en `test_assign_close_races.py`): el gancho cierra con `"222"`; se avanza el reloj; el `close` de `"111"` → `200`; `closed_by`/`closed_at` son los del gancho. Cubre: R42.
- [x] T67 — `test_assign_and_close_write_only_their_fields` (en `test_assign_close_races.py`): con `monkeypatch.setattr(env.repo, "update_case", boom)`, asignar y cerrar casos `open` y `timed_out` responde `200` (no se usa `update_case`) y `last_messages`, `contact_id`, `chat_id` y `reason` quedan idénticos. Cubre: R37, R41, R43.
- [x] T68 — En `tests/test_repository.py`: `test_postgres_conditional_writes_use_parameters_only`: con la conexión falsa, `assign_if_unassigned` con un `case_id` malicioso ejecuta una sola sentencia `UPDATE ... RETURNING case_id` con `sql.count("%s") == len(params)`, sin el valor ni literales entre comillas en el SQL y con `status IN (%s, %s)`; devuelve `True` con `conn.rows = [("case-1",)]` y `False` con `conn.rows = []`. El cierre condicional se prueba en T79. Cubre: R43, R37.
- [x] T69 — En `tests/test_repository.py`: `test_postgres_count_assigned_by_advisor_uses_parameters`: sentencia `SELECT ... GROUP BY advisor_id` con parámetro `"assigned"` (no literal) y, con `conn.rows = [("111", 2), ("999", 1), (None, 1)]`, devuelve `{"111": 2, "999": 1, None: 1}`; con el repositorio falso el mismo recuento sobre casos de distintos estados. Cubre: R49.
- [x] T70 — En `tests/test_repository.py`: `test_postgres_repository_serializes_statements_across_threads`: conexión falsa cuya cursora, en `execute`, comprueba `repo._lock.locked()`, incrementa un contador de sentencias en curso, espera un instante y lo decrementa, guardando el máximo; dos hilos (arrancados con `threading.Barrier`, `join(timeout=5)`) hacen varias llamadas a `get_case` cada uno; el máximo es `1` y no hay excepciones. Cubre: R44.
- [x] T71 — En `tests/test_repository.py`: `test_postgres_repository_connects_once_with_concurrent_first_use`: la función `connect` espera un instante antes de devolver la conexión falsa y cuenta sus llamadas; dos hilos hacen a la vez el primer `get_case`; `connect` se llama una vez y el esquema se ejecuta una vez (4 `CREATE TABLE`). Cubre: R45.
- [x] T72 — En `tests/test_startup.py`: `test_startup_logs_orphan_case_count` (parametrizado: sin huérfanos / con huérfanos): con `ADVISOR_CHAT_IDS="987654321,111"`, repositorio falso con casos `assigned` a `"987654321"`, a `"1001234567890"` (no registrado), sin `advisor_id`, y casos `open`/`closed`; `with TestClient(create_app(settings, adapters))` y `caplog` a INFO → registro INFO `orphan_cases count=2` y WARNING `orphan_cases_present count=2`; sin huérfanos → `orphan_cases count=0` y ningún `orphan_cases_present`. Ningún registro contiene `1001234567890`, `987654321` ni ids de casos. Cubre: R49, R50.
- [x] T73 — En `tests/test_startup.py`: `test_startup_orphan_count_failure_warns_and_starts`: `count_assigned_by_advisor` sustituido por una función que lanza `RuntimeError("secreto-xyz")`; `with TestClient(...)` arranca, `GET /health` → `200`, hay un WARNING `orphan_cases_check_failed` y ningún registro contiene `secreto-xyz`. Cubre: R51.
- [x] T74 — En `tests/test_startup.py`: `test_create_app_does_not_count_orphans`: `count_assigned_by_advisor` sustituido por una función que falla el test; `create_app(settings, adapters)` y `TestClient(app)` **sin** `with` no lo llaman. El test existente `test_import_main_does_not_connect` sigue pasando sin cambios. Cubre: R52.
- [x] T76 — `test_close_race_with_own_assignment_closes_case` (en `test_assign_close_races.py`): caso `open`; el gancho de `close_if_still_allowed` asigna con `"111"`; el `close` de `"111"` → `200`; el caso queda `closed` con `closed_by="111"`, `advisor_id="111"` y el `assigned_at` del gancho; ninguna denegación. Cubre: R41.
- [x] T77 — `test_close_orphan_race_with_other_close_keeps_first_closure` (en `test_assign_close_races.py`): caso `assigned` a `"999"` (huérfano); el gancho de `close_if_still_allowed` cierra con `"222"`; se avanza el reloj; el `close` de `"111"` → `200`; `closed_by`/`closed_at` son los del gancho y `advisor_id` sigue `"999"`; ninguna denegación. Cubre: R54, R42.
- [x] T78 — En `tests/test_repository.py`: `test_fake_close_if_still_allowed_checks_state_and_assignee` (parametrizado): con `FakeCaseRepository`, `close_if_still_allowed(case_id, "111", allowed_assignee, at)` devuelve `True` y escribe solo `status`/`closed_by`/`closed_at` para `open` y `timed_out` (cualquier `allowed_assignee`), para `assigned` a `"111"` con `allowed_assignee="111"`, para `assigned` a `"999"` con `allowed_assignee="999"` y para `assigned` sin `advisor_id` con `allowed_assignee=None`; devuelve `False` sin cambiar nada para `assigned` a `"222"` con `allowed_assignee="111"`, para `assigned` a `"999"` con `allowed_assignee=None`, para `assigned` sin `advisor_id` con `allowed_assignee="999"` y para `closed`. `advisor_id`, `assigned_at` y `last_messages` nunca cambian. Cubre: R41, R54, R43.
- [x] T79 — En `tests/test_repository.py`: `test_postgres_close_if_still_allowed_uses_parameters_only`: con la conexión falsa y un `case_id` malicioso, `close_if_still_allowed` con `allowed_assignee="111"` ejecuta una sola sentencia `UPDATE ... RETURNING case_id` que contiene `status IN (%s, %s)` y `advisor_id = %s`, y con `allowed_assignee=None` una que contiene `advisor_id IS NULL` y no `advisor_id = %s`; en ambos casos `sql.count("%s") == len(params)`, sin el valor ni literales entre comillas en el SQL, sin `<>`, y los parámetros incluyen `"open"`, `"timed_out"` y `"assigned"`; devuelve `True` con `conn.rows = [("case-1",)]` y `False` con `conn.rows = []`. Cubre: R43, R41, R54.

## Orchestrator — tests nuevos (decidido por el humano, 2026-10-31, decisión 1)

- [x] T75 — `test_reply_closed_case_does_not_record_advisor_forbidden` (en `test_authorization.py`, `caplog`; parametrizado caso vinculado / no vinculado): `authorize_error="case_closed"` → `409`; ningún evento nuevo (en particular ningún `advisor_forbidden`) y ningún registro de log contiene `advisor_forbidden`. Cubre: R53.

## Verificación (siempre al final)

- [x] T52 — Ejecutar `python -m pytest services/handover services/orchestrator` y luego `./init.sh`; todo verde. Revisar `git diff -- services/*/tests/` y confirmar que los únicos cambios en tests existentes son T7, T7b, T9, T10 y T36 (más tests **añadidos** en `test_repository.py`, `test_security.py` y `test_startup.py`); ninguna línea `assert` eliminada salvo el `== 3` → `== 4` de T9; `tests/test_cases.py::test_close_marks_closed_and_records_advisor` (T8), `tests/test_requests.py` de la #11 y el resto de `tests/test_timeout_races.py` de la #12 sin cambios. Cubre: R36.
- [x] T53 — Documentar la trazabilidad R1-R55 → test en `progress/impl_autorizacion_asesores.md`, incluido el diff de T7, T7b, T9, T10 y T36, y anotar que D7, D8, D9, D12 y D13 están decididas por el humano (2026-10-31, `design.md` §8.2) y que los riesgos (d) y (e) de la #12 siguen abiertos (`design.md` §8.4). Cubre: R36.

## Trazabilidad R → tasks

| R | Tasks | R | Tasks | R | Tasks |
|---|---|---|---|---|---|
| R1 | T1, T11, T32 | R19 | T3, T4, T5, T27, T32, T61, T62, T65 | R37 | T4, T7b, T55, T62, T67, T68 |
| R2 | T3, T6, T12 | R20 | T26, T28 | R38 | T4, T62 |
| R3 | T3, T13 | R21 | T2, T9, T30, T31 | R39 | T4, T63 |
| R4 | T3, T14, T32 | R22 | T3, T29 | R40 | T4, T64 |
| R5 | T3, T15 | R23 | T35, T37, T38 | R41 | T5, T7b, T24, T55, T65, T67, T76, T78, T79 |
| R6 | T3, T16 | R24 | T35, T39 | R42 | T5, T66, T77 |
| R7 | T3, T17, T54 | R25 | T33, T35, T38, T40, T51 | R43 | T55, T67, T68, T78, T79 |
| R8 | T3, T18 | R26 | T33, T35, T41 | R44 | T56, T70 |
| R9 | T6, T10 | R27 | T35, T42 | R45 | T56, T71 |
| R10 | T6, T10 | R28 | T35, T43, T51 | R46 | T3, T54, T59 |
| R11 | T4, T19, T32 | R29 | T35, T44, T51 | R47 | T5, T8, T54, T60 |
| R12 | T4, T20, T61 | R30 | T35, T45 | R48 | T3, T4, T54, T61 |
| R13 | T4, T7, T21 | R31 | T35, T46 | R49 | T55, T57, T58, T69, T72 |
| R14 | T5, T22, T32 | R32 | T34, T48 | R50 | T57, T72 |
| R15 | T5, T23, T54 | R33 | T33, T34, T49, T51 | R51 | T57, T73 |
| R16 | T5, T24 | R34 | T34, T50, T51 | R52 | T58, T74 |
| R17 | T5, T8, T25 | R35 | T35, T36, T47 | R53 | T35, T75 |
| R18 | T5, T26 | R36 | T7, T7b, T8, T9, T10, T36, T52, T53 | R54 | T5, T8, T55, T60, T77, T78, T79 |
| | | | | R55 | T5, T65 |
