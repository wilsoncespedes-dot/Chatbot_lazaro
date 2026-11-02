# Implementación — agrupacion_mensajes (#30)

Implementado en `telegram_gateway`; sin cambios de rutas, contratos ni otros servicios.

## Archivos

- `services/telegram_gateway/telegram_gateway/config.py`: campos `message_grouping_*` y validador R2.
- `services/telegram_gateway/telegram_gateway/domain.py`: `BufferedMessage`, `ClaimedGroup`,
  `is_immediate`, `compute_due`, `must_flush_before`, `build_group_request`; `Adapters.buffer`.
- `services/telegram_gateway/telegram_gateway/adapters/message_buffer.py` (nuevo):
  `MessageBuffer`, `FakeMessageBuffer`, `RedisMessageBuffer` con scripts Lua.
- `services/telegram_gateway/telegram_gateway/grouping.py` (nuevo):
  `enqueue_text`, `flush_chat`, `flush_due`, `GroupingWorker`.
- `services/telegram_gateway/telegram_gateway/main.py`: rama de texto delegada y lifespan.
- `.env.example`, `render.yaml`, `docs/despliegue.md`: configuración y herencia de la frase.
- Tests nuevos: `tests/test_grouping.py`, `tests/test_message_buffer.py`.

## Trazabilidad

- R1 → `tests/test_grouping.py::test_grouping_settings_defaults`
- R2 → `tests/test_grouping.py::test_invalid_grouping_settings_fail_with_variable_name`
- R3 → `tests/test_grouping.py::test_env_example_lists_grouping_variables_with_defaults`,
  `tests/test_grouping.py::test_render_references_accept_phrase_from_orchestrator`
- R4 → `tests/test_grouping.py::test_two_texts_within_window_are_grouped_when_due`
- R5 → `tests/test_grouping.py::test_two_texts_within_window_are_grouped_when_due`,
  `tests/test_grouping.py::test_gap_larger_than_window_produces_separate_groups`,
  `tests/test_grouping.py::test_long_burst_is_cut_at_max_wait`
- R6 → `tests/test_grouping.py::test_group_is_ordered_by_update_id_and_uses_expected_fields`,
  `tests/test_message_buffer.py::test_redis_claim_due_parses_lua_payload_for_a_due_buffer`
- R7 → `tests/test_grouping.py::test_group_is_ordered_by_update_id_and_uses_expected_fields`
- R8 → `tests/test_grouping.py::test_chats_are_isolated`
- R9 → `tests/test_grouping.py::test_other_user_forces_previous_buffer_flush`,
  `tests/test_grouping.py::test_max_messages_forces_previous_buffer_flush`,
  `tests/test_grouping.py::test_combined_length_over_contract_limit_forces_flush`
- R10 → `tests/test_grouping.py::test_single_message_longer_than_contract_limit_is_not_buffered`
- R11 → `tests/test_grouping.py::test_duplicate_update_is_not_buffered`
- R12 → `tests/test_grouping.py::test_duplicate_append_keeps_a_single_copy_when_dedup_is_down`,
  `tests/test_message_buffer.py::test_append_is_idempotent_for_same_update_id`
- R13 → `tests/test_grouping.py::test_commands_flush_buffer_then_are_sent_individually`,
  `tests/test_grouping.py::test_accept_phrase_is_immediate_after_normalization`
- R14 → `tests/test_grouping.py::test_commands_flush_buffer_then_are_sent_individually`,
  `tests/test_grouping.py::test_accept_phrase_is_immediate_after_normalization`
- R15 → `tests/test_grouping.py::test_non_text_update_keeps_buffer_untouched`
- R16 → `tests/test_grouping.py::test_grouping_disabled_forwards_directly`,
  `tests/test_grouping.py::test_without_buffer_adapter_forwards_directly`,
  `tests/test_grouping.py::test_app_does_not_start_worker_when_grouping_is_disabled`
- R17 → `tests/test_grouping.py::test_redis_failure_falls_back_to_individual_forward`
- R18 → `tests/test_grouping.py::test_eight_threads_claim_the_same_group_only_once`,
  `tests/test_message_buffer.py::test_ack_with_stale_claim_id_does_not_remove_group`,
  `tests/test_message_buffer.py::test_redis_claim_due_parses_lua_payload_for_a_due_buffer`,
  `tests/test_message_buffer.py::test_redis_ack_uses_claim_id_and_keys`,
  `tests/test_message_buffer.py::test_redis_message_buffer_against_real_redis` (opcional)
- R19 → `tests/test_grouping.py::test_group_in_flight_blocks_other_claims_of_same_chat`,
  `tests/test_message_buffer.py::test_claim_moves_buffer_and_blocks_a_second_claim`
- R20 → `tests/test_grouping.py::test_immediate_message_is_sent_alone_when_group_is_inflight`,
  `tests/test_grouping.py::test_limit_while_inflight_sends_new_message_individually`
- R21 → `tests/test_grouping.py::test_orchestrator_failure_releases_group_and_retries_same_messages`,
  `tests/test_message_buffer.py::test_ack_removes_group_and_release_allows_retry`,
  `tests/test_message_buffer.py::test_redis_release_keeps_claim_and_reschedules_lease`
- R22 → `tests/test_grouping.py::test_group_is_discarded_after_max_attempts`,
  `tests/test_grouping.py::test_group_that_fails_contract_validation_is_discarded`
- R23 → `tests/test_grouping.py::test_expired_lease_reclaims_until_max_attempts_then_discards`,
  `tests/test_message_buffer.py::test_lease_expiry_reclaims_with_incremented_attempts`,
  `tests/test_message_buffer.py::test_redis_claim_due_parses_expired_lease_with_incremented_attempts`
- R24 → `tests/test_grouping.py::test_buffer_and_group_expire_after_ttl`,
  `tests/test_message_buffer.py::test_ttl_expires_buffer_and_inflight_group`,
  `tests/test_message_buffer.py::test_redis_append_passes_ttl_and_keys`,
  `tests/test_message_buffer.py::test_redis_claim_chat_passes_ttl`
- R25 → `tests/test_grouping.py::test_worker_logs_iteration_errors_and_keeps_running`
- R26 → `tests/test_grouping.py::test_app_starts_and_stops_grouping_worker`,
  `tests/test_grouping.py::test_app_does_not_start_worker_when_grouping_is_disabled`
- R27 → `tests/test_grouping.py::test_app_starts_and_stops_grouping_worker`
- R28 → `tests/test_grouping.py::test_error_logs_do_not_include_texts_or_accept_phrase`
  (y aserciones de logs sin texto en T8–T16)
- R29 → `tests/test_message_buffer.py::test_fake_buffer_satisfies_protocol`,
  `tests/test_message_buffer.py::test_fake_buffer_fail_raises_connection_error`,
  `tests/test_grouping.py::test_worker_does_not_start_real_threads_without_buffer`

## Notas

- T1–T18 completas. T19 queda pendiente solo de que Claude ejecute `./init.sh` (el
  implementer no ejecuta shell); la trazabilidad ya está documentada aquí.
- T18 es el test opcional contra Redis real; se ejecuta solo si existe
  `REDIS_TEST_URL` y está marcado `integration`.
- No se modificó `feature_list.json`, `progress/current.md` ni el harness.

## Corrección aplicada tras ./init.sh
La suite falló en `test_fake_buffer_fail_raises_connection_error`: `FakeMessageBuffer.pending()`
no llamaba a `_check()`. Se añadió el guard en `pending()` (mismo patrón que el resto de
operaciones), de modo que `fail=True` lanza `ConnectionError` también ahí. Sin otros cambios
de alcance. Trazabilidad afectada: R29 →
`tests/test_message_buffer.py::test_fake_buffer_fail_raises_connection_error`.

## Corrección requerida por code review (aplicada)
Claude rechazó la feature: `RedisMessageBuffer.claim_due` interpretaba mal el JSON devuelto por
`_CLAIM_DUE_LUA` (lista `[chat, claim_id, attempts, messages_json]`), y `_parse_group` volvía a
hacer `json.loads` sobre la lista, lanzando `TypeError` y perdiendo todo texto normal.

- `_parse_group` ahora recibe las cuatro piezas ya deserializadas
  (`chat_id`, `claim_id`, `attempts`, `messages_json`) y solo deserializa la lista de mensajes.
- `claim_chat` desempaqueta el payload de tres elementos `[claim_id, attempts, messages_json]` y
  reutiliza el mismo parser; `claim_due` desempaqueta `[chat, claim_id, attempts, messages_json]`
  y convierte `chat` a `int`, sin volver a pasar la lista por `json.loads`.
- Tests nuevos no-integration con stub de cliente y la forma real de los Lua:
  - `test_redis_claim_chat_parses_lua_payload` (payload de 3 elementos)
  - `test_redis_claim_due_parses_lua_payload_for_a_due_buffer` (R6, R18)
  - `test_redis_claim_due_parses_expired_lease_with_incremented_attempts` (R23)
  - `test_redis_claim_due_returns_nothing_for_empty_lua_result`
  - `test_redis_ack_uses_claim_id_and_keys`
  - `test_redis_release_keeps_claim_and_reschedules_lease`

Trazabilidad añadida: R6, R18, R21 y R23 quedan verificados también sobre el adaptador Redis
de producción (sin Redis real). No se tocaron los no-bloqueantes del informe (batching de
`ZRANGEBYSCORE` ni caché de `Script`) ni se amplió el alcance.

## Estado de T19
`./init.sh` lo ejecuta Claude tras esta sesión (el implementer no usa shell); la trazabilidad
R1–R29 actualizada está en este archivo.

## Verificación y revisión final
- `./init.sh`: 2041 passed, 1 skipped; entorno listo.
- Claude code reviewer: APPROVED en segunda pasada (`progress/review_agrupacion_mensajes.md`).
- Feature #30 cerrada como done.

## Auditoría general (2026-11-02)
- Redis real local: integración T18 pasó y `./init.sh` ejecutado con `REDIS_TEST_URL`: 2093 passed, 0 skipped.
- Se registró la marca pytest `integration` para eliminar el warning de marca desconocida.
