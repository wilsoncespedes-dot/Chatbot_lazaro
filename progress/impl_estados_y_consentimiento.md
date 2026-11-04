# Implementación — estados_y_consentimiento (#37)

## Resumen

- Se completó la máquina de siete estados (`ConversationState`,
  `ConversationEvent`, `transition_state`) y el enrutamiento por estado en
  `services/orchestrator/orchestrator/domain.py`.
- El consentimiento se prueba solo con los botones canónicos
  `privacy.accept`/`privacy.reject`; la evidencia guarda canal, id externo,
  versión, hash, resultado, mensaje externo, botón y fecha UTC antes de
  confirmar. El rechazo elimina el contenido personal del hilo y conserva solo
  la evidencia mínima.
- `privacy_consents` se migra de forma aditiva (`result`, `evidence_type`,
  `external_message_id`, `button_id`, `occurred_at`) y `accepted_at` pasa a
  nullable. Las aceptaciones históricas quedan como `evidence_type='legacy'` y
  no habilitan el flujo: `has_channel_privacy_consent` exige una aceptación de
  botón de la versión vigente.
- `conversation_states` se persiste solo para contactos consentidos; antes de
  aceptar, el estado `nuevo → esperando_consentimiento` y el cierre por rechazo
  se resuelven en memoria sin crear contacto ni filas de estado.
- Los textos fijos y legales se leen **solo** del panel (`app_settings`), sin
  fallback a variables de entorno ni constantes legales. Si falta un texto
  requerido se falla cerrado y no se habilita el procesamiento posterior.
  `conversation_texts()` ya no mezcla `stored.field or settings.field`.
- El panel admin existente incorpora `/admin/texts` con sesión admin y CSRF;
  guarda texto y versión legal en una sola transacción y los cambios se leen en
  el siguiente mensaje sin reiniciar.
- Los eventos de #38 (`login_valid`, `login_expired`, `credential_expired`,
  `credential_renewed`, `session_closed`, `session_idle_timeout`) y de asesores
  (`escalated`, `advisor_resolved`, `advisor_returned`) se aplican con
  `apply_conversation_event`, sin implementar credenciales ni endpoints de
  login.
- R39: cada presentación del aviso emite un `nonce` aleatorio en
  `ConsentChallengeStore` (solo memoria) y las pruebas de los dos botones se
  calculan con ese nonce. El primer clic válido consume el desafío bajo
  `threading.Lock`; un callback ausente, repetido o de otra presentación no
  registra evidencia ni muta estado. Con consentimiento vigente cualquier botón
  se ignora antes de tocar contenido o estado.

## Cambios de prueba

- `services/orchestrator/tests/conftest.py` siembra los textos del panel en
  `make_env` (simulando que un administrador ya los guardó). `seed_texts=False`
  permite probar el fallo cerrado sin configuración del panel.
- Se añadieron pruebas para pregunta de política estando en espera, botón
  desconocido, solicitud de supresión en `sin_acceso`, parada de respuestas del
  bot en `con_asesor` y ausencia de fallback de textos desde el entorno.
- Correcciones tras la primera verificación:
  - `test_non_positive_sender_is_never_staff` siembra los textos del panel en su
    `RecordingRepository` nuevo (antes el repositorio recién creado no tenía
    textos y la compuerta fallaba cerrada sin enviar el aviso).
  - `test_button_acceptance_records_consent` compara `accepted_at` con el
    timestamp del botón (`03:04:00`), no con el reloj fijo (`03:04:05`).
  - `test_consent_store_failure_returns_500_without_confirmation` usa un
    `TestClient` con `raise_server_exceptions=False` para comprobar la respuesta
    500 del handler global en lugar de propagar la excepción del transporte.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_conversation_states.py::test_all_seven_states_exist`, `::test_transition_table_covers_the_documented_paths`
- R2 → `services/orchestrator/tests/test_conversation_states.py::test_first_message_shows_greeting_notice_and_buttons_without_persisting`; `services/orchestrator/tests/test_privacy.py::test_without_consent_sends_notice_and_stores_nothing`
- R3 → `services/orchestrator/tests/test_conversation_states.py::test_policy_question_while_awaiting_consent_answers_policy`
- R4 → `services/orchestrator/tests/test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`, `::test_unknown_button_does_not_grant_consent`; `services/orchestrator/tests/test_privacy.py::test_button_acceptance_records_consent`; `services/orchestrator/tests/test_repository_schema.py::test_schema_declares_conversation_states_and_button_evidence`
- R5 → `services/orchestrator/tests/test_conversation_states.py::test_reject_button_records_only_minimal_evidence_and_deletes_content`, `::test_unknown_button_does_not_grant_consent`
- R6 → `services/orchestrator/tests/test_conversation_states.py::test_text_affirmation_asks_for_the_button_and_keeps_awaiting`; `services/orchestrator/tests/test_privacy.py::test_acceptance_with_extra_text_does_not_record_consent`
- R7 → `services/orchestrator/tests/test_conversation_states.py::test_new_policy_version_blocks_new_messages_and_requests_consent`; `services/orchestrator/tests/test_conversation_texts.py::test_version_change_from_panel_forces_new_acceptance`; `services/orchestrator/tests/test_privacy.py::test_version_change_requires_new_acceptance_and_keeps_old_rows`
- R8 → `services/orchestrator/tests/test_conversation_states.py::test_rejected_conversation_restarts_from_new_on_next_message`, `::test_transition_table_covers_the_documented_paths`
- R9 → `services/orchestrator/tests/test_conversation_states.py::test_awaiting_login_only_sends_the_reminder`
- R10 → `services/orchestrator/tests/test_conversation_states.py::test_active_conversation_keeps_the_existing_attention_flow`; `services/orchestrator/tests/test_privacy.py::test_current_consent_keeps_the_normal_flow`
- R11 → `services/orchestrator/tests/test_conversation_states.py::test_escalation_sets_with_advisor_and_forwarding_skips_the_llm`, `::test_with_advisor_stops_bot_replies_until_resolution`
- R12 → `services/orchestrator/tests/test_conversation_states.py::test_escalation_sets_with_advisor_and_forwarding_skips_the_llm`, `::test_with_advisor_stops_bot_replies_until_resolution`
- R13 → `services/orchestrator/tests/test_conversation_states.py::test_escalation_sets_with_advisor_and_forwarding_skips_the_llm`, `::test_credential_and_session_events_update_the_state`
- R14 → `services/orchestrator/tests/test_conversation_states.py::test_no_access_replies_suspended_and_escalates_without_rag`
- R15 → `services/orchestrator/tests/test_conversation_states.py::test_unsupported_content_gets_fixed_reply_without_state_change`, `::test_unsupported_and_unknown_events_keep_the_state`; `services/orchestrator/tests/test_conversation_texts.py::test_unsupported_reply_comes_from_the_panel`
- R16 → `services/orchestrator/tests/test_conversation_states.py::test_credential_and_session_events_update_the_state`, `::test_transition_table_covers_the_documented_paths`
- R17 → `services/orchestrator/tests/test_conversation_states.py::test_credential_and_session_events_update_the_state`, `::test_transition_table_covers_the_documented_paths`
- R18 → `services/orchestrator/tests/test_conversation_states.py::test_credential_and_session_events_update_the_state`, `::test_transition_table_covers_the_documented_paths`
- R19 → `services/orchestrator/tests/test_conversation_texts.py::test_texts_page_requires_admin_session`, `::test_admin_saves_texts_and_version_together`, `::test_texts_post_requires_csrf`; `services/orchestrator/tests/test_conversation_states.py::test_panel_texts_are_read_at_runtime_without_restart`
- R20 → `services/orchestrator/tests/test_conversation_texts.py::test_admin_saves_texts_and_version_together`, `::test_legal_text_and_version_are_required`, `::test_version_change_from_panel_forces_new_acceptance`; `services/orchestrator/tests/test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`
- R21 → `services/orchestrator/tests/test_conversation_texts.py::test_saved_texts_are_used_without_restart`, `::test_unsupported_reply_comes_from_the_panel`; `services/orchestrator/tests/test_conversation_states.py::test_panel_texts_are_read_at_runtime_without_restart`
- R22 → `services/orchestrator/tests/test_conversation_states.py::test_first_message_shows_greeting_notice_and_buttons_without_persisting`; `services/orchestrator/tests/test_multichannel_identity.py::test_before_consent_no_contact_or_personal_data_is_persisted`, `::test_legacy_telegram_before_consent_only_persists_update_id`
- R23 → `services/orchestrator/tests/test_conversation_states.py::test_identity_is_isolated_per_channel`; `services/orchestrator/tests/test_multichannel_identity.py::test_contact_lookup_uses_channel_and_external_user_id`, `::test_same_numeric_id_in_telegram_and_whatsapp_stays_separate`
- R24 → `services/orchestrator/tests/test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`, `::test_reject_button_records_only_minimal_evidence_and_deletes_content`; `services/orchestrator/tests/test_privacy.py::test_button_acceptance_records_consent`; `services/orchestrator/tests/test_repository_schema.py::test_schema_declares_conversation_states_and_button_evidence`
- R25 → `services/orchestrator/tests/test_conversation_states.py::test_missing_legal_text_fails_closed_without_persisting`, `::test_settings_texts_are_not_a_fallback_for_the_panel`; `services/orchestrator/tests/test_privacy.py::test_without_privacy_config_drops_client_route`
- R26 → `services/orchestrator/tests/test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`; `services/orchestrator/tests/test_privacy.py::test_button_acceptance_records_consent`
- R27 → `services/orchestrator/tests/test_conversation_states.py::test_credential_and_session_events_update_the_state`, `::test_transition_table_covers_the_documented_paths`
- R28 → `services/orchestrator/tests/test_conversation_states.py::test_no_access_replies_suspended_and_escalates_without_rag`, `::test_no_access_suppression_request_moves_to_advisor_without_rag`
- R29 → `services/orchestrator/tests/test_conversation_states.py::test_reject_button_records_only_minimal_evidence_and_deletes_content`
- R30 → `services/orchestrator/tests/test_conversation_states.py::test_no_fixed_or_legal_text_is_generated_by_the_llm`; `services/orchestrator/tests/test_conversation_texts.py::test_unsupported_reply_comes_from_the_panel`
- R31 → `services/orchestrator/tests/test_conversation_states.py::test_identity_is_isolated_per_channel`; `services/orchestrator/tests/test_multichannel_identity.py::test_contacts_have_no_client_id_and_channels_are_not_linked`
- R32 → `services/orchestrator/tests/test_conversation_texts.py::test_saved_texts_are_used_without_restart`; `services/orchestrator/tests/test_conversation_states.py::test_panel_texts_are_read_at_runtime_without_restart`, `::test_settings_texts_are_not_a_fallback_for_the_panel`
- R33 → `services/orchestrator/tests/test_conversation_states.py::test_missing_legal_text_fails_closed_without_persisting`, `::test_settings_texts_are_not_a_fallback_for_the_panel`; `services/orchestrator/tests/test_conversation_texts.py::test_legal_text_and_version_are_required`
- R34 → `services/orchestrator/tests/test_conversation_states.py::test_legacy_text_acceptance_does_not_grant_the_flow`; `services/orchestrator/tests/test_repository_schema.py::test_migrations_add_button_evidence_without_rewriting_history`
- R35 → `services/orchestrator/tests/test_conversation_states.py::test_first_message_shows_greeting_notice_and_buttons_without_persisting`
- R36 → `services/orchestrator/tests/test_conversation_states.py::test_reject_button_records_only_minimal_evidence_and_deletes_content`, `::test_rejected_conversation_restarts_from_new_on_next_message`
- R37 → `services/orchestrator/tests/test_conversation_states.py::test_old_or_tampered_button_does_not_accept_the_new_policy`, `::test_challenge_is_random_per_presentation_and_invalidates_previous_buttons`; `services/telegram_gateway/tests/test_webhook.py::test_callback_without_proof_is_still_forwarded_for_the_orchestrator_to_reject`, `::test_webhook_callback_reaches_orchestrator_and_persists_the_decision`; `contracts/tests/test_channels.py::test_normalized_button_accepts_policy_proof`
- R38 → `services/telegram_gateway/tests/test_multicanal.py::test_telegram_adapter_sends_signed_options_as_inline_keyboard`, `::test_http_telegram_client_sends_reply_markup`; `services/telegram_gateway/tests/test_send.py::test_send_canonical_signed_options_renders_inline_keyboard`; `services/telegram_gateway/tests/test_webhook.py::test_callback_query_is_normalized_and_forwarded_as_button`, `::test_duplicate_callback_is_not_forwarded_twice`, `::test_webhook_callback_reaches_orchestrator_and_persists_the_decision`; `services/orchestrator/tests/test_conversation_states.py::test_consent_prompt_carries_signed_canonical_buttons`; `contracts/tests/test_channels.py::test_options_block_accepts_aligned_button_metadata`
- R39 → `services/orchestrator/tests/test_conversation_states.py::test_challenge_is_random_per_presentation_and_invalidates_previous_buttons`, `::test_button_without_a_pending_presentation_is_rejected`, `::test_repeated_reject_after_accept_is_ignored`, `::test_repeated_accept_after_reject_is_ignored`, `::test_challenge_store_consumes_only_once`
- R40 → `services/orchestrator/tests/test_conversation_states.py::test_button_from_another_chat_does_not_consume_the_challenge`; `services/telegram_gateway/tests/test_webhook.py::test_webhook_callback_from_another_chat_does_not_consume_the_challenge`

## Verificación

- Primera ejecución de `./init.sh`: falló con 3 tests y 2 warnings
  (`2275 passed, 1 skipped`). Los tres casos se corrigieron sin cambiar el
  comportamiento de producto.
  - `test_consent_before_data.py::test_non_positive_sender_is_never_staff` no
    recibió texto porque su `RecordingRepository` recién creado no tenía los
    textos de panel que ahora exige el flujo.
  - `test_privacy.py::test_button_acceptance_records_consent` compara contra
    segundos 5, aunque el mensaje de prueba tiene timestamp `03:04:00`.
  - `test_privacy.py::test_consent_store_failure_returns_500_without_confirmation`
    deja escapar la excepción del TestClient aunque existe handler HTTP 500.
- Segunda ejecución de `./init.sh`: exit code 0, **2,278 passed, 1 skipped**,
  2 warnings. Incluye regresión de #35/#36.
- Verificación tras botones Telegram: exit code 0, **2,291 passed, 1 skipped**,
  2 warnings.
- Verificación final tras desafío de un solo uso: exit code 0,
  **2,296 passed, 1 skipped**, 2 warnings; incluye regresión #35/#36.
- Tras T15 (prueba ligada a `external_chat_id`), `./init.sh` terminó con exit
  code 0: **2,298 passed, 1 skipped, 2 warnings**.
- Revisión final independiente de código #37: `APPROVED` en
  `progress/review_estados_y_consentimiento.md`; #37 quedó `done`.

## Correcciones requeridas por la primera revisión de código

`progress/review_estados_y_consentimiento.md` solicita dos cambios bloqueantes:

1. El gateway Telegram debe mostrar botones interactivos y normalizar
   `callback_query` (hasta ahora solo se mostraban etiquetas como texto y los
   tests inyectaban botones directamente al orquestador).
2. El callback debe probar la versión/hash del aviso que lo originó; un clic
   antiguo no puede aceptar la política publicada después.
3. La prueba también debe quedar vinculada a `(channel, external_user_id)` para
   que reenviar el callback a otro chat no autorice esa identidad.
4. El callback debe ser un desafío aleatorio de un solo uso ligado a la
   presentación y consumirse atómicamente; ignorar botones cuando ya existe
   consentimiento vigente. Probar rechazo repetido tras aceptar y aceptación
   repetida tras rechazar.
5. Ligarlo también al `external_chat_id`: un callback del mismo usuario desde
   otro chat no puede consumir el desafío.

Se añadieron R37–R40, T12–T16 y cambios de diseño para cubrir los hallazgos.
La suite verde anterior no cubría la integración Telegram real.

### T12–T13 implementadas (segunda pasada)

- El contrato añade `NormalizedMessage.button_proof` y
  `OptionsBlock.option_ids`/`option_proofs` (aditivo, S15 de `CONTRATOS.md`).
- El orquestador genera `HMAC-SHA256(service_token, "<channel>:<external_user_id>:<button_id>:<notice_version>:<notice_sha256>")`
  truncado a 32 hex y lo adjunta a cada opción; el gateway pinta un teclado
  inline con `callback_data = "<button_id>:<proof>"`.
- El gateway extrae `callback_query`, lo deduplica por el id del callback y lo
  reenvía como `NormalizedMessage(kind="button", button_id, button_proof)`.
- El orquestador recalcula la prueba con la identidad/canal y la política
  vigentes; si no coincide, muestra de nuevo el aviso y no registra
  consentimiento ni cambia estado (R37). El botón desconocido sigue mostrando
  el aviso.
- Pruebas nuevas: teclado inline, `reply_markup` HTTP, callback normalizado,
  deduplicación, callback sin prueba, publicación de versión nueva entre
  presentación y clic, y recorrido webhook → consentimiento persistido con
  repositorio falso del orquestador.

### T14 implementada (tercera pasada)

- `privacy.ConsentChallengeStore` guarda por `(channel, external_user_id)` un
  `ConsentChallenge(notice_version, notice_sha256, nonce)` y `consume` valida la
  prueba HMAC del nonce y borra el desafío bajo `threading.Lock`.
- `_notify_consent_prompt` registra un nonce nuevo en cada presentación y
  calcula `option_proofs` con él; la prueba anterior deja de valer.
- `_handle_consent_button` ignora el botón si ya hay consentimiento vigente y
  consume el desafío **antes** de guardar evidencia, borrar contenido o cambiar
  estado. Un callback ausente/repetido/de otra presentación no registra decisión.
- Los helpers de tests presentan el aviso y extraen la prueba del desafío real;
  se añadieron pruebas de nonce distinto por presentación, callback sin
  presentación, rechazo repetido tras aceptar, aceptación repetida tras rechazar
  y consumo concurrente único.

### T15 implementada (cuarta pasada)

- La prueba HMAC y el desafío efímero incluyen ahora `external_chat_id` además
  de canal, id externo, botón, versión/hash y nonce.
  `ConsentChallengeStore.register/consume` guardan y comprueban el chat que
  recibió el aviso.
- `_handle_consent_button` rechaza sin consumir ni re-presentar cuando el
  callback llega desde otro chat, de modo que el desafío original sigue válido.
- Pruebas nuevas: un botón del mismo usuario desde otro chat no registra ni
  consume el desafío (orquestador) y el recorrido real de webhook con un
  `callback_query` desde otro chat no persiste consentimiento y luego acepta
  desde el chat correcto.
- Se actualizaron los helpers de prueba para firmar con el chat presentado y la
  trazabilidad incluye R40.

T16 quedó marcada `[x]` después de `./init.sh` y revisión `APPROVED`.
T12–T16 están completas.
