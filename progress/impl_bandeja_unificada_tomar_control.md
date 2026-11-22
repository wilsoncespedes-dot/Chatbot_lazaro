# Implementación — #68 `bandeja_unificada_tomar_control`

## Resumen

- Bandeja nueva `/asesor/conversaciones` (asesores y supervisores) con estado
  derivado: `atendida_por_bot`, `atendida_por_asesor`, `pendiente` o `cerrada`;
  canal, última actividad y asesor; filtros `canal`/`estado`, orden con
  `pendiente` primero y límite configurable.
- Lectura en vivo `/asesor/conversaciones/{contact_id}` solo lectura, con
  auditoría `conversation_read`; refresco `/asesor/live/conversaciones[/{id}]`
  sin auditoría adicional.
- `POST /asesor/conversaciones/{id}/tomar` con CSRF y auditoría
  `conversation_take`: crea el caso si no existe y lo asigna en una operación
  atómica; 303 al caso, 409 `case_changed`, 404 y 403/502 según requisitos.
  Handover expone `POST /cases/take` atómico y `GET /cases?scope=overview`.
- «Devolver al bot» reutiliza `/asesor/return`; resolver registra `case_closed`
  y devolver no.
- Ajustes `PANEL_BOT_CONVERSATIONS_VISIBLE` y `PANEL_CONVERSATIONS_LIMIT`.
- Contrato: `CaseTakeRequest`, `CaseTakeResponse`, `scope=overview` y razón
  `advisor_take`; `actions` puede ser `[]` en `overview`.

## Trazabilidad R1–R7

- **R1** → `services/orchestrator/tests/test_conversations_pure.py::test_advisor_wins_when_open_case_has_advisor`, `::test_pending_when_open_case_has_no_advisor`, `::test_pending_when_with_advisor_without_case`, `::test_closed_when_resolved_after_last_user_message`, `::test_bot_after_client_writes_again`, `::test_bot_without_closed_case`, `::test_closed_case_does_not_count_as_open`, `::test_status_vocabulary_has_exactly_four_values`; `services/orchestrator/tests/test_bandeja_unificada.py::test_list_shows_all_states_without_excluded_or_empty_contacts`, `::test_pending_conversations_come_first`, `::test_channel_and_status_filters_combine_with_and`, `::test_invalid_filters_are_422_without_calling_handover`, `::test_inbox_limit_is_configurable`.
- **R2** → `services/orchestrator/tests/test_lectura_conversacion.py::test_bot_conversation_is_read_only`, `::test_reading_records_audit_without_message_text` (acción `conversation_read`), `::test_reading_does_not_change_state_or_send_anything`, `::test_live_history_matches_initial_and_does_not_audit`, `::test_own_assigned_conversation_redirects_to_case`, `::test_unknown_invalid_or_excluded_conversation_is_404`; `test_bandeja_unificada.py::test_live_table_matches_initial_load`.
- **R3** → `services/orchestrator/tests/test_tomar_conversacion.py::test_take_creates_links_and_moves_to_with_advisor`, `::test_take_pending_case_assigns_without_creating_another`, `::test_take_is_idempotent_after_the_advisor_already_took`, `::test_take_assigned_to_another_advisor_is_409`, `::test_two_advisors_concurrently_only_one_takes`, `::test_handover_unavailable_returns_502_without_changing_state`, `::test_take_maps_handover_denials`, `::test_take_excluded_state_is_404_without_creating_case`, `::test_take_without_valid_csrf_is_403_without_effects`, `::test_unlinked_advisor_cannot_take`, `::test_bot_is_silent_after_take`, `::test_supervisor_cannot_take_another_advisors_conversation`; `services/handover/tests/test_take_case.py::test_concurrent_advisors_create_a_single_case`, `::test_take_is_idempotent_for_the_same_advisor`.
- **R4** → `services/orchestrator/tests/test_devolver_conversacion.py::test_return_reuses_existing_route_and_bot_resumes`, `::test_resolving_records_case_closed_only_then`.
- **R5** → `services/orchestrator/tests/test_lectura_conversacion.py::test_bot_visibility_true_shows_bot_and_closed`, `::test_bot_visibility_can_be_disabled`; `test_tomar_conversacion.py::test_take_bot_is_403_when_visibility_is_disabled`, `::test_non_advisor_role_is_denied`, `::test_new_routes_do_not_expose_suppression_execution`; `test_lectura_conversacion.py::test_purged_contact_is_not_listed_or_readable`.
- **R6** → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`; `test_conversations_pure.py::test_only_states_with_content_are_listable`; `test_bandeja_unificada.py::test_list_shows_all_states_without_excluded_or_empty_contacts`; `test_lectura_conversacion.py::test_purged_contact_is_not_listed_or_readable`.
- **R7** → conjunto anterior (estados, lectura + auditoría, tomar con y sin caso, concurrencia, devolver y permisos) y `./init.sh` verde.

## Alineación con la revisión

- Estados visibles alineados con `requirements.md`: el código usa ahora
  `atendida_por_bot` y `atendida_por_asesor` (antes `bot` y `asesor`), incluidos
  filtros, etiquetas, badges y el parámetro `estado`.
- Auditoría de lectura renombrada a `conversation_read` en la ruta y en el test.
- Trazabilidad del informe reescrita sobre los R1–R7 vigentes.
- T5 marcada `[x]`: el informe ya recoge la ejecución de la batería; Claude
  vuelve a ejecutar `./init.sh` al cerrar esta sesión y anexa el resultado.
- `feature_list.json` no se modifica. Solo #68 está `in_progress`; el cierre de
  estado corresponde al leader.

## Notas de implementación

- `GET /cases?scope=overview` devuelve `actions=[]`; el modelo `CaseListItem`
  deja de exigir acciones no vacías para ese caso.
- `POST /cases/take` usa un advisory lock por `contact_id` en Postgres y un
  `threading.Lock` en el repositorio falso.
- El `FakeHandoverClient` recuerda la asignación por contacto para probar
  concurrencia e idempotencia sin red.
- `Env.clock()` (fixture de `services/orchestrator/tests/conftest.py`) devuelve
  `adapters.clock()`; corrigió los 32 fallos iniciales de los tests nuevos.

## Verificación

- Última ejecución registrada de `python -m pytest services/orchestrator -q` +
  `./init.sh`: **4403 passed, 1 skipped, 0 fallos**. Claude re-ejecutará
  `./init.sh` al cerrar esta sesión y anexará el nuevo resultado.
- Único `[FAIL]` del harness en esa ejecución: «2 features en in_progress»; a
  día de hoy solo #68 figura `in_progress` en `feature_list.json` (el leader
  mantiene el estado).

## Resultado init.sh (correccion del reviewer)
./init.sh verde: 4403 passed, 1 skipped; una sola feature in_progress. Trazabilidad R1-R7 -> tests arriba.
