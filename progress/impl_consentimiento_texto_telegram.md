# Implementación — feature #46 `consentimiento_texto_telegram`

## Contexto para el writer (observaciones no bloqueantes del spec review)

Fuente: `progress/specreview_consentimiento_texto_telegram.md` (APPROVED).

1. R23 y R30 tienen dos modales; cubre ambos modales en el test de cada uno.
2. R8 quita los sufijos `(privacy.accept)`/`(privacy.reject)` del texto del
   aviso de WhatsApp (`domain.py` ~2248-2249). El `OptionsBlock` de WhatsApp
   NO cambia (R28). Es el único cambio visible en WhatsApp: déjalo anotado aquí.
3. `normalize_privacy_text` hace trim, mayúsculas/minúsculas y junta espacios
   internos repetidos; documéntalo en `docs/proyecto.md` (T23).
4. No relajar #35: ningún dato personal persiste antes del consentimiento; la
   gate sigue antes de `get_or_create_contact` (R24).

## Registro

Implementado T1–T24. Cambios principales:

- `orchestrator/config.py`: frases efectivas de aceptación/rechazo con defaults
  `ACEPTO` / `NO ACEPTO`, instrucción configurable y validaciones R3/R4.
- `orchestrator/privacy.py`: `TEXT_CONSENT_CHANNELS`, `matches_consent_phrase`,
  `text_consent_instruction` y `ConsentChallengeStore.consume_text` atómico.
- `orchestrator/domain.py`: aviso de Telegram solo con `TextBlock` y desafío
  siempre registrado; aceptación/rechazo por texto con evidencia `text`;
  botones Telegram antiguos ignorados y reenviados como aviso de texto.
- `orchestrator/adapters/repository.py`: consentimiento vigente con evidencia
  `button` o `text` (memoria y SQL Postgres).
- `orchestrator/main.py`: las frases de texto de Telegram se procesan dentro de
  la petición HTTP (paridad 500 de #35).
- `telegram_gateway`: `MESSAGE_GROUPING_REJECT_PHRASE` y frase de rechazo
  inmediata; test de `reply_markup=None` con solo `TextBlock`.
- `.env.example`, `render.yaml` y `docs/proyecto.md` actualizados.
- Tests de botones de `test_conversation_states.py`, `test_consent_before_data.py`,
  `test_privacy.py` y `test_identity_link.py` movidos a WhatsApp o a la
  aceptación por texto de Telegram, sin eliminar aserciones.

Único cambio visible en WhatsApp (observación 2): el texto del aviso ya no
incluye `(privacy.accept)`/`(privacy.reject)`; el `OptionsBlock` con etiquetas,
ids y pruebas sigue igual (R28).

## Trazabilidad

- R1 → `test_text_consent_telegram.py::test_accept_phrase_defaults_to_acepto`
- R2 → `test_text_consent_telegram.py::test_reject_phrase_defaults_to_no_acepto`
- R3 → `test_text_consent_telegram.py::test_equal_phrases_fail_settings`
- R4 → `test_text_consent_telegram.py::test_instruction_without_placeholders_fails_settings`
- R5 → `test_text_consent_telegram.py::test_phrase_match_is_exact_after_normalization`
- R6 → `test_text_consent_telegram.py::test_telegram_notice_has_no_options_block`
- R7 → `test_text_consent_telegram.py::test_telegram_notice_text_is_panel_notice_plus_instruction`
- R8 → `test_text_consent_telegram.py::test_notice_text_never_contains_button_ids`
- R9 → `test_text_consent_telegram.py::test_telegram_notice_registers_challenge_with_version_hash_chat`
- R9 → `test_text_consent_telegram.py::test_telegram_notice_registers_challenge_without_send_channel_blocks`
- R10 → `test_text_consent_telegram.py::test_exact_accept_after_notice_records_text_evidence`
- R10 → `test_text_consent_telegram.py::test_legacy_route_accept_uses_update_id_as_external_message_id`
- R11 → `test_text_consent_telegram.py::test_consume_text_requires_same_version_hash_and_chat`
- R11 → `test_text_consent_telegram.py::test_consume_text_consumes_only_once`
- R11 → `test_text_consent_telegram.py::test_second_accept_phrase_does_not_record_twice`
- R12 → `test_text_consent_telegram.py::test_text_accept_continues_to_awaiting_login_with_link`
- R13 → `test_text_consent_telegram.py::test_text_evidence_counts_as_current_consent`
- R13 → `test_text_consent_telegram.py::test_postgres_consent_query_accepts_button_and_text`
- R13 → `test_conversation_states.py::test_legacy_text_acceptance_does_not_grant_the_flow`
- R14 → `test_text_consent_telegram.py::test_accept_phrase_before_notice_shows_notice_without_decision`
- R14 → `test_text_consent_telegram.py::test_reject_phrase_before_notice_shows_notice_without_decision`
- R14 → `test_text_consent_telegram.py::test_accept_after_version_change_requires_new_notice`
- R14 → `test_text_consent_telegram.py::test_accept_from_other_chat_does_not_consume_challenge`
- R15 → `test_text_consent_telegram.py::test_accept_phrase_before_notice_shows_notice_without_decision`
- R15 → `test_text_consent_telegram.py::test_reject_phrase_before_notice_shows_notice_without_decision`
- R16 → `test_text_consent_telegram.py::test_text_accept_storage_failure_returns_500`
- R17 → `test_text_consent_telegram.py::test_redelivered_accept_message_is_duplicate`
- R18 → `test_text_consent_telegram.py::test_reject_phrase_after_notice_records_minimal_text_decision_and_replies`
- R19 → `test_text_consent_telegram.py::test_reject_phrase_leaves_only_privacy_consents_row`
- R20 → `test_text_consent_telegram.py::test_after_reject_accept_phrase_restarts_and_shows_notice`
- R21 → `test_text_consent_telegram.py::test_non_matching_text_resends_notice_with_instruction`
- R22 → `test_text_consent_telegram.py::test_non_matching_text_persists_nothing_and_skips_llm`
- R23 → `test_text_consent_telegram.py::test_affirmation_without_exact_phrase_does_not_use_button_reply`
- R24 → `test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`
- R24 → `test_consent_before_data.py::test_acceptance_after_any_route_only_adds_privacy_consent`
- R25 → `test_text_consent_telegram.py::test_telegram_button_with_valid_proof_records_nothing`
- R26 → `test_text_consent_telegram.py::test_telegram_button_returns_202_and_resends_text_notice`
- R27 → `test_text_consent_telegram.py::test_telegram_button_after_consent_is_ignored`
- R28 → `test_text_consent_telegram.py::test_whatsapp_notice_keeps_signed_options_block`
- R29 → `test_text_consent_telegram.py::test_whatsapp_button_accept_records_button_evidence`
- R30 → `test_text_consent_telegram.py::test_whatsapp_accept_phrase_does_not_grant_consent`
- R31 → `test_grouping.py::test_reject_phrase_is_delivered_immediately`
- R31 → `test_grouping.py::test_empty_reject_phrase_does_not_change_grouping`
- R32 → `test_adapters.py::test_text_only_blocks_send_without_reply_markup`

## Tasks y verificación

- T1–T24 completadas en código, tests y docs. T24 incluye este informe; la
  ejecución de `./init.sh` la realiza Claude al cerrar la sesión y añade aquí
  el resultado. No se modificó `feature_list.json` ni se marcó la feature
  `done`.

## init.sh — intento 2 (correcciones del intento 1)

Los tres fallos del intento 1 corregidos sin relajar #35 ni cambiar WhatsApp:

1. `test_text_consent_telegram.py::test_reject_phrase_after_notice_records_minimal_text_decision_and_replies`:
   el rechazo se entrega por `_notify_channel`; con un chat numérico de Telegram
   eso usa la vía legacy `gateway.send` (`.sent`), no `send_channel_blocks`.
   El test comprueba ahora `gateway.sent[-1] == (100, rejected_reply)` y que el
   aviso solo se envió una vez (no se reenvía tras rechazar). Dominio sin cambios.
2. `test_webhook.py::test_webhook_callback_reaches_orchestrator_and_persists_the_decision`:
   adaptado a #46. El callback antiguo responde 200 y no registra nada (R25-R27);
   después una frase `ACEPTO` por el webhook persiste la evidencia `text` (R10) y
   deja el contacto en `AWAITING_LOGIN`.
3. `test_webhook.py::test_webhook_callback_from_another_chat_does_not_consume_the_challenge`:
   un callback de otro chat no registra decisión y deja desafío; el aviso se
   vuelve a presentar en el chat correcto (R14/R15) y la frase `ACEPTO` de ese
   chat consume el desafío y registra la evidencia `text`.

`_build_consent_flow` ya no extrae prueba de un `OptionsBlock` (el aviso de
Telegram solo lleva `TextBlock`) y su cliente de orquestador enruta
`MessageRequest` por `process_message` y `NormalizedMessage` por
`process_channel_message`, como el `/messages` real.

## init.sh — intento 1 (FAIL: 3 failed, 3095 passed, 1 skipped)

Corrige estos fallos concretos sin relajar #35 ni cambiar WhatsApp:

1. `services/orchestrator/tests/test_text_consent_telegram.py::test_reject_phrase_after_notice_records_minimal_text_decision_and_replies`
   (línea 484). La fila `privacy_consents` rejected/text se guarda bien, pero el
   último envío (`env.gateway.channel_sent[-1]`) es otra vez el aviso con la
   instrucción («Para aceptar, escribe exactamente: …»), no
   `settings.conversation_rejected_reply`. R18 exige que, tras registrar el
   rechazo, la respuesta sea el texto de rechazo y que no se reenvíe el aviso
   después. Revisa el flujo de dominio (o el test, si envía el aviso después).
2. `services/telegram_gateway/tests/test_webhook.py::test_webhook_callback_reaches_orchestrator_and_persists_the_decision`
3. `services/telegram_gateway/tests/test_webhook.py::test_webhook_callback_from_another_chat_does_not_consume_the_challenge`
   Ambos fallan en `_build_consent_flow` (test_webhook.py:363):
   `options.option_ids` → `AttributeError: 'TextBlock' object has no attribute 'option_ids'`,
   porque el aviso de Telegram ya no trae `OptionsBlock` (R6). Adapta estos
   tests de integración al spec: la aceptación de Telegram se hace con la
   frase de texto tras el aviso (evidencia `text`, R10/R11) y el callback
   antiguo de otro chat o de botón no registra nada (R14/R25/R26). Conserva
   la intención de cada test (decisión persistida de extremo a extremo; otro
   chat no consume el desafío) sin eliminar aserciones de seguridad.

## init.sh — tras corrección 1 (OK)

- `bash ./init.sh` → **Entorno listo**: 3098 passed, 1 skipped, 0 failed (4m09s).
- R18: el test sigue exigiendo que la última respuesta sea
  `conversation_rejected_reply` y ahora además que el aviso se envió solo una
  vez (aserción reforzada, no relajada).
- Trazabilidad `R<n> → test` presente para R1–R32 (sección «Trazabilidad»).
- Nota de proceso: el envoltorio de la corrección se detuvo por timeout de la
  herramienta de Claude, pero el proceso OpenCode siguió vivo y terminó solo;
  no se lanzó una segunda copia.
- `feature_list.json`: OpenCode no lo modificó; #46 sigue `in_progress`
  (pendiente de revisión de código).
