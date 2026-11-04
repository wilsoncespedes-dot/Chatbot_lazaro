# Review — feature 37

**Veredicto:** APPROVED

## Trazabilidad requirements ↔ tests

- R1: [x] `test_conversation_states.py::test_all_seven_states_exist`, `::test_transition_table_covers_the_documented_paths`
- R2: [x] `test_conversation_states.py::test_first_message_shows_greeting_notice_and_buttons_without_persisting`
- R3: [x] `test_conversation_states.py::test_policy_question_while_awaiting_consent_answers_policy`
- R4: [x] `test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`
- R5: [x] `test_conversation_states.py::test_reject_button_records_only_minimal_evidence_and_deletes_content`
- R6: [x] `test_conversation_states.py::test_text_affirmation_asks_for_the_button_and_keeps_awaiting`
- R7: [x] `test_conversation_states.py::test_new_policy_version_blocks_new_messages_and_requests_consent`
- R8: [x] `test_conversation_states.py::test_rejected_conversation_restarts_from_new_on_next_message`
- R9: [x] `test_conversation_states.py::test_awaiting_login_only_sends_the_reminder`
- R10: [x] `test_conversation_states.py::test_active_conversation_keeps_the_existing_attention_flow`
- R11: [x] `test_conversation_states.py::test_escalation_sets_with_advisor_and_forwarding_skips_the_llm`
- R12: [x] `test_conversation_states.py::test_with_advisor_stops_bot_replies_until_resolution`
- R13: [x] `test_conversation_states.py::test_credential_and_session_events_update_the_state`
- R14: [x] `test_conversation_states.py::test_no_access_replies_suspended_and_escalates_without_rag`
- R15: [x] `test_conversation_states.py::test_unsupported_content_gets_fixed_reply_without_state_change`
- R16: [x] `test_conversation_states.py::test_credential_and_session_events_update_the_state`
- R17: [x] `test_conversation_states.py::test_credential_and_session_events_update_the_state`
- R18: [x] `test_conversation_states.py::test_credential_and_session_events_update_the_state`
- R19: [x] `test_conversation_texts.py::test_texts_page_requires_admin_session`, `::test_admin_saves_texts_and_version_together`
- R20: [x] `test_conversation_texts.py::test_admin_saves_texts_and_version_together`, `::test_version_change_from_panel_forces_new_acceptance`
- R21: [x] `test_conversation_texts.py::test_saved_texts_are_used_without_restart`, `::test_unsupported_reply_comes_from_the_panel`
- R22: [x] `test_multichannel_identity.py::test_before_consent_no_contact_or_personal_data_is_persisted`
- R23: [x] `test_multichannel_identity.py::test_same_numeric_id_in_telegram_and_whatsapp_stays_separate`
- R24: [x] `test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`
- R25: [x] `test_conversation_states.py::test_missing_legal_text_fails_closed_without_persisting`
- R26: [x] `test_conversation_states.py::test_accept_button_records_version_hash_message_and_button`
- R27: [x] `test_conversation_states.py::test_credential_and_session_events_update_the_state`
- R28: [x] `test_conversation_states.py::test_no_access_suppression_request_moves_to_advisor_without_rag`
- R29: [x] `test_conversation_states.py::test_reject_button_records_only_minimal_evidence_and_deletes_content`
- R30: [x] `test_conversation_states.py::test_no_fixed_or_legal_text_is_generated_by_the_llm`
- R31: [x] `test_multichannel_identity.py::test_contacts_have_no_client_id_and_channels_are_not_linked`
- R32: [x] `test_conversation_texts.py::test_saved_texts_are_used_without_restart`
- R33: [x] `test_conversation_states.py::test_missing_legal_text_fails_closed_without_persisting`
- R34: [x] `test_conversation_states.py::test_legacy_text_acceptance_does_not_grant_the_flow`
- R35: [x] `test_conversation_states.py::test_first_message_shows_greeting_notice_and_buttons_without_persisting`
- R36: [x] `test_conversation_states.py::test_reject_button_records_only_minimal_evidence_and_deletes_content`
- R37: [x] `test_conversation_states.py::test_old_or_tampered_button_does_not_accept_the_new_policy`, `::test_challenge_is_random_per_presentation_and_invalidates_previous_buttons`
- R38: [x] `test_send.py::test_http_telegram_client_sends_reply_markup`, `test_webhook.py::test_callback_query_is_normalized_and_forwarded_as_button`, `test_webhook.py::test_webhook_callback_reaches_orchestrator_and_persists_the_decision`
- R39: [x] `test_conversation_states.py::test_challenge_is_random_per_presentation_and_invalidates_previous_buttons`, `::test_button_without_a_pending_presentation_is_rejected`, `::test_repeated_reject_after_accept_is_ignored`, `::test_repeated_accept_after_reject_is_ignored`, `::test_challenge_store_consumes_only_once`
- R40: [x] `test_conversation_states.py::test_button_from_another_chat_does_not_consume_the_challenge`; `services/telegram_gateway/tests/test_webhook.py::test_webhook_callback_from_another_chat_does_not_consume_the_challenge`

## Tasks completas

- T1–T15: [x]
- T16: [x] `./init.sh` verde, trazabilidad R1–R40 actualizada y revisión final
  APPROVED; marcado por el líder al cerrar la feature.

## Revisión final

Los cuatro hallazgos de revisiones previas están resueltos: Telegram muestra y
recibe botones interactivos; HMAC cubre canal, identidad, chat, botón y huella
de aviso; el desafío incluye nonce aleatorio de un solo uso, se consume bajo
candado y no opera si la identidad ya tiene consentimiento vigente; un callback
del mismo usuario desde un chat distinto se rechaza sin consumir el desafío. El
test de webhook confirma después que el chat correcto todavía puede usarlo.

La suite completa fue ejecutada por el líder con exit code 0: **2,298 passed,
1 skipped, 2 warnings**. La trazabilidad concreta R1–R40 está en
`progress/impl_estados_y_consentimiento.md`.

## Checkpoints

- C1: [x] harness válido y suite verde según resultado del líder.
- C2: [x] #37 está `done`; `progress/current.md` conserva la plantilla y el
  historial registra la sesión cerrada.
- C3: [x] límites de capas, contratos y transporte Telegram cubiertos.
- C4: [x] suite verde y tests con fakes; casos de consentimiento obsoleto,
  manipulado, repetido, identidad/chat incorrectos están cubiertos.
- C5: [x] T16 marcada, #37 registrada en `progress/history.md`, estado `done`
  y `progress/current.md` vacía salvo la plantilla.
- C6: [x] R1–R40 están mapeados a tests; T16 queda justificada como cierre del
  líder tras esta aprobación.

No ejecuté `./init.sh`; usé el resultado reportado por el líder.
