# Implementación — orquestador_basico

Estado: T1..T29 hechas; `./init.sh` verde (460 tests). Pendiente de reviewer (no marcada `done`).
Se instalaron `httpx` y `pg8000` en `.venv` desde `services/orchestrator/requirements.txt`.
`tests/fakes.py` reexporta los fakes; los helpers van en `tests/conftest.py` (modo importlib).

## Trazabilidad R -> test
(archivos en services/orchestrator/tests/)

| R | Test |
|---|---|
| R1 | test_messages::test_new_message_returns_202_accepted_and_is_processed |
| R2 | test_messages::test_duplicate_update_returns_202_duplicate_without_processing |
| R3 | test_messages::test_messages_without_token_returns_401 |
| R4 | test_messages::test_messages_invalid_body_returns_422 |
| R5 | test_messages::test_new_telegram_user_creates_contact |
| R6 | test_messages::test_existing_telegram_user_reuses_contact |
| R7, R8 | test_messages::test_incoming_and_outgoing_messages_saved_with_dates |
| R9 | test_messages::test_rag_answer_event_saved |
| R10 | test_messages::test_no_results_event_saved |
| R11 | test_messages::test_handover_event_saved |
| R12 | test_messages::test_search_called_with_text_and_rag_top_k |
| R13 | test_decisions::test_empty_search_does_not_call_llm |
| R14 | test_decisions::test_empty_search_sends_no_answer_reply |
| R15 | test_decisions::test_empty_search_requests_handover_no_relevant_chunks |
| R16 | test_decisions::test_chunks_call_llm_once_with_question_and_fragments |
| R17 | test_decisions::test_prompt_delimits_question_and_fragments_as_data |
| R18 | test_decisions::test_llm_answer_sent_to_chat |
| R19 | test_decisions::test_keyword_triggers_handover_user_request_without_rag_or_llm, test_keyword_match_ignores_case_accents_and_spaces |
| R20 | test_decisions::test_keyword_triggers_handover_user_request_without_rag_or_llm |
| R21 | test_decisions::test_ack_sent_when_notified_for_user_request |
| R22 | test_decisions::test_handover_request_has_new_case_id_and_last_10_chronological |
| R23, R38 | test_decisions::test_rag_failure_sends_error_reply_and_event |
| R24, R40 | test_decisions::test_llm_failure_or_empty_sends_error_reply_and_event |
| R25 | test_decisions::test_handover_failure_or_no_advisors_saves_event |
| R26 | test_messages::test_failed_send_is_not_saved_as_outgoing |
| R27 | test_security::test_instruction_message_only_triggers_search_send_handover |
| R28 | test_security::test_llm_client_accepts_only_system_and_user_text, test_adapters::test_http_llm_client_sends_only_system_and_user |
| R29 | test_security::test_package_has_no_eval_exec_subprocess_pickle |
| R30 | test_security::test_logs_do_not_contain_message_text |
| R31 | FakeRepository usado en todos los tests; test_adapters::test_postgres_repository_uses_parameters_only |
| R32 | test_adapters::test_http_clients_send_service_token_url_and_timeout |
| R33 | test_config::test_settings_defaults, test_rag_top_k_out_of_range_rejected |
| R34 | test_config::test_import_main_without_env_does_not_connect, test_adapters::test_postgres_repository_connects_lazily |
| R35 | test_config::test_only_health_and_messages_routes_exposed |
| R36 | test_decisions::test_prompt_has_system_instruction_about_data |
| R37 | test_decisions::test_prompt_neutralizes_closing_tags |
| R39 | test_decisions::test_rag_failure_does_not_call_llm_or_handover |
| R41 | test_adapters::test_postgres_repository_uses_parameters_only |
| R42 | test_config::test_env_example_lists_all_variables |
