# Review — feature 15 (contrato_conversacion_caso)

**Veredicto:** APPROVED

Verificación ejecutada (2026-11-01, modo nocturno):
- `bash ./init.sh` → 1014 passed, 1 warning (deprecación de `starlette.testclient`, ajena); entorno OK.
- `.venv/Scripts/python.exe -m pytest contracts` → 434 passed (línea base 385 + 49 nuevos).

## Trazabilidad requirements ↔ tests
- R1: [x] `test_doc_has_a_section_per_route` (ROUTES, `test_contratos_doc.py:25`)
- R2: [x] `test_route_names_exposing_service[POST /cases/{id}/client-message]`
- R3: [x] `test_route_names_caller[...]`, `test_client_message_route_is_called_by_orchestrator` (`test_contratos_doc.py:738`)
- R4: [x] `test_route_names_models_in_package[...]`
- R5: [x] `test_request_table_lists_every_request_field[...]`
- R6: [x] `test_response_section_has_success_code_and_fields[...]` (SUCCESS_CODES, `:56`)
- R7: [x] `test_errors_table_has_common_rows[...]`
- R8: [x] `test_errors_table_has_route_specific_rows[...]` (OWN_ERRORS, `:39`)
- R9: [x] `test_client_message_errors_table_has_internal_error` (`:743`)
- R10: [x] `test_client_message_section_documents_path_id` (`:750`)
- R11: [x] `test_client_message_section_documents_statuses` (`:757`)
- R12: [x] `test_client_message_upstream_error_row_mentions_advisor` (`:772`)
- R13: [x] `test_client_message_error_codes_are_declared_in_common_rules` (`:780`)
- R14: [x] `test_close_route_is_also_called_by_orchestrator` (`:788`)
- R15: [x] `test_assumptions_include_client_message_forwarding` (`:795`)
- R16: [x] `test_assumptions_s13_forward_failure_does_not_fall_back_to_rag` (`:809`)
- R17: [x] `test_assumptions_s13_advisor_commands_use_messages_route` (`:816`)
- R18: [x] `test_assumptions_s13_advisor_id_is_telegram_sender` (`:828`)
- R19: [x] `test_case_client_message_request_requires_text_and_at` (`test_models.py:587`)
- R20: [x] idem + `test_missing_required_field_is_rejected[CaseClientMessageRequest.text]`
- R21: [x] `test_missing_required_field_is_rejected[CaseClientMessageRequest.at]`
- R22: [x] `test_case_client_message_request_rejects_naive_at` (`test_models.py:599`)
- R23: [x] `test_case_client_message_request_rejects_invalid_text[empty|too_long]`, `..._accepts_text_at_max_length`
- R24: [x] `test_case_client_message_response_requires_status_and_case_id`, `..._accepts_valid_status`
- R25: [x] `test_case_client_message_response_rejects_invalid_status` (`test_models.py:651`)
- R26: [x] `test_invalid_identifier_is_rejected[*-CaseClientMessageResponse.case_id]` (IDENTIFIER_FIELDS, `:201`)
- R27: [x] `test_unexpected_field_is_rejected[CaseClientMessageRequest|CaseClientMessageResponse]` (BASE_EXAMPLES, `:73-74`)
- R28: [x] `test_model_is_exported_and_is_base_model[...]` (`test_packaging.py:39-40`)
- R29: [x] `test_every_example_validates_against_its_model[case_client_message_request.json]`
- R30: [x] `...[case_client_message_response.json]`
- R31: [x] `...[case_client_message_response_not_assigned.json]`
- R32: [x] `test_every_example_file_is_mapped`, `test_every_model_has_an_example` (`test_examples.py:61-63, 91-92`)
- R33: [x] `test_message_request_requires_its_fields`, `test_message_response_accepts_valid_status`; `### POST /messages` y `messages.py` sin diff
- R34: [x] batería previa intacta; únicas líneas eliminadas atribuibles a la #15: `- **Llama:**` de close y docstring de `cases.py`. Las otras eliminaciones del diff contra HEAD (fila `409 case_closed` de Reglas comunes, fila `S11`) son de la #13, aún sin commitear, no de esta feature. Ningún JSON existente modificado.
- R35: [x] 434 passed en `contracts`, 1014 en total, sin tests eliminados.
- R36: [x] `test_assumptions_s13_non_command_advisor_message_follows_current_flow` (`:840`)
- R37: [x] `test_assumptions_s13_advisor_list_matches_sender_user_id` (`:857`)
- R38: [x] `test_assumptions_s13_advisor_commands_follow_s12` (`:850`)
- R39: [x] `test_assumptions_s13_group_ids_cannot_use_commands` (`:868`)

## Tasks completas
- T0–T34: [x] (todas marcadas en `specs/contrato_conversacion_caso/tasks.md`; T0/T28/T29 verificadas por el puente y reconfirmadas en esta revisión)

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0
- C2: [x] una sola feature `in_progress` (#15)
- C3: [x] solo `contracts/`; ruta documentada en `CONTRATOS.md`; sin dependencias ni variables nuevas; sin secretos ni `print()`
- C4: [x] tests verdes, sin red ni BD real
- C5: [x] sin archivos sospechosos atribuibles a la feature (el cierre de sesión lo hace el leader)
- C6: [x] specs completos, EARS, design con supuestos y alternativas, R1–R39 cubiertos

## Observaciones (no bloqueantes)
- `progress/impl_contrato_conversacion_caso.md` sección «Tasks» aún dice T0/T28/T29 «pendientes»; la sección «Verificación» posterior las cierra. Cosmético.
- Las celdas «Dónde» de `404`/`502` en `## Reglas comunes` no listan la ruta nueva: decisión explícita de `design.md` §1.
