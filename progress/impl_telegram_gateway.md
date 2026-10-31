# Impl telegram_gateway

Estado: tasks T1..T22 completadas, `./init.sh` verde (416 tests). Pendiente de reviewer; no marcado `done`.

Notas: se instalaron `httpx` y `redis` en `.venv` (en requirements.txt y design). Se actualizó
`test_requirements_txt_matches_design` del esqueleto (ahora 6 dependencias). Tests de `tests/` usan
solo fakes; `httpx.post` simulado con monkeypatch para los clientes HTTP; sin red ni Redis.
Las constantes de conftest se duplican en los tests (modo importlib impide importar conftest).

## Trazabilidad R -> test (services/telegram_gateway/tests/)
- R1: test_webhook::test_webhook_without_secret_returns_401, test_webhook_wrong_secret_returns_401
- R2: test_webhook_empty_configured_secret_returns_401
- R3: test_webhook_does_not_require_service_token
- R4: test_new_text_update_is_forwarded_with_contract_fields, test_empty_or_blank_text_treated_as_non_text
- R5: test_new_text_update_is_forwarded_with_contract_fields (reloj fijo, tz)
- R6: test_http_orchestrator_sends_service_token_header
- R7: test_new_text_update_is_forwarded_with_contract_fields
- R8: test_duplicate_update_is_not_forwarded_and_returns_200, test_duplicate_non_text_update_sends_nothing_twice
- R9: test_dedup_key_stored_with_ttl, test_redis_adapter_uses_set_nx_ex
- R10: test_dedup_store_failure_still_forwards
- R11, R12: test_orchestrator_down_returns_200_and_logs_error
- R13, R14: test_non_text_update_sends_fixed_reply_and_not_forwarded, test_empty_or_blank_text_treated_as_non_text
- R15: test_non_text_reply_failure_returns_200
- R16: test_update_without_message_is_ignored
- R17: test_webhook_invalid_body_returns_422
- R18-R21: test_send.py (ok, 502, 401, 422)
- R22: test_settings_defaults, test_settings_reads_env
- R23: todos los tests usan fakes / monkeypatch (conftest.py)
- R24: test_bot_token_not_in_logs_or_errors, test_http_telegram_error_hides_bot_token
- R25: test_env_example_lists_all_variables
