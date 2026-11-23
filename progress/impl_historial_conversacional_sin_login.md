# Implementación — historial_conversacional_sin_login

## Trazabilidad

- R1 → `services/orchestrator/tests/test_conversational_memory.py::test_optional_login_includes_recent_messages_for_same_contact`
- R2 → `services/orchestrator/tests/test_conversational_memory.py::test_current_message_is_removed_but_previous_same_text_is_kept`
- R3 → `services/orchestrator/tests/test_conversational_memory.py::test_casual_history_is_limited_to_memory_context_messages`
- R4 → `services/orchestrator/tests/test_conversational_memory.py::test_casual_history_is_isolated_by_contact_and_channel`
- R5 → `services/orchestrator/tests/test_conversational_memory.py::test_memory_disabled_omits_casual_history_and_permanent_memory`
- R6 → `services/orchestrator/tests/test_conversational_memory.py::test_unconsented_contact_history_never_reaches_llm`
- R7 → `services/orchestrator/tests/test_conversational_memory.py::test_active_authenticated_session_keeps_existing_context`; también `services/orchestrator/tests/test_conversational_mode.py::test_memory_enabled_includes_active_session_history`
- R8 → `services/orchestrator/tests/test_conversational_memory.py::test_context_reuses_repository_and_adds_no_storage_schema`
- R9 → `services/orchestrator/tests/test_conversational_memory.py::test_required_login_does_not_fall_back_to_contact_history`

## Cambios

Se agregó `_conversational_context` en `domain.py`; el fallback conversacional
usa el historial del contacto sin sesión solo con `MEMORY_ENABLED=true` y
`IDENTITY_LOGIN_REQUIRED=false`. Se agregó `test_conversational_memory.py` para
validar límites, aislamiento y puertas de privacidad/identidad.

## Verificación

`./init.sh` pasó los checks del arnés y arrancó pytest, pero la suite completa permaneció silenciosa por más de dos minutos y se interrumpió por instrucción del líder. La ejecución enfocada `test_conversational_memory.py -q` terminó con **9 passed**. Revisión estática final aprobada.
