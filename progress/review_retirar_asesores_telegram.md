# Review — feature 48 (retirar_asesores_telegram)

**Veredicto:** APPROVED

`bash ./init.sh` ejecutado una vez en esta revisión: exit 0, `3076 passed, 1 skipped`.

## Trazabilidad requirements ↔ tests
Se comprobó que cada test citado existe en el árbol (búsqueda por `def <nombre>`).

- R1: [x] `orchestrator/tests/test_advisor_commands.py::test_telegram_text_is_ordinary_and_does_not_touch_cases`, `::test_command_text_is_not_removed_from_sender_history`
- R2: [x] `test_advisor_commands.py::test_command_text_does_not_close_an_assigned_case`; `orchestrator/tests/test_security.py::test_security_responder_text_is_ordinary_and_never_authorizes`
- R3: [x] `orchestrator/tests/test_db_query.py::test_consultar_runs_query_without_storing_message_rag_or_handover`
- R4: [x] `orchestrator/tests/test_advisor_panel.py::test_unlinked_profile_can_act_with_profile_id`
- R5: [x] `test_advisor_panel.py::test_unlinked_profile_can_act_with_profile_id`
- R6: [x] `orchestrator/tests/test_authorization.py::test_reply_authorize_unavailable_returns_502_without_sending`
- R7: [x] `orchestrator/tests/test_client_forward.py::test_assigned_case_message_is_forwarded_without_rag`
- R8: [x] `handover/tests/test_client_message.py::test_client_message_assigned_case_is_available_in_panel`; `orchestrator/tests/test_security.py::test_security_client_text_is_not_interpreted_nor_sent_by_telegram`
- R9: [x] `handover/tests/test_advisor_sync.py::test_sync_persists_roster_and_generation`
- R10: [x] `test_advisor_sync.py::test_sync_requires_valid_service_token`
- R11: [x] `test_advisor_sync.py::test_sync_rejects_invalid_request`
- R12: [x] `test_advisor_sync.py::test_sync_persistence_failure_returns_500`
- R13: [x] `orchestrator/tests/test_advisor_roster.py::test_begin_change_marks_pending_and_publish_marks_synced`, `::test_ensure_roster_ready_syncs_pending_state`, `::test_creating_advisor_profile_publishes_the_roster`; `handover/tests/test_startup.py::test_startup_log_reports_roster_count`
- R14: [x] `handover/tests/test_handover.py::test_handover_creates_case_and_queues_it_without_telegram`, `::test_handover_reuses_assigned_case`
- R15: [x] `test_handover.py::test_handover_without_advisors_returns_no_advisors_and_does_not_send`
- R16: [x] `orchestrator/tests/test_case_reply.py::test_no_advisors_sends_fixed_reply_to_client`
- R17: [x] `handover/tests/test_authorization.py::test_authorize_unassigned_case_allows_any_registered_advisor`
- R18: [x] `orchestrator/tests/test_case_reply.py::test_reply_assigns_case_in_handover` (línea 108). Nota: `impl_*.md` cita `test_reply_assign_failure_still_returns_sent`, que no verifica R18; la cobertura real es la indicada aquí.
- R19: [x] `handover/tests/test_authorization.py::test_authorize_assigned_case_rejects_other_advisor`
- R20: [x] `test_authorization.py::test_authorize_close_orphan_case_allowed_for_any_registered_advisor`
- R21: [x] `test_authorization.py::test_close_orphan_case_by_any_registered_advisor`
- R22: [x] `test_authorization.py::test_orphan_case_cannot_be_replied_or_assigned_by_other_advisor`
- R23: [x] `test_authorization.py::test_authorize_unregistered_advisor_returns_403_before_checking_case`
- R24: [x] `handover/tests/test_cases.py::test_close_is_idempotent_and_keeps_first_closure`
- R25: [x] `test_cases.py::test_assign_already_assigned_keeps_first_advisor`
- R26: [x] `handover/tests/test_list_cases.py::test_orphan_cases_offer_only_close`
- R27: [x] `test_client_message.py::test_client_message_assigned_case_is_available_in_panel`
- R28: [x] `test_client_message.py::test_client_message_not_assigned_cases_send_nothing`
- R29: [x] `test_authorization.py::test_registered_advisor_matches_profile_id_exactly`
- R30: [x] `test_advisor_sync.py::test_sync_migrates_telegram_assignment_to_profile_id`
- R31: [x] `test_advisor_sync.py::test_sync_marks_unknown_assignment_as_orphan`
- R32: [x] `test_advisor_sync.py::test_sync_preserves_case_identity_and_timestamps`
- R33: [x] `test_advisor_sync.py::test_repeated_sync_does_not_reinterpret_profile_ids`
- R34: [x] `test_advisor_roster.py::test_creating_advisor_profile_publishes_the_roster`
- R35: [x] `test_advisor_roster.py::test_handover_with_pending_roster_calls_no_handover`
- R36: [x] `test_advisor_sync.py::test_stale_generation_is_rejected_with_503`, `::test_list_cases_with_stale_generation_is_rejected`
- R37: [x] `test_advisor_roster.py::test_failed_sync_keeps_pending_and_fails_closed`
- R38: [x] `contracts/tests/test_contratos_doc.py::test_assumptions_s6_identity_is_profile_id`
- R39: [x] `test_contratos_doc.py::test_sync_route_error_codes`
- R40: [x] `test_contratos_doc.py::test_client_message_section_documents_statuses`
- R41: [x] `contracts/tests/test_models.py::test_advisor_roster_sync_request_requires_generation_and_profiles`
- R42: [x] `contracts/tests/test_examples.py::test_every_model_has_an_example` (ejemplos `advisor_roster_sync_{request,response}.json`)
- R43: [x] `test_models.py::test_advisor_roster_sync_request_requires_generation_and_profiles`
- R44: [x] `handover/tests/test_config.py::test_settings_work_without_advisor_chat_ids`; `test_startup.py` línea 43
- R45: [x] `handover/tests/test_production_config.py::test_advisor_chat_ids_is_removed_from_deployment_files` (`.env.example`, `docker-compose.yml`, `render.yaml`)
- R46: [x] `test_contratos_doc.py::test_assumptions_s13_advisor_commands_are_retired`; búsqueda en `docs/`, `README.md`, `AGENTS.md` sin `ADVISOR_CHAT_IDS`
- R47: [x] `test_advisor_commands.py::test_command_text_does_not_send_anything_to_the_case_client`; `test_security.py::test_security_responder_text_is_ordinary_and_never_authorizes`
- R48: [x] conjunto anterior (R4/R5, R30/R31, R17–R23, R26, R9–R13, R44, R38–R43)
- R49: [x] `test_advisor_sync.py` (token ausente/inválido, cuerpo inválido, persistencia, 500)
- R50: [x] `test_advisor_roster.py::test_mark_synced_only_for_current_generation`, `::test_handover_with_pending_roster_calls_no_handover`; `test_advisor_sync.py::test_stale_generation_is_rejected_with_503`
- R51: [x] `orchestrator/tests/test_security.py` conserva 11 tests (11 en HEAD); `handover/tests/test_security.py` solo adapta el estado. Las aserciones retiradas corresponden a la ruta de comandos eliminada; el fallo cerrado ante handover caído sigue cubierto en el panel (R6).
- R52: [x] `./init.sh` exit 0 en esta revisión

## Tasks completas
- T1–T11: [x]
- T12: [ ] en `specs/retirar_asesores_telegram/tasks.md`, con justificación documentada en `progress/impl_retirar_asesores_telegram.md` («Verificación»: el writer no tiene shell; `./init.sh` queda a cargo de Claude). La parte pendiente (`./init.sh`) quedó satisfecha en esta revisión: verde. Aceptada.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0
- C2: [x] una sola feature `in_progress` (#48); `progress/current.md` describe la sesión activa
- C3: [x] sin imports entre servicios; `POST /advisors/sync` documentada en `contracts/CONTRATOS.md`; sin cambios en `requirements*.txt`; `.env` sin trackear; sin `print()` de debug/`eval`/`exec` nuevos (los `print` de `bootstrap_admin.py` son salida de CLI previa)
- C4: [x] 3076 tests verdes con adaptadores falsos; pruebas de seguridad presentes y verdes
- C5: [x] sin archivos sin trackear sospechosos. La entrada de cierre en `progress/history.md` corresponde al leader al cerrar la sesión
- C6: [x] `specs/retirar_asesores_telegram/` con los 3 archivos; cada `R<n>` con test. Las tasks deben quedar todas `[x]` antes de pasar a `done` (ver T12)

## Observaciones no bloqueantes (para el cierre)
1. Marcar T12 `[x]` en `specs/retirar_asesores_telegram/tasks.md` y anexar el resultado de `./init.sh` (3076 passed, 1 skipped) en `progress/impl_retirar_asesores_telegram.md`, cuya línea R52 y sección final aún dicen «pendiente».
2. `progress/impl_retirar_asesores_telegram.md` R18: corregir la cita a `test_reply_assigns_case_in_handover`.
3. `services/handover/tests/test_list_cases.py:99`: el docstring aún menciona `ADVISOR_CHAT_IDS`; el identificador ya es el roster de perfiles.
4. Añadir la entrada de sesión de #48 en `progress/history.md` al cerrar.
