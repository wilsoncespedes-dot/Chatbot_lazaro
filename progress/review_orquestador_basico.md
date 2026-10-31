# Review — feature orquestador_basico

**Veredicto:** APPROVED

`./init.sh` termina verde (460 tests pasan, 1 warning de deprecación de Starlette que no afecta).

## Trazabilidad requirements ↔ tests
Todos los tests citados existen en `services/orchestrator/tests/` (verificado por nombre). Tabla completa en `progress/impl_orquestador_basico.md`.
- R1: [x] `test_new_message_returns_202_accepted_and_is_processed`
- R2: [x] `test_duplicate_update_returns_202_duplicate_without_processing`
- R3: [x] `test_messages_without_token_returns_401`
- R4: [x] `test_messages_invalid_body_returns_422`
- R5: [x] `test_new_telegram_user_creates_contact`
- R6: [x] `test_existing_telegram_user_reuses_contact`
- R7: [x] `test_incoming_and_outgoing_messages_saved_with_dates`
- R8: [x] `test_incoming_and_outgoing_messages_saved_with_dates`
- R9: [x] `test_rag_answer_event_saved`
- R10: [x] `test_no_results_event_saved`
- R11: [x] `test_handover_event_saved`
- R12: [x] `test_search_called_with_text_and_rag_top_k`
- R13: [x] `test_empty_search_does_not_call_llm`
- R14: [x] `test_empty_search_sends_no_answer_reply`
- R15: [x] `test_empty_search_requests_handover_no_relevant_chunks`
- R16: [x] `test_chunks_call_llm_once_with_question_and_fragments`
- R17: [x] `test_prompt_delimits_question_and_fragments_as_data`
- R18: [x] `test_llm_answer_sent_to_chat`
- R19: [x] `test_keyword_triggers_handover_user_request_without_rag_or_llm`, `test_keyword_match_ignores_case_accents_and_spaces`
- R20: [x] `test_keyword_triggers_handover_user_request_without_rag_or_llm`
- R21: [x] `test_ack_sent_when_notified_for_user_request`
- R22: [x] `test_handover_request_has_new_case_id_and_last_10_chronological`
- R23: [x] `test_rag_failure_sends_error_reply_and_event`
- R24: [x] `test_llm_failure_or_empty_sends_error_reply_and_event`
- R25: [x] `test_handover_failure_or_no_advisors_saves_event`
- R26: [x] `test_failed_send_is_not_saved_as_outgoing`
- R27: [x] `test_instruction_message_only_triggers_search_send_handover`
- R28: [x] `test_llm_client_accepts_only_system_and_user_text`, `test_http_llm_client_sends_only_system_and_user`
- R29: [x] `test_package_has_no_eval_exec_subprocess_pickle`
- R30: [x] `test_logs_do_not_contain_message_text`. Los `logger.*` revisados en `domain.py`, `main.py` y `adapters/*` solo registran ids y códigos.
- R31: [x] `FakeRepository` en todos los tests y `test_postgres_repository_uses_parameters_only`
- R32: [x] `test_http_clients_send_service_token_url_and_timeout`, `test_http_clients_raise_service_unavailable_on_errors`
- R33: [x] `test_settings_defaults`, `test_rag_top_k_out_of_range_rejected`
- R34: [x] `test_import_main_without_env_does_not_connect`, `test_postgres_repository_connects_lazily`
- R35: [x] `test_only_health_and_messages_routes_exposed`
- R36: [x] `test_prompt_has_system_instruction_about_data`
- R37: [x] `test_prompt_neutralizes_closing_tags`
- R38: [x] `test_rag_failure_sends_error_reply_and_event`
- R39: [x] `test_rag_failure_does_not_call_llm_or_handover`
- R40: [x] `test_llm_failure_or_empty_sends_error_reply_and_event`
- R41: [x] `test_postgres_repository_uses_parameters_only`
- R42: [x] `test_env_example_lists_all_variables`

## Tasks completas
- T1 a T29: [x] todas marcadas `[x]` en `specs/orquestador_basico/tasks.md`.

## Revisión de archivos
- Arquitectura: [x] los adaptadores importan solo `lazaro_contracts` y el `domain` del propio servicio. No hay imports entre servicios. `main.py` mantiene el patrón de `create_app` y el manejo de errores del esqueleto.
- Dependencias: [x] `httpx>=0.27,<1` y `pg8000>=1.31,<2` están acotadas en `requirements.txt`.
- No se encontraron `print`, `eval`, `exec`, `subprocess`, `pickle` ni TODOs en `services/orchestrator/orchestrator`.
- Solo hay `/health` y `/messages`. La deduplicación es síncrona y el procesamiento va en `BackgroundTasks`.

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x]
- C4: [x]
- C5: [x] El cierre de sesión (`progress/history.md`) y el paso a `done` los gestiona el leader. No es bloqueante para esta revisión.
- C6: [x]

## Cambios requeridos
Ninguno.
