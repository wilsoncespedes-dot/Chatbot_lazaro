# Review — feature 90

**Veredicto:** APPROVED

La revisión comprobó las rutas de sincronización/reset, el cursor incremental,
la respuesta MIME en el hilo, el panel de canales, el cliente OAuth y el script
programado. El 404 de Gmail History se distingue ahora del 404 al leer un
mensaje; ambos fallos conservan el cursor. La última ejecución de `./init.sh`
terminó con **4931 passed, 1 skipped**.

## Trazabilidad requirements ↔ tests

- R1: [x] `test_gmail_channel_form_carries_mailbox_address_and_oauth_credentials`; `test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R2: [x] `test_gmail_factory_rejects_invalid_mailbox_config`; `test_gmail_channel_form_rejects_invalid_mailbox_address`
- R3: [x] `test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R4: [x] `test_added_message_ids_are_unique_and_ordered`; `test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R5: [x] `test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R6: [x] `test_gmail_sync_keeps_cursor_when_orchestrator_fails`
- R7: [x] `test_gmail_sync_initializes_then_only_forwards_inbox_external_text`
- R8: [x] `test_send_reply_preserves_thread_and_reply_headers`
- R9: [x] `test_send_reply_preserves_thread_and_reply_headers`
- R10: [x] `test_plain_text_body_ignores_html_and_attachments`; `test_send_reply_preserves_thread_and_reply_headers`
- R11: [x] `test_gmail_sync_requires_service_token`
- R12: [x] `test_gmail_sync_rejects_inactive_channel`
- R13: [x] `test_gmail_expired_history_keeps_cursor_until_explicit_reset`; `test_gmail_message_404_does_not_masquerade_as_expired_history`
- R14: [x] `test_gmail_expired_history_keeps_cursor_until_explicit_reset`
- R15: [x] `test_gmail_send_error_logs_no_reply_content_or_oauth_values`
- R16: [x] `test_scheduler_syncs_only_active_gmail_channels`
- R17: [x] `test_scheduler_fails_when_one_gmail_channel_fails`
- R18: [x] `test_gmail_docs_cover_routes_scopes_and_privacy`

## Tasks completas

- T1–T9: [x] Todas aparecen marcadas `[x]` en `specs/canal_gmail/tasks.md`.

## Checkpoints

- C1: [x] Archivos base y docs existen; `./init.sh` terminó con código 0.
- C2: [x] La única feature activa es #90; sus pruebas pasan y `progress/current.md` describe la sesión activa.
- C3: [x] El adaptador permanece en `telegram_gateway`, las credenciales usan el cifrado existente, los contratos se documentan y no se añade dependencia.
- C4: [x] Pruebas con transportes falsos; suite completa verde.
- C5: [x] Los archivos locales sin seguimiento visibles (`docs/manuales_demo/` y `sonar-project.properties`) son artefactos preexistentes y no temporales. La sesión activa está documentada en `progress/current.md`; el traslado a historial corresponde al cierre posterior a este veredicto.
- C6: [x] Spec SDD completo; requisitos trazados a pruebas y tasks completas.
