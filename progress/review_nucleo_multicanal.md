# Review — feature #36

**Veredicto:** CHANGES_REQUESTED

## Trazabilidad requirements ↔ tests

- R1: [x] `contracts/tests/test_channels.py::test_normalized_message_accepts_both_channels`; `services/telegram_gateway/tests/test_multicanal.py::test_telegram_update_is_normalized_to_common_message`; `services/orchestrator/tests/test_multicanal_flow.py::test_canonical_whatsapp_message_is_processed_and_answered`
- R2: [x] `contracts/tests/test_channels.py` valida bloques y límites; `services/telegram_gateway/tests/test_multicanal.py::test_telegram_adapter_renders_abstract_blocks`
- R3: [x] `services/telegram_gateway/tests/test_multicanal.py::test_telegram_adapter_send_keeps_legacy_text_delivery`; suite previa `test_webhook.py` y `test_send.py`
- R4: [x] `services/telegram_gateway/tests/test_multicanal.py::test_fake_whatsapp_normalizes_text_and_button_messages`, `::test_fake_whatsapp_sends_text_inside_window`, `::test_canonical_send_uses_injected_whatsapp_adapter`
- R5: [x] `services/orchestrator/tests/test_multicanal_dedup.py::test_same_channel_same_external_id_is_duplicate`, `::test_postgres_honors_legacy_processed_updates`; `services/telegram_gateway/tests/test_multicanal.py::test_redis_dedup_preserves_legacy_update_key`
- R6: [x] `services/orchestrator/tests/test_multicanal_dedup.py::test_same_external_id_in_two_channels_is_not_duplicate`, `::test_messages_processes_same_id_once_per_channel`
- R7: [x] `services/telegram_gateway/tests/test_multicanal.py::test_core_checks_capabilities_before_send`
- R8: [x] `services/telegram_gateway/tests/test_multicanal.py::test_canonical_send_fails_closed_outside_window`
- R9: [x] `services/telegram_gateway/tests/test_multicanal.py::test_canonical_send_allows_approved_template`
- R10: [x] `services/telegram_gateway/tests/test_multicanal.py::test_both_adapters_preserve_the_same_abstract_response`; `services/orchestrator/tests/test_multicanal_flow.py::test_same_canonical_message_produces_the_same_answer_in_both_channels`
- R11: [x] `services/telegram_gateway/tests/test_multicanal.py::test_no_network_is_used`
- R12: [x] `services/telegram_gateway/tests/test_multicanal.py::test_send_failure_is_simulable_and_status_is_common_vocabulary`

## Tasks completas

- T1: [x]
- T2: [x]
- T3: [x]
- T4: [x]
- T5: [x]
- T6: [x]
- T7: [x]
- T8: [x] `./init.sh`: 2223 passed, 1 skipped, 1 warning.

## Checkpoints

- C1: [x] El arnés y `./init.sh` terminan correctamente.
- C2: [x] Solo #36 está `in_progress`; `progress/current.md` describe el trabajo activo.
- C3: [ ] La identidad de WhatsApp se guarda y consulta como `telegram_user_id`, sin namespace de canal.
- C4: [x] Suite completa verde; R1–R12 tienen tests.
- C5: [ ] La sesión sigue abierta y los cambios aún no están cerrados en historial.
- C6: [x] Spec, tasks y trazabilidad requirement-test están presentes.

## Cambios requeridos

1. **[P1] Aislar la identidad y el consentimiento por canal.** En `services/orchestrator/orchestrator/main.py:112-130`, `_legacy_from_normalized` convierte `external_user_id` de WhatsApp a entero y lo asigna a `MessageRequest.telegram_user_id`. El mismo valor se usa para `contacts.telegram_user_id` (`services/orchestrator/orchestrator/adapters/repository.py:693,850`) y para buscar/guardar consentimiento (`services/orchestrator/orchestrator/domain.py:826-847`, `services/orchestrator/orchestrator/adapters/repository.py:1273-1293`). Así se pierde el namespace del canal: una coincidencia entre un ID de Telegram y un ID de WhatsApp puede fusionar contactos o reutilizar consentimiento de otra identidad. También se rechazan IDs canónicos no numéricos aunque `NormalizedMessage` los define como texto (`services/orchestrator/orchestrator/main.py:121-122`). No almacenar ni consultar la identidad de WhatsApp como `telegram_user_id`. Criterio: el procesamiento debe usar identidad externa con clave `(channel, external_user_id)` y consentimiento aislado por canal, con pruebas donde Telegram y WhatsApp usan el mismo ID y no comparten contacto, historial ni consentimiento. Como opción temporal segura hasta que exista esa identidad aislada, el orquestador debe rechazar explícitamente WhatsApp antes de responder `accepted`; nunca aceptar y descartar, ni convertirlo a ID de Telegram.

Los hallazgos P1 anteriores de identidad cruzada (WhatsApp como `telegram_user_id`), deduplicación Redis/PostgreSQL legacy, descarte silencioso de mensajes WhatsApp y texto Telegram de 4097 caracteres se atendieron en cambios posteriores. La suite reportada pasó con `2239 passed, 1 skipped`, aunque la revisión final detectó nuevas brechas R21/P2:

## Revisión final tras T9–T14 — CHANGES_REQUESTED

1. **[P1] Deduplicación persistente antes del consentimiento.** `services/orchestrator/orchestrator/main.py` fijaba `consent_ready=True` para `privacy_configured=False` y para el request legacy; además, un payload canónico Telegram numérico se traduce al modelo legacy. Eso permitía llamar `mark_message_if_new` y escribir `processed_messages` antes de pasar la compuerta. Ajustar la ruta: requests canónicos/canales nuevos sin consentimiento o sin aviso configurado no escriben `processed_messages`; el endpoint Telegram legacy conserva únicamente la excepción de #35 `processed_updates(update_id)`. Cubrir canónico Telegram numérico, legacy Telegram no consentido y aviso desconfigurado.
2. **[P2] Relaciones históricas del backfill sin cobertura.** `services/orchestrator/tests/test_repository_schema.py` comprobaba IDs y datos del contacto, pero el fixture legacy no contenía mensajes ni `case_links`. Agregar esas relaciones y demostrar que sobreviven intactas a más de una ejecución del backfill.

El spec ajustó R21 y separó R22 (excepción Telegram legacy) de R23 (no persistir deduplicación nueva antes del consentimiento); un reviewer de spec aprobó esa corrección EARS. La implementación debe añadir `R22/R23 → tests` al informe y ejecutar `./init.sh` después de estos cambios.

## Resultado de revisión dirigida final

**APPROVED.** Se confirmaron las correcciones P1/P2: `processed_updates` conserva únicamente el `update_id` para el endpoint Telegram legacy; requests canónicos y canales nuevos no persisten `processed_messages` antes del consentimiento ni cuando la privacidad está desconfigurada; el backfill repetido conserva IDs, mensajes, relaciones de casos y evidencia histórica. También se verificó identidad/consentimiento channel-scoped y que el test de independencia mantiene ambos sentidos. `./init.sh`: 2243 passed, 1 skipped, 1 warning Starlette/httpx.
