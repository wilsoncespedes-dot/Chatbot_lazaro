# Implementación #90 — Canal Gmail

## Verificación

- `./init.sh`: exit code 0; 4.931 passed, 1 skipped, 2 warnings preexistentes de Starlette/Pydantic.
- Revisión final: sin imports entre servicios; OAuth y secretos se cifran con
  `SecretCipher`; rutas protegidas por middleware `X-Service-Token`; cursores
  actualizados solo al terminar; texto plano, sin descargas ni HTML; `git diff
  --check` limpio.
- La cuenta Gmail real no se conectó: requiere OAuth del dueño en Google Cloud
  y scheduler externo según `docs/gmail.md`.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_admin_canales.py::test_gmail_channel_form_carries_mailbox_address_and_oauth_credentials`; `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R2 → `services/orchestrator/tests/test_admin_canales.py::test_gmail_channel_form_rejects_invalid_mailbox_address`; `services/telegram_gateway/tests/test_gmail_api.py::test_gmail_factory_rejects_invalid_mailbox_config`
- R3 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R4 → `services/telegram_gateway/tests/test_gmail_api.py::test_added_message_ids_are_unique_and_ordered`; `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R5 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R6 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_keeps_cursor_when_orchestrator_fails`
- R7 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R8 → `services/telegram_gateway/tests/test_gmail_api.py::test_send_reply_preserves_thread_and_reply_headers`
- R9-R10 → `services/telegram_gateway/tests/test_gmail_api.py::test_send_reply_preserves_thread_and_reply_headers`; `services/telegram_gateway/tests/test_gmail_api.py::test_plain_text_body_ignores_html_and_attachments`
- R11 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_requires_service_token`
- R12 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_initializes_then_only_forwards_inbox_external_text`; `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_sync_rejects_inactive_channel`
- R13-R14 → `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_expired_history_keeps_cursor_until_explicit_reset`; `services/telegram_gateway/tests/test_gmail_sync.py::test_gmail_message_404_does_not_masquerade_as_expired_history`
- R15 → `services/telegram_gateway/tests/test_gmail_api.py::test_gmail_send_error_logs_no_reply_content_or_oauth_values`
- R16-R17 → `scripts/tests/test_sincronizar_gmail.py::test_scheduler_syncs_only_active_gmail_channels`; `scripts/tests/test_sincronizar_gmail.py::test_scheduler_fails_when_one_gmail_channel_fails`
- R18 → `contracts/tests/test_gmail_doc.py::test_gmail_docs_cover_routes_scopes_and_privacy`
- Panel request → `services/orchestrator/tests/test_admin_canales.py::test_gmail_channel_form_carries_mailbox_address_and_oauth_credentials`
