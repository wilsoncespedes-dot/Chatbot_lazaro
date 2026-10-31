# Review — feature telegram_gateway

**Veredicto:** APPROVED

`./init.sh` termina verde (416 tests pasan).

## Trazabilidad requirements ↔ tests
- R1: [x] `test_webhook_without_secret_returns_401`, `test_webhook_wrong_secret_returns_401`
- R2: [x] `test_webhook_empty_configured_secret_returns_401`
- R3: [x] `test_webhook_does_not_require_service_token`
- R4: [x] `test_new_text_update_is_forwarded_with_contract_fields`
- R5: [x] `test_new_text_update_is_forwarded_with_contract_fields` (reloj fijo y zona horaria)
- R6: [x] `test_http_orchestrator_sends_service_token_header`
- R7: [x] `test_new_text_update_is_forwarded_with_contract_fields`
- R8: [x] `test_duplicate_update_is_not_forwarded_and_returns_200`, `test_duplicate_non_text_update_sends_nothing_twice`
- R9: [x] `test_dedup_key_stored_with_ttl`, `test_redis_adapter_uses_set_nx_ex`
- R10: [x] `test_dedup_store_failure_still_forwards`
- R11: [x] `test_orchestrator_down_returns_200_and_logs_error`
- R12: [x] `test_orchestrator_down_returns_200_and_logs_error`
- R13: [x] `test_non_text_update_sends_fixed_reply_and_not_forwarded`, `test_empty_or_blank_text_treated_as_non_text`
- R14: [x] los mismos tests que R13
- R15: [x] `test_non_text_reply_failure_returns_200`
- R16: [x] `test_update_without_message_is_ignored`
- R17: [x] `test_webhook_invalid_body_returns_422`
- R18: [x] `test_send_ok_returns_sent_true`
- R19: [x] `test_send_telegram_failure_returns_502`
- R20: [x] `test_send_without_token_returns_401`
- R21: [x] `test_send_invalid_body_returns_422`
- R22: [x] `test_settings_defaults`, `test_settings_reads_env`
- R23: [x] Los tests usan fakes en `conftest.py`. El `httpx.post` de los clientes HTTP y el cliente de Redis se simulan con monkeypatch. No hay red ni Redis real.
- R24: [x] `test_bot_token_not_in_logs_or_errors`, `test_http_telegram_error_hides_bot_token`
- R25: [x] `test_env_example_lists_all_variables`. `.env.example` contiene las 7 variables.

## Tasks completas
- T1 a T22 (incluida T20b): [x] todas marcadas `[x]` en `specs/telegram_gateway/tasks.md`.

## Checkpoints
- C1: [x]
- C2: [x] Solo `telegram_gateway` está en curso. Su estado pasará a `done` por el flujo del leader.
- C3: [x] No se importa código de otros servicios. `requirements.txt` acota las versiones de `httpx` y `redis`, y ambas figuran en `design.md` con licencia (BSD-3 y MIT). No se encontraron `print()` ni TODOs. El token del bot solo se usa para construir la URL. `.env.example` está al día.
- C4: [x] Los tests usan fakes. Las pruebas de seguridad aplicables existen: secreto del webhook, token de servicio y token del bot fuera de logs.
- C5: [x] Aplicable al cierre de sesión (`progress/history.md`), a cargo del leader.
- C6: [x] El spec tiene los 3 archivos. `design.md` incluye dependencias, alternativas descartadas y «Supuestos a confirmar».

## Cambios requeridos
Ninguno.
