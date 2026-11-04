# Implementación #41 panel_asesores_multicanal

Estado: implementación completada; corrección de colección aplicada; pendiente
`./init.sh` y revisión de Claude.

## Resumen

- `contracts`: `CaseTransferRequest`/`CaseTransferResponse`, ejemplos, mapeo de
  tests y sección `POST /cases/{id}/transfer` en `CONTRATOS.md` (aditivo).
- `handover`: `transfer_if_assigned_to` (Fake y Postgres), `transfer_case`,
  `TransferTargetInvalid`, `DenialAction` con `transfer` y la ruta
  `POST /cases/{id}/transfer`.
- `orchestrator`: `panel.py` (funciones puras), ventana WhatsApp en
  `reply_to_case`, `advisor_send_template`, transferencia, devolución,
  bandeja, vista de caso, presencia, auditoría `panel_audit`, cola de supresión,
  rutas y plantillas del panel, config de R71 y migraciones aditivas.
- `docs/architecture.md`: nota del panel multicanal y de la transferencia.

## Trazabilidad

- R1 → `tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`, `::test_inbox_uses_advisor_id_from_session`
- R2 → `tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`
- R3 → `tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`
- R4 → `tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`, `tests/test_panel_pure.py::test_case_wait_three_branches`
- R5 → `tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`, `tests/test_panel_pure.py::test_channel_window_boundaries_and_telegram`
- R6 → `tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`
- R7 → `tests/test_panel_inbox.py::test_inbox_filters_by_channel_and_assignment`
- R8 → `tests/test_panel_inbox.py::test_invalid_filter_is_422_without_calling_handover`
- R9 → `tests/test_panel_inbox.py::test_inbox_orders_by_created_at_and_tolerates_unlinked_case`
- R10 → `tests/test_panel_inbox.py::test_inbox_orders_by_created_at_and_tolerates_unlinked_case`
- R11 → `tests/test_panel_inbox.py::test_non_advisor_session_redirects_without_listing`
- R12 → `tests/test_panel_inbox.py::test_meta_refresh_is_configurable`
- R13 → `tests/test_repository_schema.py::test_get_case_contact_selects_all_six_columns`, `tests/test_panel_case_view.py::test_memory_route_and_whatsapp_contact_remain_available`
- R14 → `tests/test_panel_reply.py::test_reply_telegram_uses_gateway_send`, `::test_reply_whatsapp_open_uses_channel_send`
- R15 → `tests/test_panel_reply.py::test_reply_requires_exactly_one_of_text_or_template`
- R16 → `tests/test_panel_reply.py::test_reply_whatsapp_closed_returns_409_without_sending`
- R17 → `tests/test_panel_reply.py::test_template_valid_is_sent_and_stored`
- R18 → `tests/test_panel_reply.py::test_template_valid_is_sent_and_stored`
- R19 → `tests/test_panel_reply.py::test_template_rejected_without_calling_gateway`
- R20 → `tests/test_panel_reply.py::test_template_rejected_without_calling_gateway`
- R21 → `tests/test_panel_reply.py::test_gateway_422_maps_to_channel_window_closed`, `tests/test_adapters.py::test_http_gateway_raises_channel_rejected_on_422`
- R22 → `tests/test_panel_reply.py::test_responder_command_on_closed_whatsapp_sends_failed_reply`
- R23 → `tests/test_panel_reply.py::test_authorize_happens_before_window_check`
- R24 → `tests/test_panel_reply.py::test_case_view_renders_selector_or_textarea`
- R25 → `tests/test_panel_reply.py::test_case_view_renders_selector_or_textarea`
- R26 → `contracts/tests/test_examples.py`, `tests/test_adapters.py::test_http_transfer_uses_route_token_and_payload`
- R27 → `services/handover/tests/test_transfer.py::test_transfer_reassigns_case_and_updates_assigned_at`
- R28 → `services/handover/tests/test_transfer.py::test_unregistered_actor_is_denied_and_records_transfer`, `::test_case_not_assigned_to_actor_is_denied`, `::test_case_assigned_to_other_advisor_is_denied`
- R29 → `services/handover/tests/test_transfer.py::test_invalid_or_same_target_returns_422_without_changes`
- R30 → `services/handover/tests/test_transfer.py::test_missing_case_returns_404`, `::test_closed_case_returns_409`
- R31 → `services/handover/tests/test_transfer.py::test_lost_race_to_target_returns_200`, `::test_lost_race_to_other_advisor_returns_403`
- R32 → `tests/test_panel_actions.py::test_transfer_success_records_handover_and_event`, `::test_transfer_maps_handover_errors`
- R33 → `tests/test_panel_actions.py::test_transfer_invalid_target_is_422_without_handover`
- R34 → `tests/test_panel_actions.py::test_transfer_away_target_is_409_without_handover`
- R35 → `tests/test_panel_actions.py::test_transfer_success_records_handover_and_event`
- R36 → `tests/test_panel_actions.py::test_resolve_keeps_closed_reply_and_state`
- R37 → `tests/test_panel_actions.py::test_return_closes_sends_return_reply_and_records_event`
- R38 → `tests/test_panel_actions.py::test_return_closes_sends_return_reply_and_records_event`
- R39 → `tests/test_panel_actions.py::test_whatsapp_closed_skips_notice_but_closes_case`
- R40 → `tests/test_panel_case_view.py::test_authorization_happens_before_reading_case_data`
- R41 → `tests/test_panel_case_view.py::test_authorization_happens_before_reading_case_data`
- R42 → `tests/test_panel_case_view.py::test_history_respects_lookback_limit_labels_and_order`
- R43 → `tests/test_panel_case_view.py::test_history_respects_lookback_limit_labels_and_order`
- R44 → `tests/test_panel_case_view.py::test_foreign_session_windows_are_hidden_with_and_without_profile`
- R45 → `tests/test_panel_case_view.py::test_memory_and_summaries_are_shown_and_client_data_is_masked`
- R46 → `tests/test_panel_case_view.py::test_memory_and_summaries_are_shown_and_client_data_is_masked`
- R47 → `tests/test_panel_case_view.py::test_case_without_profile_shows_no_client_and_no_memory`
- R48 → `tests/test_panel_case_view.py::test_all_texts_are_escaped`
- R49 → `tests/test_panel_case_view.py::test_transfer_targets_include_presence`
- R50 → `tests/test_panel_audit.py::test_reads_record_one_audit_row_each`
- R51 → `tests/test_panel_audit.py::test_actions_record_ok`
- R52 → `tests/test_panel_audit.py::test_domain_errors_record_their_code`
- R53 → `tests/test_panel_audit.py::test_audit_never_stores_client_text_username_external_id_or_note`
- R54 → `tests/test_panel_audit.py::test_domain_errors_record_their_code`, `tests/test_advisor_panel.py::test_forbidden_actions_record_advisor_forbidden_event`
- R55 → `tests/test_repository_schema.py::test_schema_declares_panel_audit_and_presence`
- R56 → `tests/test_panel_actions.py::test_presence_is_stored_with_now`
- R57 → `tests/test_panel_actions.py::test_invalid_presence_is_422_without_changing_state`
- R58 → `tests/test_panel_actions.py::test_protected_request_touches_last_seen_keeping_status`
- R59 → `tests/test_panel_actions.py::test_logout_sets_presence_away`
- R60 → `tests/test_panel_suppression.py::test_admin_queue_shows_pending_with_priority`, `::test_asesor_queue_requires_executor_role`
- R61 → `tests/test_panel_suppression.py::test_asesor_queue_requires_executor_role`
- R62 → `tests/test_panel_suppression.py::test_queue_orders_pending_by_deadline_and_limits_executed`
- R63 → `tests/test_panel_pure.py::test_business_deadline_skips_weekend`
- R64 → `tests/test_panel_pure.py::test_business_days_left_and_priority_three_branches`
- R65 → `tests/test_panel_suppression.py::test_admin_queue_shows_pending_with_priority`
- R66 → `tests/test_panel_suppression.py::test_execute_telegram_saves_note_and_sends_text`, `::test_execute_without_csrf_is_forbidden`
- R67 → `tests/test_panel_suppression.py::test_long_note_is_422_without_executing`
- R68 → `tests/test_panel_suppression.py::test_execute_whatsapp_open_uses_text_and_closed_uses_template`
- R69 → `tests/test_panel_suppression.py::test_notice_failure_and_missing_contact_are_recorded`
- R70 → `tests/test_panel_suppression.py::test_execution_errors_do_not_notify`
- R71 → `tests/test_config.py::test_panel_settings_defaults_and_env_example`
- R72 → `tests/test_config.py::test_panel_settings_reject_invalid_values`
- R73 → `tests/test_panel_case_view.py::test_memory_route_and_whatsapp_contact_remain_available`, `tests/test_advisor_commands.py`, `tests/test_advisor_panel.py`
- R74 → `services/handover/tests/test_transfer.py::test_transfer_without_token_returns_401`, `::test_invalid_body_returns_422`, `services/handover/tests/test_security.py`

## Nota de verificación

No se ejecutó shell (límite del implementer). Claude debe ejecutar
`./init.sh` y confirmar que todo queda verde antes de la revisión final.

## Intento de corrección 1 — fallo de `./init.sh` (Claude)

`./init.sh` salió con FAIL: pytest se interrumpió con 6 errores de colección.
`test_panel_actions.py`, `test_panel_audit.py`, `test_panel_case_view.py`,
`test_panel_inbox.py`, `test_panel_reply.py` y `test_panel_suppression.py`
fallan con `ModuleNotFoundError: No module named 'panel_helpers'`.
Causa: `pytest.ini` usa `addopts = -q --import-mode=importlib`, así que
`services/orchestrator/tests/` no está en `sys.path` y no se puede importar
`panel_helpers.py` como módulo. Corrección pedida: mover los helpers
compartidos a `services/orchestrator/tests/conftest.py` como fixtures/funciones
expuestas mediante fixtures, o duplicarlos en cada test, sin depender
de importar módulos hermanos de `tests/`; no cambiar `pytest.ini`. Después,
revisar que el resto de los tests nuevos pasen (no se pudieron recolectar).

## Intento de corrección 2 — colección de los tests del panel (#41)

Causa corregida sin tocar `pytest.ini` ni código de aplicación:

- Los helpers compartidos (`NOW`, `CSRF`, `make_profile`, `login`, `login_admin`,
  `link_case`, `add_message`, `case_item`, `set_presence`,
  `add_client_session`) viven ahora en `services/orchestrator/tests/conftest.py`
  y se exponen con la fixture `panel`.
- Los seis tests nuevos (`test_panel_inbox.py`, `test_panel_reply.py`,
  `test_panel_actions.py`, `test_panel_case_view.py`, `test_panel_audit.py`,
  `test_panel_suppression.py`) reciben la fixture `panel` y ya no importan
  `panel_helpers`; sus helpers locales también reciben `panel`.
- `panel_helpers.py` queda reducido a un docstring que indica que los helpers
  se movieron a `conftest.py` (no se puede borrar con las herramientas del
  implementer; puede eliminarse en el cierre si se desea).
- No cambia ninguna aserción ni el comportamiento cubierto: solo la forma de
  importar los helpers. `pytest.ini` sigue con `--import-mode=importlib`.

## Corrección aplicada — helpers del panel en `conftest.py`

Se eliminó la dependencia de `panel_helpers` en los seis módulos nuevos:
`test_panel_actions.py`, `test_panel_audit.py`, `test_panel_case_view.py`,
`test_panel_inbox.py`, `test_panel_reply.py` y `test_panel_suppression.py`.

- `services/orchestrator/tests/conftest.py` define las funciones compartidas
  (`make_profile`, `login`, `login_admin`, `link_case`, `add_message`,
  `case_item`, `set_presence`, `add_client_session`, `NOW`, `CSRF`) y las
  expone con el fixture `panel` (`SimpleNamespace`).
- Cada test recibe `panel` como fixture y llama `panel.login(...)`,
  `panel.link_case(...)`, etc.; los helpers locales reciben `panel` como
  parámetro. Ningún test importa módulos hermanos de `tests/`, por lo que la
  recolección con `--import-mode=importlib` ya no falla.
- `services/orchestrator/tests/panel_helpers.py` queda sin uso (el escritor no
  puede borrarlo desde sus herramientas).
- `pytest.ini` no se modificó. No cambian aserciones ni cobertura de R1–R74.

## Intento de corrección 2 — fallo de `./init.sh` (Claude)

La colección ya funciona. Resultado: `3 failed, 2786 passed, 1 skipped`.

1. `services/orchestrator/tests/test_case_reply.py::test_postgres_case_links_use_parameters_only`:
   `PostgresRepository.get_case_contact` ahora selecciona seis columnas (R13),
   pero el `_Conn` falso de ese test devuelve filas de 3 columnas →
   `IndexError: tuple index out of range` en `repository.py` (`external_chat_id=row[3]`).
   Corrección: ajustar los datos devueltos por el `_Conn` falso de ese test a
   las seis columnas (`id, channel, external_user_id, external_chat_id,
   telegram_user_id, chat_id`) sin cambiar sus aserciones (R73/T31).
2. `services/orchestrator/tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`:
   `'10 min'` no aparece en el HTML de la bandeja. Revisar `case_wait` / el
   render de la columna de espera (R4) frente a lo que espera el test y el
   design: el caso Telegram tiene último mensaje `user` hace 10 min tras un
   mensaje `advisor` hace 20 min; corregir el código o el test según el design.
3. `services/orchestrator/tests/test_panel_inbox.py::test_inbox_uses_advisor_id_from_session`:
   `panel.login(env, telegram_user_id=701)` devuelve un `Profile` con
   `telegram_user_id=None`; el helper `login` de `conftest.py` no aplica el
   `telegram_user_id` al perfil devuelto. Corregir el helper (o la aserción
   si el perfil devuelto es una copia anterior a la vinculación).

Nota: la ejecución de OpenCode para el intento 2 se quedó colgada unos 42 min sin salida ni cambios en archivos; Claude la detuvo (EXIT=143) y la relanzó una vez con el mismo contexto (intento 3).

## Corrección aplicada 3 — tres fallos de `./init.sh`

Se corrigen los tres fallos señalados por Claude sin tocar código de aplicación ni aserciones:

1. `services/orchestrator/tests/test_case_reply.py::test_postgres_case_links_use_parameters_only`:
   el `_Cursor.fetchall` falso devuelve ahora las seis columnas que selecciona
   `PostgresRepository.get_case_contact` (R13): `c1, telegram, "", "", 10, 100`.
   La aserción de `Contact` no cambia y el foco sigue siendo el SQL parametrizado.
2. `services/orchestrator/tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`:
   el vínculo `case-tg` se crea con `created_at = NOW - 30 min` para que los
   mensajes `advisor` (-20 min) y `user` (-10 min) caigan dentro de la ventana
   que el design define para `case_activity` (`at >= case_links.created_at`).
   Así `case_wait` devuelve 10 min y el caso respeta el orden esperado.
3. `services/orchestrator/tests/conftest.py::make_profile`: devuelve el perfil
   releído con `env.repo.get_profile(profile.id)` tras vincular
   `telegram_user_id`, en lugar de la copia previa a la vinculación. Corrige
   `test_inbox_uses_advisor_id_from_session` (R1) sin cambiar sus aserciones.

No se modificaron `pytest.ini`, el código de la feature ni la cobertura R1–R74.
Pendiente de ejecutar `./init.sh` por Claude (el implementer no ejecuta shell).

## Resultado final de `./init.sh` (Claude) — BLOQUEADO

Tras el intento 3: `1 failed, 2788 passed, 1 skipped` → `./init.sh` en FAIL.
Los fallos 1 (`test_case_reply.py`, `_Conn` de 6 columnas) y 3 (helper `login`
con `telegram_user_id`) quedaron corregidos. Persiste:

- `services/orchestrator/tests/test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`:
  `'10 min'` ya aparece, pero `'Abierta'` no está en el HTML de la bandeja. El
  caso WhatsApp `case-wa` tiene un mensaje `user` hace 1 h (dentro de 24 h), así
  que la columna de ventana (R5, `channel_window`) debería mostrar `Abierta`.
  Revisar en `advisor_inbox` si `last_user_message_at` usa el contacto/caso
  correcto y el mismo `now` del test (reloj inyectado), y la etiqueta que
  `render_advisor_cases` usa para el estado `open`.

Se agotaron los tres intentos de corrección permitidos (uno se quedó colgado
42 min sin cambios, Claude lo detuvo y lo relanzó). Feature sigue en
`in_progress`; no se marcó done. Hace falta un ciclo más de corrección
autorizado por el leader (con este informe como `--context`).

Comandos: `bash scripts/run_opencode_writer.sh panel_asesores_multicanal`
(implementación) y `... --context progress/impl_panel_asesores_multicanal.md`
(correcciones); `bash ./init.sh` tras cada respuesta `done`.
Trazabilidad R1–R74 → test: presente en la sección de trazabilidad de este informe.

## Ciclo de corrección adicional (autorizado por el leader) — diagnóstico

Fallo: `test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`
no muestra `Abierta` para el caso WhatsApp.

Causa: en `services/orchestrator/orchestrator/domain.py` (construcción de
`InboxRow` en la bandeja, ~línea 3033) `channel_window(...)` recibe `last_user`
de `repo.case_activity(contact.id, link.created_at)`, que solo cuenta mensajes
posteriores al vínculo del caso. Según requirements.md ("Ventana WhatsApp
abierta") la ventana depende del último mensaje `user` del contacto sin filtrar
por caso.

Corrección pedida (mínima):
- En la bandeja, calcular la ventana con
  `repo.last_user_message_at(contact.id)` (ya existe, design.md:295) y pasar
  ese valor a `channel_window`.
- `case_wait` sigue usando los valores de `case_activity` sin cambios.
- El resto de usos de `channel_window` (detalle del caso, envío R16) ya usan
  `last_user_message_at`; no tocarlos.
- No modificar ningún test.

## Corrección aplicada 4 — ventana WhatsApp en la bandeja

En `services/orchestrator/orchestrator/domain.py::advisor_inbox` la ventana de
cada fila se calcula ahora con `repo.last_user_message_at(contact.id)`
(último mensaje `user` del contacto, sin filtrar por el vínculo del caso), tal
como exige requirements.md (R5 / «Ventana WhatsApp abierta»). `case_wait` sigue
usando los valores de `repo.case_activity(contact.id, link.created_at)` sin
cambios. El resto de usos de `channel_window` (vista del caso, envío R16) ya
usaban `last_user_message_at` y no se tocan. No se modificó ningún test.

Esto corrige el único fallo persistente de `./init.sh`
(`test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`, que
esperaba `Abierta` para `case-wa` con un mensaje `user` de hace 1 h) y no
altera la cobertura de R1–R74: R5 sigue cubierto por
`test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role` y
`test_panel_pure.py::test_channel_window_boundaries_and_telegram`.

Pendiente: Claude ejecuta `./init.sh` y añade el resultado.

## Resultado de `./init.sh` tras corrección 4 (Claude)

`2789 passed, 1 skipped` → `./init.sh` en OK. Pendiente revisión de código del reviewer.
