# impl_traspaso_automatico_fallos

Estado: implementado y tests escritos; Claude ejecutará `./init.sh` y añadirá el
resultado. No se marca la feature `done`.

Sin cambios de contrato, dependencias nuevas ni código de terceros.

## Cambios

- `orchestrator/config.py`: `AUTO_HANDOVER_FAILURE_THRESHOLD` (default 3, entero
  >= 1) y `AUTO_HANDOVER_FAILURE_REASONS` (allowlist). Validación al iniciar con
  el nombre de la variable; `invalid_answer` se excluye del conteo efectivo si
  `INVALID_ANSWER_HANDOVER=false`.
- `.env.example`: las dos variables nuevas con sus defaults.
- `orchestrator/adapters/repository.py`: `record_rag_outcome`, `reset_rag_streak`
  y `finish_auto_handover` en el protocolo, `FakeRepository` y
  `PostgresRepository`. Tablas `auto_handover_outcomes` (idempotencia por
  contacto+update) y `auto_handover_streaks` (conteo y estado
  `open`/`pending`/`retry`/`handed_over`). SQL parametrizado y transacción
  atómica bajo el lock existente.
- `orchestrator/domain.py`: los fallos elegibles registran racha; al cruzar el
  umbral se llama una sola vez a `_handover` con el motivo actual. `notified`
  envía/guarda `HANDOVER_ACK_REPLY`; `no_advisors` envía `NO_ADVISORS_REPLY` y
  cierra la racha; si handover no está disponible queda en `retry`. La respuesta
  válida reinicia; los errores de RAG/LLM, comandos, privacidad, reenvío asignado
  y `user_request` no cuentan (este último reinicia).
- Tests: nuevo `tests/test_auto_handover.py`. Se ajustaron cinco tests previos
  para fijar umbral 1 donde comprobaban la derivación inmediata de la feature
  anterior y se añadió la comprobación del ACK; ninguna aserción se eliminó.

## Trazabilidad R → test

Tests en `services/orchestrator/tests/test_auto_handover.py` salvo indicación.

| R | Test |
|---|---|
| R1 | `test_failures_below_threshold_do_not_hand_over`, `test_no_relevant_chunks_is_not_counted_when_outside_the_policy`, `test_invalid_answer_counts_when_enabled` |
| R2 | `test_rag_and_llm_errors_do_not_count_or_break_the_streak`, `test_commands_privacy_and_user_request_are_not_counted`, `test_forwarded_assigned_conversation_is_not_counted`, `test_invalid_answer_is_not_counted_when_handover_is_disabled` |
| R3 | `test_threshold_and_reasons_defaults`, `test_env_example_documents_auto_handover_defaults`, `test_invalid_answer_is_excluded_when_its_handover_is_disabled` |
| R13 | `test_invalid_threshold_prevents_start`, `test_invalid_reasons_prevent_start_and_name_the_variable` |
| R4 | `test_streak_is_isolated_by_contact`, `test_postgres_rag_outcomes_use_parameterized_sql`, `test_streak_survives_a_restart_and_retry_is_persisted` |
| R5 | `test_repeated_update_id_does_not_increment_the_streak`, `test_postgres_rag_outcomes_use_parameterized_sql`, `test_streak_survives_a_restart_and_retry_is_persisted` |
| R6 | `test_valid_answer_resets_the_streak`, `test_valid_answer_after_handover_opens_a_new_streak` |
| R7 | `test_failures_below_threshold_do_not_hand_over`, `test_invalid_answer_counts_when_enabled` |
| R8 | `test_extra_failures_after_notified_do_not_derive_again`, `test_no_advisors_sends_fixed_reply_and_closes_streak`, `test_transient_handover_failure_is_retried_on_the_next_failure` |
| R9 | `test_failures_below_threshold_do_not_hand_over`, `test_extra_failures_after_notified_do_not_derive_again`, `test_transient_handover_failure_is_retried_on_the_next_failure` |
| R10 | `test_no_advisors_sends_fixed_reply_and_closes_streak` |
| R11 | `test_transient_handover_failure_is_retried_on_the_next_failure`, `test_pending_retry_uses_the_next_eligible_outcome_even_if_not_counted`, `test_streak_survives_a_restart_and_retry_is_persisted` |
| R14 | `test_retry_reuses_the_active_case` |
| R12 | suite completa: `test_decisions.py`, `test_messages.py`, `test_case_reply.py`, `test_security.py`, `test_no_inventar.py`, `test_client_forward.py` y el resto de la batería, sin eliminar pruebas |

Verificación: ./init.sh pasó con 2088 passed, 1 skipped. El código está listo para revisión de Claude.

## Cierre
- `./init.sh`: 2088 passed, 1 skipped.
- Claude code reviewer: APPROVED (`progress/review_traspaso_automatico_fallos.md`).
- Feature #32 cerrada como done.
- Seguimientos no bloqueantes del reviewer: purgar outcomes/streaks con retención de contacto; retry tras excepciones inesperadas en enlace de caso; coordinación distribuida si se despliega con varios workers/instancias.
