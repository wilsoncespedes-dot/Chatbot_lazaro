# Implementación — modo_conversacional_general

## Trazabilidad

- R1 → `services/orchestrator/tests/test_conversational_mode.py::test_no_hit_can_send_general_answer_without_counting_rag_failure`
- R2 → `services/orchestrator/tests/test_conversational_mode.py::test_no_hit_can_send_general_answer_without_counting_rag_failure`
- R3 → `services/orchestrator/tests/test_conversational_mode.py::test_manual_required_uses_fixed_rejection_and_existing_handover`
- R4 → `services/orchestrator/tests/test_conversational_mode.py::test_manual_required_uses_fixed_rejection_and_existing_handover`
- R5 → `services/orchestrator/tests/test_conversational_mode.py::test_parse_conversational_answer_rejects_invalid_or_unsafe_shapes`, `test_invalid_conversational_output_fails_closed`, `test_invalid_conversational_output_uses_existing_handover_threshold`
- R6 → `services/orchestrator/tests/test_conversational_mode.py::test_configured_business_term_overrides_general_classification`, `test_business_term_match_uses_whole_words`
- R7 → `services/orchestrator/tests/test_conversational_mode.py::test_memory_enabled_includes_active_session_history`
- R8 → `services/orchestrator/tests/test_conversational_mode.py::test_memory_disabled_omits_session_context_from_conversational_prompt`, `test_memory_enabled_without_active_session_omits_context`
- R9 → `services/orchestrator/tests/test_conversational_mode.py::test_rag_hits_keep_citation_prompt_and_existing_validation`
- R10 → `services/orchestrator/tests/test_conversational_mode.py::test_rag_unavailable_does_not_invoke_conversational_fallback`
- R11-R12 → `services/orchestrator/tests/test_conversational_mode.py::test_conversation_reuses_existing_schema_and_outbox`
- R13 → `services/orchestrator/tests/test_conversational_mode.py::test_conversation_reuses_existing_schema_and_outbox`
- R14 → `services/orchestrator/tests/test_conversational_mode.py::test_conversation_mode_does_not_add_a_service`
- R15 → `services/orchestrator/tests/test_security.py::test_instruction_message_only_triggers_search_send_handover`

## Verificación

- `python -m compileall` de los módulos y tests modificados: correcto.
- `./init.sh`: falló antes de pytest (`find_python.sh` con CRLF; WSL no inició su sesión systemd).
- Pruebas enfocadas: no pudieron arrancar; `python -m pytest` responde `No module named pytest`.
- Revisión estática del reviewer: aprobada; no sustituye la ejecución de pytest.
