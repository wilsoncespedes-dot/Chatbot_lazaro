# Implementación — #70 aviso_intencion_compra

Todo en `services/orchestrator`, sin cambios en `contracts/` ni en handover.

## Resumen

- `purchase_intent.py` (nuevo): frases normalizadas, validación, coincidencia,
  intervalo anti-repetición y ventana de la marca.
- `config.py`, `.env.example`, `render.yaml`: cinco variables con rangos y
  validación de frases.
- `administration.py` / `admin_routes.py`: `kind="phrases"`, cuatro ajustes
  operativos con fallback al entorno y efecto inmediato.
- `harness.py`: `purchase_intent` solo en `buscar_base_conocimiento`; el
  motivo se retira de `args` y se expone en `RouterDecision`.
- `domain.py`: detección por frase y por router, evento `purchase_intent`,
  publicación en vivo, anti-repetición, tolerancia a fallos, caso opcional
  tras responder y marca/orden en la bandeja.
- `adapters/repository.py`: `last_event_at` y `last_purchase_intent_at` en
  `ConversationRef` (Protocol, Fake y Postgres).
- `panel_live.py`, `panel_live_js.py`, `advisor_panel.py`: tipo de evento,
  refresco en vivo e insignia «Interés de compra» con texto y escape.
- Tests nuevos: `test_purchase_intent_pure.py`, `test_purchase_intent_flow.py`,
  `test_purchase_intent_panel.py`, `test_purchase_intent_settings.py`; casos
  añadidos a `test_config.py`.
- T15 no se marca: `./init.sh` lo ejecuta Claude al terminar la sesión.

## Trazabilidad

- R1 → `tests/test_purchase_intent_settings.py::test_settings_page_shows_initial_phrases_defaults_and_range`; `tests/test_config.py::test_purchase_intent_defaults_and_documented_env`
- R2 → `tests/test_purchase_intent_pure.py::test_phrases_valid_rejects_invalid_lists`; `tests/test_purchase_intent_settings.py::test_invalid_phrases_reject_the_form_without_saving`; `tests/test_config.py::test_purchase_intent_settings_reject_invalid_values`
- R3 → `tests/test_purchase_intent_settings.py::test_invalid_stored_phrases_fall_back_to_the_environment`
- R4 → `tests/test_purchase_intent_settings.py::test_valid_settings_are_saved_and_apply_immediately`; `tests/test_purchase_intent_settings.py::test_advisor_session_cannot_save_purchase_settings`
- R5 → `tests/test_purchase_intent_flow.py::test_phrase_detection_records_reason_without_client_text`; `tests/test_purchase_intent_flow.py::test_phrases_are_detected_in_no_access_too`; `tests/test_purchase_intent_pure.py::test_matches_purchase_phrase_compares_normalized_substring`
- R6 → `tests/test_purchase_intent_flow.py::test_parser_accepts_purchase_intent_only_for_knowledge_search`; `tests/test_purchase_intent_flow.py::test_router_detection_records_reason_and_runs_search_without_args`
- R7 → `tests/test_purchase_intent_flow.py::test_parser_rejects_purchase_intent_with_any_other_tool`
- R8 → `tests/test_purchase_intent_flow.py::test_prompt_mentions_purchase_intent_only_for_knowledge_search`
- R9 → `tests/test_purchase_intent_flow.py::test_disabled_detection_ignores_phrase_and_router`
- R10 → `tests/test_purchase_intent_flow.py::test_human_handover_wins_over_purchase_intent`
- R11 → `tests/test_purchase_intent_flow.py::test_phrase_detection_records_reason_without_client_text`; `tests/test_purchase_intent_flow.py::test_router_detection_records_reason_and_runs_search_without_args`
- R12 → `tests/test_purchase_intent_flow.py::test_phrase_detection_records_reason_without_client_text`; `tests/test_purchase_intent_flow.py::test_router_detection_records_reason_and_runs_search_without_args`
- R13 → `tests/test_purchase_intent_panel.py::test_inbox_shows_the_purchase_interest_badge`; `tests/test_purchase_intent_panel.py::test_mark_expires_after_the_configured_window`; `tests/test_purchase_intent_panel.py::test_mark_expires_when_a_later_case_closed_exists`; `tests/test_purchase_intent_panel.py::test_mark_is_hidden_for_closed_conversations`; `tests/test_purchase_intent_pure.py::test_has_purchase_interest_window_status_and_case_closed`
- R14 → `tests/test_purchase_intent_panel.py::test_order_is_pending_then_interest_then_rest`
- R15 → `tests/test_purchase_intent_flow.py::test_live_event_uses_contact_key_without_case`; `tests/test_purchase_intent_flow.py::test_live_event_uses_last_case_key_when_it_exists`; `tests/test_purchase_intent_panel.py::test_live_payload_is_minimal_for_purchase_intent`
- R16 → `tests/test_purchase_intent_panel.py::test_live_javascript_accepts_purchase_intent`; `tests/test_purchase_intent_panel.py::test_live_fragment_matches_initial_load`
- R17 → `tests/test_purchase_intent_flow.py::test_create_case_on_opens_a_case_after_answering`; `tests/test_purchase_intent_flow.py::test_create_case_on_does_not_duplicate_an_existing_case`
- R18 → `tests/test_purchase_intent_flow.py::test_create_case_off_does_not_change_state_or_call_handover`
- R19 → `tests/test_purchase_intent_flow.py::test_anti_repetition_blocks_within_interval_and_allows_after`; `tests/test_purchase_intent_pure.py::test_within_interval_blocks_inside_and_allows_after_the_boundary`
- R20 → `tests/test_purchase_intent_flow.py::test_anti_repetition_blocks_within_interval_and_allows_after`; `tests/test_purchase_intent_pure.py::test_within_interval_blocks_inside_and_allows_after_the_boundary`
- R21 → `tests/test_purchase_intent_flow.py::test_event_failure_does_not_stop_the_reply`
- R22 → `tests/test_purchase_intent_flow.py::test_prompt_keeps_client_text_as_data`; `tests/test_purchase_intent_pure.py::test_matches_purchase_phrase_compares_normalized_substring`
- R23 → `tests/test_purchase_intent_flow.py::test_prompt_injection_with_purchase_phrase_skips_the_router`
- R24 → `tests/test_purchase_intent_panel.py::test_badge_text_is_escaped_and_does_not_rely_on_color`; `tests/test_purchase_intent_settings.py::test_settings_escape_html_in_effective_values`; `tests/test_purchase_intent_panel.py::test_live_fragment_matches_initial_load`
- R25 → `tests/test_config.py::test_purchase_intent_defaults_and_documented_env`; `tests/test_config.py::test_purchase_intent_settings_reject_invalid_values`

## Fallo de init.sh (intento 1)

7 tests fallan (4478 pasan):
- test_purchase_intent_flow.py::test_live_event_uses_last_case_key_when_it_exists: `event.kind == 'message'` en vez de 'purchase_intent'.
- test_purchase_intent_pure.py::test_has_purchase_interest_window_status_and_case_closed: has_purchase_interest devuelve False donde el test espera True (limite exacto de ventana 72h / estado 'pendiente' / caso cerrado).
- test_purchase_intent_settings.py::test_invalid_phrases_reject_the_form_without_saving (5 casos: '', 'ab', frase larga, 31 frases, 'me interesa,\x00').
Corrige codigo o tests segun el spec; no toques feature_list.json. Ejecuta solo esos tests con pytest.

## Correcciones (intento 2)

- `administration.py::validate_settings_form`: `purchase_intent.phrases` ya no se
  trata como «vacío = borrar»; si la clave llega vacía o con una lista que queda
  vacía tras normalizar, invalida todo el formulario (R2). Si la clave no viene
  en el POST, se conserva el valor guardado (los formularios parciales siguen
  funcionando).
- `admin.py::render_settings`: el bloque de error del formulario incluye
  `data-code="validation_error"`, igual que el resto de errores del panel (R2).
- `tests/test_purchase_intent_flow.py`: el evento en vivo se busca por
  `kind == "purchase_intent"` en vez de exigir que sea el último; con un caso
  abierto, el guardado de la respuesta publica después un evento `message`
  (R15 no exige orden entre ambos).
- `tests/test_purchase_intent_pure.py`: el caso límite de 72 h usa un
  `case_closed` anterior a la detección; con uno posterior la marca no aplica
  por R13 («detección posterior a su último case_closed»).

No se ejecutaron comandos de shell: `./init.sh` lo corre Claude al terminar.
Pendiente T15 (verificación final).

## Resultado de init.sh (tras corrección, intento 2)

`./init.sh`: 4485 passed, 1 skipped; entorno listo. Trazabilidad R<n> → test presente arriba.
