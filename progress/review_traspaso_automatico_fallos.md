# Review — feature 32 (traspaso_automatico_fallos)

**Veredicto:** APPROVED

`./init.sh`: 2088 passed, 1 skipped (resultado aportado por el leader; esta revisión no lo vuelve a ejecutar).
Tests en `services/orchestrator/tests/test_auto_handover.py` salvo que se indique otro archivo.

## Trazabilidad requirements ↔ tests
- R1: [x] `test_failures_below_threshold_do_not_hand_over`, `test_no_relevant_chunks_is_not_counted_when_outside_the_policy`, `test_invalid_answer_counts_when_enabled`
- R2: [x] `test_rag_and_llm_errors_do_not_count_or_break_the_streak`, `test_commands_privacy_and_user_request_are_not_counted`, `test_forwarded_assigned_conversation_is_not_counted`, `test_invalid_answer_is_not_counted_when_handover_is_disabled`
- R3: [x] `test_threshold_and_reasons_defaults`, `test_env_example_documents_auto_handover_defaults`, `test_invalid_answer_is_excluded_when_its_handover_is_disabled`
- R13: [x] `test_invalid_threshold_prevents_start`, `test_invalid_reasons_prevent_start_and_name_the_variable`
- R4: [x] `test_streak_is_isolated_by_contact`, `test_streak_survives_a_restart_and_retry_is_persisted`
- R5: [x] `test_repeated_update_id_does_not_increment_the_streak` (Fake) y `_MemoryConn` en `test_streak_survives_a_restart_and_retry_is_persisted` (Postgres, `ON CONFLICT DO NOTHING RETURNING`). Además `main.py:211` ya filtra duplicados con `mark_update_if_new`.
- R6: [x] `test_valid_answer_resets_the_streak`, `test_valid_answer_after_handover_opens_a_new_streak`
- R7: [x] `test_failures_below_threshold_do_not_hand_over` (una sola petición, con el motivo actual), `test_invalid_answer_counts_when_enabled`
- R8: [x] `test_extra_failures_after_notified_do_not_derive_again`, `test_no_advisors_sends_fixed_reply_and_closes_streak`, `test_transient_handover_failure_is_retried_on_the_next_failure` (4.º fallo sin nueva petición)
- R9: [x] `ACK` contado `== 1` en `test_failures_below_threshold_do_not_hand_over`, `test_extra_failures_after_notified_do_not_derive_again`, `test_transient_handover_failure_is_retried_on_the_next_failure`
- R10: [x] `test_no_advisors_sends_fixed_reply_and_closes_streak`
- R11: [x] `test_transient_handover_failure_is_retried_on_the_next_failure`, `test_pending_retry_uses_the_next_eligible_outcome_even_if_not_counted`, `test_streak_survives_a_restart_and_retry_is_persisted`
- R14: [x] `test_retry_reuses_the_active_case` (un único `case_links`, mismo `contact_id`)
- R12: [x] batería completa verde; los 5 tests previos modificados (`test_decisions.py:33`, `test_messages.py:104`, `test_no_inventar.py:162`, `test_security.py:29`, `test_case_reply.py:52`) solo fijan umbral 1 y endurecen/actualizan aserciones al ACK que exige R9; no se eliminó ninguna.

## Puntos pedidos por el leader
- **Atomicidad Postgres:** `record_rag_outcome` (`repository.py:829-896`) inserta el outcome, lee la racha y hace upsert en una única transacción bajo `self._lock`, con rollback ante excepción. Correcto para el despliegue actual (un proceso uvicorn, `Dockerfile:12`).
- **Dedup `update_id`:** PK `(contact_id, update_id)` + `ON CONFLICT DO NOTHING RETURNING`; Fake equivalente con `_rag_lock`.
- **Retries:** `finish_auto_handover(..., False)` → `retry`; el siguiente outcome RAG elegible pasa a `pending` y reintenta; `_handover` devuelve False solo ante `ServiceUnavailable` (el cliente HTTP envuelve todos los errores, `handover.py:74-76`).
- **Reset:** `rag_answer` reinicia a `0/open` dentro de la misma transacción; `user_request` llama a `reset_rag_streak` (`domain.py:906`, coherente con design.md).
- **Outcomes excluidos:** errores RAG/LLM salen por `_processing_error` antes de registrar; comandos, privacidad y reenvío al asesor retornan antes; `RAG_OUTCOMES` rechaza valores libres.
- **Avisos una vez:** ACK/NO_ADVISORS solo se envían cuando `record_rag_outcome` devuelve True, lo que ocurre solo en la transición a `pending`; `handed_over` bloquea hasta una respuesta válida.

## Tasks completas
- T1: [x]  T2: [x]  T3: [x]  T4: [x]  T5: [x]  T6: [x]

## Checkpoints
- C1: [x] archivos base y docs presentes; init.sh verde.
- C2: [x] una sola feature en `in_progress` (#32); `current.md` describe la sesión.
- C3: [x] sin imports entre servicios, sin cambios de contrato ni dependencias nuevas; variables nuevas en `.env.example`; SQL parametrizado (`test_postgres_rag_outcomes_use_parameterized_sql`); sin `print`/TODO/`eval`.
- C4: [x] tests con adaptadores falsos y conexiones simuladas; nada contra la BD real.
- C5: [x] sin archivos temporales sospechosos; la entrada de history para #32 se añade al cerrar la feature.
- C6: [x] specs completos, tasks `[x]`, R1–R14 cubiertos.

## Observaciones no bloqueantes (para una feature posterior)
1. `purge_personal_data` (`repository.py:1203`) no limpia `auto_handover_outcomes` ni `auto_handover_streaks`: cuando se purga un contacto quedan filas huérfanas con su `contact_id` (seudónimo, sin texto), y `auto_handover_outcomes` crece con una fila por consulta RAG para siempre. Conviene añadir la purga por `at` < corte y por contactos borrados.
2. Si `_handover` lanza una excepción que no sea `ServiceUnavailable` (p. ej. un fallo de BD en `link_case`) después de que `record_rag_outcome` pase a `pending`, la racha queda en `pending` y no reintenta hasta la próxima respuesta válida. Es un caso límite.
3. La exclusión mutua depende del lock del proceso. Con varios workers o instancias habría que usar `SELECT ... FOR UPDATE` o un upsert atómico con `RETURNING`.
