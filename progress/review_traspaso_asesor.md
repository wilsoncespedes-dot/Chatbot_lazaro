# Review — feature 7 `traspaso_asesor`

**Veredicto:** APPROVED

`./init.sh` lo he ejecutado yo: exit 0, **674 passed** (línea base 598, +76), 1 warning de
starlette/httpx que ya existía, ningún `skip`.

## Trazabilidad requirements ↔ tests

Prefijos: `H` = `services/handover/tests/`, `O` = `services/orchestrator/tests/`. Todos los tests
pasan y cada uno indica su `R<n>` en el docstring.

- R1: [x] `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors`, `::test_handover_does_not_reuse_closed_or_timed_out_cases`
- R2: [x] `H/test_handover.py::test_handover_reuses_open_case_of_same_contact`, `::test_handover_reuses_assigned_case`
- R3: [x] `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors` (envía a 111, 222 y 333); `H/test_repository.py::test_http_gateway_client_posts_send_with_token`
- R4: [x] `H/test_handover.py::test_notice_contains_case_reason_and_messages`
- R41: [x] `H/test_handover.py::test_notice_fits_4096_limit_with_long_messages`, `::test_notice_cuts_each_message_to_300_characters`
- R5: [x] `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors` (tupla exacta caso, asesor, motivo, fecha, delivered)
- R6: [x] `H/test_handover.py::test_handover_one_failed_notice_still_notifies_others`, `::test_handover_all_notices_fail_returns_no_advisors`
- R7: [x] `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors`, `::test_handover_one_failed_notice_still_notifies_others`
- R8: [x] `H/test_handover.py::test_handover_without_advisors_returns_no_advisors_and_does_not_send` (`gateway.sent == []`)
- R9: [x] `H/test_handover.py::test_handover_all_notices_fail_returns_no_advisors`
- R10: [x] `H/test_handover.py::test_handover_without_advisors_returns_no_advisors_and_does_not_send`, `::test_no_advisors_case_is_not_notified_again_by_check_timeouts`, `::test_no_advisors_keeps_reused_assigned_case_assigned`
- R11: [x] `H/test_cases.py::test_assign_marks_case_assigned`, `::test_assign_timed_out_case`
- R12: [x] `H/test_cases.py::test_assign_already_assigned_keeps_first_advisor`
- R13: [x] `H/test_cases.py::test_assign_closed_case_returns_409` (además comprueba que el caso no cambia)
- R14: [x] `H/test_cases.py::test_assign_and_close_unknown_case_return_404`
- R15: [x] `H/test_cases.py::test_close_marks_closed_and_records_advisor` (desde open, assigned y timed_out)
- R16: [x] `H/test_cases.py::test_close_is_idempotent_and_keeps_first_closure`
- R17: [x] `H/test_timeouts.py::test_check_timeouts_notifies_client_and_marks_timed_out`
- R18: [x] `H/test_timeouts.py::test_check_timeouts_ignores_assigned_closed_and_recent_cases`
- R19: [x] `H/test_timeouts.py::test_check_timeouts_send_failure_keeps_case_open`
- R20: [x] `H/test_timeouts.py::test_check_timeouts_continues_after_failure`
- R21: [x] `H/test_timeouts.py::test_check_timeouts_returns_empty_list_when_none_expired`, `::test_check_timeouts_notifies_client_and_marks_timed_out`
- R22: [x] `H/test_timeouts.py::test_check_timeouts_uses_injected_clock` (límite 299/300 s), `::test_package_never_reads_wall_clock_outside_main`
- R23: [x] `H/test_config.py` (5 tests: descarte de blancos y no numéricos, vacío por defecto, 300 por defecto, lectura del entorno, rechazo de valores < 1)
- R24: [x] `H/test_security.py::test_handover_routes_without_token_return_401_and_change_nothing` (4 rutas × sin token / token erróneo; comprueba casos, notificaciones y envíos sin cambios)
- R25: [x] `H/test_security.py::test_handover_invalid_body_returns_422` (6 cuerpos, las 4 rutas)
- R26: [x] `H/test_repository.py::test_postgres_repository_uses_parameters_only`, `::test_postgres_repository_connects_lazily_and_once`, `::test_postgres_repository_reads_cases_from_rows`, `::test_import_main_does_not_connect`
- R27: [x] `O/test_config.py::test_no_advisors_reply_has_default`
- R28: [x] `O/test_case_reply.py::test_case_is_linked_to_contact_after_handover`, `::test_case_link_uses_effective_case_id`, `::test_postgres_case_links_use_parameters_only`
- R29: [x] `O/test_case_reply.py::test_no_advisors_sends_fixed_reply_to_client`
- R30: [x] `O/test_case_reply.py::test_no_advisors_sends_fixed_reply_to_client` (envío más guardado con rol `bot`), `::test_no_advisors_after_no_relevant_chunks_also_informs_client`
- R31: [x] `O/test_case_reply.py::test_reply_sends_text_stores_advisor_message_and_event`
- R32: [x] `O/test_case_reply.py::test_reply_sends_text_stores_advisor_message_and_event`
- R33: [x] `O/test_case_reply.py::test_reply_assigns_case_in_handover`, `::test_http_handover_client_assign_posts_to_assign_route`
- R34: [x] `O/test_case_reply.py::test_reply_assign_failure_still_returns_sent`, `::test_http_handover_client_assign_raises_on_error_status` (404/409/500)
- R35: [x] `O/test_case_reply.py::test_reply_unknown_case_returns_404_without_sending`
- R36: [x] `O/test_case_reply.py::test_reply_send_failure_returns_502_and_stores_nothing`
- R37: [x] `O/test_case_reply.py::test_reply_without_token_returns_401`
- R38: [x] `O/test_case_reply.py::test_reply_invalid_body_returns_422`
- R39, R40: retirados del spec (pasaron a la #9); no se esperan tests en esta feature.

Todos los tests nuevos (`H/test_handover.py`, `test_cases.py`, `test_timeouts.py`,
`test_security.py`, `test_repository.py`, `test_config.py`, `O/test_case_reply.py`) mapean a algún
R. `O/test_case_reply.py::test_handover_unavailable_creates_no_link` (R28) protege el supuesto
«con ServiceUnavailable no cambia nada» del design.

## Tasks completas
- T5 a T33: [x] (`specs/traspaso_asesor/tasks.md:12-49`). La precondición (#9 `done`, con
  `CaseAssignRequest`/`CaseAssignResponse` exportados) se cumple.

## Acceptance de la #7 (`feature_list.json`)
1. [x] Crea o reutiliza el caso, avisa con `POST /send`, responde `notified`: `handover/domain.py:91-126`.
2. [x] Cada aviso queda registrado con caso, asesor, motivo, fecha y `delivered`: `domain.py:120-122`, tabla `handover_notifications` en `adapters/repository.py:79-81`.
3. [x] `no_advisors` (sin asesores o todos fallan) y el orquestador envía `NO_ADVISORS_REPLY`: `domain.py:125-133`, `orchestrator/domain.py:217-221`. La prueba de seguridad obligatoria «sin asesores» existe en los dos lados: `H/test_handover.py:102` y `O/test_case_reply.py:41`.
4. [x] `POST /cases/{id}/reply` envía, guarda en el historial y marca `assigned` vía `assign`; 404 si el caso no existe: `orchestrator/domain.py:285-305`, `orchestrator/main.py:121-123`.
5. [x] `check-timeouts` con reloj inyectado: `handover/domain.py:174-188`.
6. [x] Cierre registrado (`closed_by`, `closed_at`): `domain.py:156-171`.
7. [x] 300 s por defecto y `ADVISOR_CHAT_IDS`: `handover/config.py:19-33`.
8. [x] Están todos los casos de test pedidos: 3 asesores (`test_handover.py:18`), sin asesores (`:102`), fallo de un aviso (`:133`), respuesta del asesor (`test_case_reply.py:91`), caso inexistente (`test_case_reply.py:125`, `test_cases.py:69`), vencimiento (`test_timeouts.py:22`) y cierre (`test_cases.py:76`, `:90`).

## Supuestos confirmados por el humano
- R10: [x] `handover/domain.py:130-131`: con `no_advisors` un caso `open` pasa a `timed_out` sin
  enviar `HANDOVER_TIMEOUT_REPLY`. Con `no_advisors` no se llama a `gateway.send` en ningún
  punto, y un caso `assigned` reutilizado no cambia de estado.
- R11: [x] `handover/domain.py:141-152`: `open` o `timed_out` → `assigned`; `assigned` → sin
  cambios (R12); `closed` → `CaseClosed` 409.

## Contrato
- [x] Handover usa `CaseAssignRequest`/`CaseAssignResponse` en `handover/main.py:107-109` y
  `domain.py:136-153`. El orquestador los usa en `orchestrator/adapters/handover.py:52-68`, con
  `quote(case_id, safe='')` y `ServiceUnavailable` ante 4xx/5xx.
- [x] S11: ya `assigned` → 200 sin cambiar el asesor; `closed` → 409 `case_closed`; inexistente →
  404 `not_found`, todo con tests.
- [x] `contracts/` no se ha tocado en esta feature. `git diff --numstat -- contracts/` coincide
  línea a línea con la tabla de `progress/impl_contrato_asignar_caso.md` (38/4/16-1/62/6/34/2).
  Ningún archivo de `contracts/` es más reciente que `progress/review_contrato_asignar_caso.md`
  (22:30); el código de la #7 es posterior (`handover/domain.py` 22:34).

## Tests existentes modificados (git diff de `services/*/tests/`)
No se ha borrado ningún test: `git diff -U0` no tiene ninguna línea `-def test_`. Solo se
reemplazan 3 aserciones:

1. `O/test_decisions.py:106` `test_ack_sent_when_notified_for_user_request`. Antes
   `== [(100, ACK)]`, ahora `== [(100, ACK), (100, no_advisors_reply)]`. El design lo autoriza
   (design.md:58-59, T28) y R30 lo exige. Sigue siendo una igualdad exacta, así que lo que pedía
   R21 de la feature 4 (con `no_advisors` no se manda el ACK) sigue comprobado.
2. `O/test_config.py:74` `test_only_health_and_messages_routes_exposed`. Antes
   `paths == {"/health", "/messages"}`, ahora `paths == {"/health", "/messages", "/cases/{case_id}/reply"}`.
   Lo exige T30 y la ruta está en el contrato. Sigue siendo **igualdad exacta** de conjuntos: es
   una lista cerrada, no un subconjunto, y cualquier otra ruta hace fallar el test. No se debilita.
3. `H/test_handover_app.py:137` `test_requirements_txt_matches_design`. La lista exacta ordenada
   gana `httpx` y `pg8000`. Lo exigen T5 y design.md:40,190. Sigue siendo igualdad exacta y se
   mantiene el bucle que exige cota doble `>=`/`<` (`:145-146`). No se debilita.

`test_messages.py` y `tests/fakes.py` del orquestador no cambian.

## Arquitectura y convenciones
- [x] `handover/domain.py` no hace IO: los adaptadores se inyectan por `Adapters` y solo hay
  imports de tipos bajo `TYPE_CHECKING`.
- [x] Cada adaptador tiene su Fake: `FakeGatewayClient(fail_for=...)`
  (`adapters/gateway.py:43-53`), `FakeCaseRepository` (`adapters/repository.py:33-70`) y
  `FakeHandoverClient.assign/fail_assign`.
- [x] SQL siempre parametrizado con `%s`: `handover/adapters/repository.py:156-223` y
  `orchestrator/adapters/repository.py` (`link_case`/`get_case_contact`). Los tests lo prueban
  con una cadena de inyección. La conexión es perezosa.
- [x] Reloj: `datetime.now` solo aparece en `handover/main.py:49` y
  `orchestrator/main.py:53` (los dos dentro de `build_default_adapters`). Hay test de ello.
- [x] Los logs no llevan texto de clientes. Solo `case_id`, `advisor_id`, `contact_id` y el tipo
  de la excepción (`handover/domain.py:116,132,184`, `gateway.py:39`,
  `orchestrator/domain.py:293,303`). Además, `test_check_timeouts_send_failure_keeps_case_open`
  comprueba que el texto no aparece en el log.
- [x] Token de servicio: el middleware de handover (`main.py:58-70`, solo `/health` es pública)
  cubre las 4 rutas nuevas, y en el orquestador lo cubre su middleware existente. Los tests de
  401 están en los dos servicios.
- [x] El orquestador no lee la base de handover: `case_links` está en la base del propio
  orquestador y el estado del caso solo se toca por HTTP (`assign`).
- [x] Estilo: no hay líneas nuevas de más de 100 caracteres. Las únicas que hay
  (`orchestrator/domain.py:226`, `adapters/repository.py:77`) ya existían en HEAD.

## Alcance
- [x] Archivos tocados: `services/handover/**` y `services/orchestrator/**` (los que lista el
  design), `.env.example` (`NO_ADVISORS_REPLY` y `HANDOVER_TIMEOUT_REPLY`), y `tasks.md` y
  `progress/`. `docker-compose.yml`, `eval/`, `scripts/`, `.github/` y `contracts/` siguen
  intactos. `docker-compose.yml` no hacía falta cambiarlo porque `handover` y `orchestrator` ya
  usan `env_file: [.env]`.
- [x] Dependencias nuevas: solo `httpx>=0.27,<1` y `pg8000>=1.31,<2` (BSD-3), las que lista el design.

## Checkpoints
- C1: [x] El arnés está completo y `./init.sh` termina con exit 0.
- C2: [x] Solo la #7 está `in_progress`, las `done` tienen tests en verde y `progress/current.md` describe la sesión activa.
- C3: [x] Solo están los servicios previstos, ningún servicio importa a otro, las rutas están en `CONTRATOS.md`, las dependencias tienen versión acotada y figuran en el design, no hay GPL, las variables nuevas están en `.env.example`, y no hay `print`, `eval` ni SQL concatenado.
- C4: [x] Los tests solo usan fakes (httpx con `MockTransport` y una conexión pg falsa), son 674 y están en verde, y existe la prueba de seguridad «el traspaso responde bien cuando no hay asesores».
- C5: [x] No hay archivos sospechosos sin trackear. La entrada de `history.md` para la #7 la añade el leader al cerrar; no bloquea.
- C6: [x] El spec está completo, tasks `[x]` y todos los R cubiertos.

## Observaciones (no bloquean)
1. Al reutilizar un caso, el aviso y la notificación usan el `reason` de la petición nueva y el
   caso conserva el original (`handover/domain.py:109,121`). Está documentado en
   `progress/impl_traspaso_asesor.md:136-137` y es compatible con R2 y R5.

## Cambios requeridos
Ninguno.
