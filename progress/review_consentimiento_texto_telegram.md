# Review — feature 46 `consentimiento_texto_telegram`

**Veredicto:** APPROVED

`bash ./init.sh` → exit 0, **3098 passed, 1 skipped**, 0 failed (19m13s), modo supervisado.

## Trazabilidad requirements ↔ tests
(OT = `services/orchestrator/tests/test_text_consent_telegram.py`)
- R1: [x] OT `test_accept_phrase_defaults_to_acepto`, `test_configured_phrases_override_defaults`
- R2: [x] OT `test_reject_phrase_defaults_to_no_acepto`, `test_configured_phrases_override_defaults`
- R3: [x] OT `test_equal_phrases_fail_settings` (comprueba que el error nombra `PRIVACY_REJECT_PHRASE`)
- R4: [x] OT `test_instruction_without_placeholders_fails_settings`
- R5: [x] OT `test_phrase_match_is_exact_after_normalization` (parametrizado)
- R6: [x] OT `test_telegram_notice_has_no_options_block`
- R7: [x] OT `test_telegram_notice_text_is_panel_notice_plus_instruction` (saludo solo la primera vez)
- R8: [x] OT `test_notice_text_never_contains_button_ids` (telegram/whatsapp)
- R9: [x] OT `test_telegram_notice_registers_challenge_with_version_hash_chat`, `..._without_send_channel_blocks`
- R10: [x] OT `test_exact_accept_after_notice_records_text_evidence` (result, evidence `text`, id externo, versión, hash, `button_id==""`, timestamp), `test_legacy_route_accept_uses_update_id_as_external_message_id`
- R11: [x] OT `test_consume_text_requires_same_version_hash_and_chat`, `test_consume_text_consumes_only_once` (hilos), `test_second_accept_phrase_does_not_record_twice`
- R12: [x] OT `test_text_accept_continues_to_awaiting_login_with_link`
- R13: [x] OT `test_text_evidence_counts_as_current_consent`, `test_postgres_consent_query_accepts_button_and_text`; `test_conversation_states.py::test_legacy_text_acceptance_does_not_grant_the_flow`
- R14: [x] OT `test_accept_phrase_before_notice_...`, `test_reject_phrase_before_notice_...`, `test_accept_after_version_change_requires_new_notice`, `test_accept_from_other_chat_does_not_consume_challenge`
- R15: [x] OT `test_accept_phrase_before_notice_shows_notice_without_decision`, `test_reject_phrase_before_notice_shows_notice_without_decision`
- R16: [x] OT `test_text_accept_storage_failure_returns_500`
- R17: [x] OT `test_redelivered_accept_message_is_duplicate`
- R18: [x] OT `test_reject_phrase_after_notice_records_minimal_text_decision_and_replies`
- R19: [x] OT `test_reject_phrase_leaves_only_privacy_consents_row`
- R20: [x] OT `test_after_reject_accept_phrase_restarts_and_shows_notice`
- R21: [x] OT `test_non_matching_text_resends_notice_with_instruction`
- R22: [x] OT `test_non_matching_text_persists_nothing_and_skips_llm`
- R23: [x] OT `test_affirmation_without_exact_phrase_does_not_use_button_reply` (ambos modales: no `confirm_button_reply` y reenvía instrucción)
- R24: [x] `test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`, `::test_acceptance_after_any_route_only_adds_privacy_consent`
- R25: [x] OT `test_telegram_button_with_valid_proof_records_nothing`
- R26: [x] OT `test_telegram_button_returns_202_and_resends_text_notice`
- R27: [x] OT `test_telegram_button_after_consent_is_ignored`
- R28: [x] OT `test_whatsapp_notice_keeps_signed_options_block` + tests de botones de `test_conversation_states.py` migrados a whatsapp
- R29: [x] OT `test_whatsapp_button_accept_records_button_evidence`
- R30: [x] OT `test_whatsapp_accept_phrase_does_not_grant_consent` (sin consentimiento + `confirm_button_reply` + `OptionsBlock`)
- R31: [x] `telegram_gateway/tests/test_grouping.py::test_reject_phrase_is_delivered_immediately`, `::test_empty_reject_phrase_does_not_change_grouping`
- R32: [x] `telegram_gateway/tests/test_adapters.py::test_text_only_blocks_send_without_reply_markup`

## Tasks completas
- T1–T24: [x] (todas marcadas en `specs/consentimiento_texto_telegram/tasks.md`; resultado de `./init.sh` registrado en `progress/impl_consentimiento_texto_telegram.md`)

## Revisión de código (puntos verificados)
- `orchestrator/privacy.py` `consume_text`: comprobación y borrado bajo `self._lock` → atómico (R11).
- `orchestrator/domain.py` `_handle_pre_consent_text`: la rama Telegram consume el desafío antes de `add_privacy_decision`; si falla, no se marca el mensaje y responde 500 (R16); si no hay desafío vigente, reenvía el aviso (R14/R15). En `CLOSED` descarta `consent_shown` y el desafío (R20). Afirmaciones parecidas no usan `confirm_button_reply` (R23). La compuerta sigue antes de `get_or_create_contact` (R24).
- `_handle_consent_button`: la rama Telegram va después del chequeo «ya consentido → ignorar» (R27) y antes de validar la prueba → no registra aunque la prueba sea válida (R25).
- `adapters/repository.py`: `IN ('button', 'text')` en la memoria y en Postgres, parametrizado; `legacy` excluido (R13).
- `main.py`: `pending` se calcula después de `consent_ready` en ambas rutas (R16).
- Arquitectura: sin imports entre servicios, sin contratos ni dependencias nuevas, sin `print`/`eval`/TODO en lo modificado.

## Checkpoints
- C1: [x] archivos y docs base presentes; `./init.sh` exit 0.
- C2: [x] solo #46 en `in_progress`; `progress/current.md` describe la sesión activa.
- C3: [x] sin servicios nuevos ni imports cruzados; sin dependencias nuevas; variables nuevas en `.env.example` y `render.yaml`; `.env` no está trackeado.
- C4: [x] tests con adaptadores falsos (FakeRepository, FakeTelegramClient, Conn/Cursor falsos para SQL); 3098 tests en verde.
- C5: [x] no hay archivos sospechosos sin trackear. La entrada de #46 en `history.md` la añade el leader al cerrar.
- C6: [x] spec completo; EARS revisado en el specreview; todas las tasks en `[x]`; cada R tiene su test.

## Observaciones no bloqueantes
1. El working tree también tiene cambios de otras features (#44 `confirmar_callback_telegram`: `answer_callback_query` en `telegram_gateway/adapters/telegram.py`, `main.py`, `config.py`; #45: `foreign_session_windows` en `repository.py`). Están fuera del alcance de #46. El leader debe hacer commit por feature o dejarlo claro en el mensaje.
2. `render.yaml`/`.env.example`: `MESSAGE_GROUPING_REJECT_PHRASE` hereda `PRIVACY_REJECT_PHRASE`. Si esta queda vacía (default efectivo `NO ACEPTO` en el orquestador), el gateway no trata `NO ACEPTO` como inmediato y puede agruparlo con otros textos. Pasa lo mismo con la frase de aceptación desde antes. Conviene fijar ambas frases de forma explícita en producción.
3. El default de `PRIVACY_TEXT_CONSENT_INSTRUCTION` en `.env.example`/`render.yaml` (una sola línea con puntos) es distinto del default del código (dos líneas). Los dos son válidos, solo difiere la presentación.

## Cambios requeridos
Ninguno.
