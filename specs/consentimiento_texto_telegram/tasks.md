# Tasks — #46 `consentimiento_texto_telegram`

Rutas de test abreviadas:
- `OT` = `services/orchestrator/tests/test_text_consent_telegram.py` (nuevo)
- `CS` = `services/orchestrator/tests/test_conversation_states.py`
- `CB` = `services/orchestrator/tests/test_consent_before_data.py`
- `GW` = `services/telegram_gateway/tests/test_grouping.py`
- `GA` = `services/telegram_gateway/tests/test_adapters.py`

## Configuración

- [x] T1 — Añadir `privacy_reject_phrase`, `privacy_text_consent_instruction`, propiedades `consent_accept_phrase` / `consent_reject_phrase` y el validador `_validate_text_consent_phrases` en `services/orchestrator/orchestrator/config.py`. Cubre: R1, R2, R3, R4.
- [x] T2 — Tests en `OT`: `test_accept_phrase_defaults_to_acepto`, `test_reject_phrase_defaults_to_no_acepto`, `test_configured_phrases_override_defaults`, `test_equal_phrases_fail_settings`, `test_instruction_without_placeholders_fails_settings`. Cubre: R1, R2, R3, R4.

## Utilidades puras

- [x] T3 — Añadir `TEXT_CONSENT_CHANNELS`, `matches_consent_phrase`, `text_consent_instruction` y `ConsentChallengeStore.consume_text` en `services/orchestrator/orchestrator/privacy.py`. Cubre: R5, R7, R11, R14.
- [x] T4 — Tests en `OT`: `test_phrase_match_is_exact_after_normalization` (parametrizado: `"  acepto "` sí; `"NO ACEPTO"`, `"acepto por favor"`, `"sí acepto"` no), `test_consume_text_requires_same_version_hash_and_chat`, `test_consume_text_consumes_only_once` (dos hilos, un solo `True`). Cubre: R5, R11, R14.

## Repositorio

- [x] T5 — `has_channel_privacy_consent` acepta `evidence_type IN ('button','text')` en el repositorio en memoria y en Postgres (`services/orchestrator/orchestrator/adapters/repository.py`). Cubre: R13.
- [x] T6 — Tests en `OT`: `test_text_evidence_counts_as_current_consent`, y conservar `CS::test_legacy_text_acceptance_does_not_grant_the_flow`; si existe test de SQL del repositorio Postgres, añadir aserción de la cláusula `IN ('button', 'text')`. Cubre: R13.

## Aviso Telegram

- [x] T7 — Cambiar `_consent_prompt` y `_notify_consent_prompt` en `domain.py`: Telegram solo `TextBlock` con aviso + instrucción y desafío siempre registrado; otros canales sin IDs en el texto y con `OptionsBlock` intacto. Cubre: R6, R7, R8, R9, R28.
- [x] T8 — Tests en `OT`: `test_telegram_notice_has_no_options_block`, `test_telegram_notice_text_is_panel_notice_plus_instruction` (incluye saludo en la primera presentación y frases efectivas), `test_notice_text_never_contains_button_ids` (parametrizado `telegram`/`whatsapp`), `test_telegram_notice_registers_challenge_with_version_hash_chat`, `test_telegram_notice_registers_challenge_without_send_channel_blocks`. Cubre: R6, R7, R8, R9.

## Aceptación y rechazo por texto

- [x] T9 — Añadir `_finish_acceptance` (extraído de `_handle_consent_button`) y `_record_text_consent_decision`; reescribir la rama Telegram de `_handle_pre_consent_text` con el orden del design; pasar `external_message_id` y `received_at` desde `_legacy_consent_gate` y `process_channel_message`. Cubre: R10, R11, R12, R14, R15, R17, R18, R19, R20, R21, R22, R23.
- [x] T10 — Tests en `OT` (ruta `process_channel_message` y ruta histórica `process_message`): `test_exact_accept_after_notice_records_text_evidence` (comprueba `result`, `evidence_type="text"`, `external_message_id`, versión, hash, `button_id==""`, timestamp == `received_at`), `test_legacy_route_accept_uses_update_id_as_external_message_id`, `test_text_accept_continues_to_awaiting_login_with_link`. Cubre: R10, R12.
- [x] T11 — Tests en `OT`: `test_accept_phrase_before_notice_shows_notice_without_decision`, `test_reject_phrase_before_notice_shows_notice_without_decision`, `test_accept_after_version_change_requires_new_notice`, `test_accept_from_other_chat_does_not_consume_challenge`, `test_second_accept_phrase_does_not_record_twice`. Cubre: R11, R14, R15.
- [x] T12 — Tests en `OT`: `test_reject_phrase_after_notice_records_minimal_text_decision_and_replies`, `test_reject_phrase_leaves_only_privacy_consents_row` (comprueba que `contacts`, `messages`, `events`, `db_query_audit`, `case_links`, `auto_handover_*` y `profiles.telegram_user_id` quedan vacíos para ese remitente y que se llamó `delete_contact_content`), `test_after_reject_accept_phrase_restarts_and_shows_notice`. Cubre: R18, R19, R20.
- [x] T13 — Tests en `OT`: `test_non_matching_text_resends_notice_with_instruction`, `test_non_matching_text_persists_nothing_and_skips_llm`, `test_affirmation_without_exact_phrase_does_not_use_button_reply` (parametrizado `sí`, `sí acepto`). Cubre: R21, R22, R23.

## Procesamiento en la petición y deduplicación

- [x] T14 — Añadir `consent_text_pending` en `domain.py` y usarlo en `main.py` (rama `NormalizedMessage` y rama `MessageRequest`) para procesar la frase en la petición. Cubre: R16.
- [x] T15 — Tests en `OT` con `TestClient`: `test_text_accept_storage_failure_returns_500` (repositorio con `fail_privacy_consent=True`), `test_redelivered_accept_message_is_duplicate` (mismo `external_message_id` tras aceptar → `status="duplicate"`, una sola fila y una sola respuesta). Cubre: R16, R17.

## Botones antiguos de Telegram

- [x] T16 — En `_handle_consent_button`, tras el chequeo de consentimiento vigente, ignorar botones del canal Telegram y reenviar el aviso de texto. Cubre: R25, R26, R27.
- [x] T17 — Tests en `OT`: `test_telegram_button_with_valid_proof_records_nothing` (genera prueba con el nonce del desafío pendiente), `test_telegram_button_returns_202_and_resends_text_notice` (vía `TestClient`, último envío sin `OptionsBlock`), `test_telegram_button_after_consent_is_ignored`. Cubre: R25, R26, R27.

## WhatsApp y #35 sin regresión

- [x] T18 — Migrar a `channel="whatsapp"` los tests de botones de `CS` (aceptar/rechazar con botón, prueba firmada, desafío por presentación, chat ajeno, repetidos, `test_text_affirmation_asks_for_the_button_and_keeps_awaiting`) sin relajar sus aserciones. Cubre: R28, R29, R30.
- [x] T19 — Tests en `OT`: `test_whatsapp_notice_keeps_signed_options_block`, `test_whatsapp_button_accept_records_button_evidence`, `test_whatsapp_accept_phrase_does_not_grant_consent`. Cubre: R28, R29, R30.
- [x] T20 — Adaptar `CB` para que la aceptación de Telegram sea por frase de texto tras el aviso y mantener `test_unconsented_sender_leaves_no_personal_data` y `test_acceptance_after_any_route_only_adds_privacy_consent` parametrizados por las seis rutas. Cubre: R24.

## Gateway

- [x] T21 — Añadir `message_grouping_reject_phrase` en `services/telegram_gateway/telegram_gateway/config.py`, extender `is_immediate` en `domain.py` y pasarla desde `grouping.py`. Cubre: R31.
- [x] T22 — Tests: `GW::test_reject_phrase_is_delivered_immediately`, `GW::test_empty_reject_phrase_does_not_change_grouping`; `GA::test_text_only_blocks_send_without_reply_markup`. Cubre: R31, R32.

## Config, docs y cierre

- [x] T23 — Documentar `PRIVACY_REJECT_PHRASE`, `PRIVACY_TEXT_CONSENT_INSTRUCTION` y `MESSAGE_GROUPING_REJECT_PHRASE` en `.env.example` y `render.yaml`; actualizar la sección de consentimiento de `docs/proyecto.md` (Telegram por frase, WhatsApp por botones, normalización, evidencia `text`). Cubre: R1, R2, R4, R31.
- [x] T24 — Escribir `progress/impl_consentimiento_texto_telegram.md` con el mapa de trazabilidad R1–R32 → tests y ejecutar `./init.sh` en verde. Cubre: R1–R32.
