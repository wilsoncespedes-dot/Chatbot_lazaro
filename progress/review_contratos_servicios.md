# Review — feature 1 (contratos_servicios)

**Veredicto:** APPROVED

Revisión de código en modo nocturno, 2026-10-30. Comprobado contra
`specs/contratos_servicios/{requirements,design,tasks}.md`, `docs/architecture.md`,
`docs/conventions.md`, `CHECKPOINTS.md` y los 7 `acceptance` de `feature_list.json`.

## Verificación ejecutada

- `./init.sh` termina con exit code 0. Todas las comprobaciones salen `[OK]` y pasan 273 tests.
- `.venv/Scripts/python.exe -m pytest contracts -q` da 273 passed.
- `python -m pytest -q` en la raíz también sale verde.

## Trazabilidad requirements ↔ tests

TD = `contracts/tests/test_contratos_doc.py`, TM = `contracts/tests/test_models.py`,
TE = `contracts/tests/test_examples.py`, TP = `contracts/tests/test_packaging.py`.

- R1: [x] TD `test_doc_has_a_section_per_route`
- R2: [x] TD `test_route_names_exposing_service` (compara con el servicio exacto de `ROUTES`)
- R3: [x] TD `test_route_names_caller`
- R4: [x] TD `test_route_names_models_in_package`
- R5: [x] TD `test_request_table_lists_every_request_field`, `test_manuals_request_table_lists_multipart_parts`, `test_check_timeouts_request_table_has_no_fields_row`
- R6: [x] TD `test_response_section_has_success_code_and_fields` (con `SearchResult` para `/search`)
- R7: [x] TD `test_errors_table_has_common_rows`
- R8: [x] TD `test_errors_table_has_route_specific_rows`
- R9: [x] TD `test_common_rules_document_service_token`
- R10: [x] TD `test_common_rules_document_error_shape_and_codes` (las 8 filas de la tabla de design §4)
- R11: [x] TD `test_common_rules_document_duplicate_messages`
- R12: [x] TD `test_common_rules_document_health`
- R13: [x] TD `test_assumptions_include_manuals_multipart`
- R14: [x] TD `test_assumptions_include_last_messages`
- R15: [x] TD `test_assumptions_mention_s1_to_s10`
- R16: [x] TP `test_model_is_exported_and_is_base_model` (los 20 modelos), `test_all_names_are_importable`
- R17: [x] TP `test_pydantic_major_version_is_2`, `test_model_is_exported_and_is_base_model`
- R18: [x] TM `test_unexpected_field_is_rejected` (19 modelos de objeto), `test_unexpected_field_inside_search_response_element_is_rejected`
- R19: [x] TM `test_missing_required_field_is_rejected` (cada campo obligatorio de cada modelo, sacado de los ejemplos), `test_every_model_has_a_required_field_case_except_check_timeouts_request`
- R20: [x] TM `test_datetime_without_timezone_is_rejected` (`received_at` y `at`)
- R21: [x] TM `test_invalid_text_is_rejected` (los 4 modelos, texto vacío y de 4097), `test_text_at_max_length_is_accepted`
- R22: [x] TM `test_invalid_identifier_is_rejected` (los 8 campos), `test_invalid_timed_out_case_identifier_is_rejected`
- R23: [x] TM `test_message_request_requires_its_fields`, `test_message_request_rejects_negative_update_id`, `test_message_request_rejects_non_integer_ids`
- R24: [x] TM `test_message_response_accepts_valid_status`, `test_message_response_rejects_invalid_status`
- R25: [x] TM `test_send_request_requires_chat_id_and_text`
- R26: [x] TM `test_sent_must_be_true` (`SendResponse` y `CaseReplyResponse`)
- R27: [x] TM `test_search_request_requires_query_and_top_k`
- R28: [x] TM `test_search_request_rejects_top_k_out_of_range` (0 y 21), `test_search_request_accepts_top_k_limits`
- R29: [x] TM `test_search_response_accepts_empty_list`, `test_search_response_accepts_results`, `test_search_response_rejects_object_body`
- R30: [x] TM `test_search_result_rejects_score_out_of_range`, `test_search_result_accepts_score_limits`
- R31: [x] TM `test_handover_request_requires_its_fields`
- R32: [x] TM `test_handover_request_accepts_valid_reason`, `test_handover_request_rejects_invalid_reason`
- R33: [x] TM `test_handover_request_rejects_too_many_last_messages` (10 se aceptan, 11 se rechazan)
- R34: [x] TM `test_last_message_accepts_valid_role`, `test_last_message_rejects_invalid_role`
- R35: [x] TM `test_handover_response_accepts_valid_status`, `test_handover_response_requires_status_and_case_id`
- R36: [x] TM `test_case_reply_request_requires_advisor_id_and_text`
- R37: [x] TM `test_manual_upload_request_rejects_invalid_name`
- R38: [x] TM `test_manual_upload_response_rejects_zero_chunks`
- R39: [x] TM `test_case_close_request_requires_advisor_id`
- R40: [x] TM `test_case_close_response_rejects_invalid_status`
- R41: [x] TM `test_check_timeouts_request_accepts_empty_object`
- R42: [x] TM `test_check_timeouts_response_accepts_empty_list`
- R43: [x] TM `test_error_response_rejects_invalid_values`
- R44: [x] TM `test_health_response_rejects_invalid_values`
- R45: [x] TP `test_constants_have_contract_values`
- R46: [x] TP `test_package_imports_only_stdlib_and_pydantic` (recorre los imports con `ast`), `test_package_has_the_expected_modules`
- R47: [x] TE `test_every_model_has_an_example`, `test_nested_models_are_covered_by_examples`
- R48: [x] TE `test_every_example_validates_against_its_model` (21 ejemplos, con `model_validate_json`)
- R49: [x] TE `test_every_example_file_is_mapped`
- R50: [x] TP `test_contracts_requirements_pins_pydantic_v2`
- R51: [x] TP `test_dev_requirements_include_contracts`
- R52: [x] TM `test_search_request_category_defaults_to_none`

Todos los tests llevan en su docstring el `R<n>` que cubren, como pide `docs/conventions.md` §Tests.

## Cobertura de `acceptance`

1. [x] `CONTRATOS.md` tiene las 8 rutas, y en cada una el servicio que la expone, quién la llama, los modelos, las tablas Request/Respuesta/Errores y el código de éxito.
2. [x] Reglas comunes: autenticación, errores, mensajes repetidos y salud (`contracts/CONTRATOS.md`, sección `## Reglas comunes`).
3. [x] El paquete `contracts/lazaro_contracts/` tiene 20 modelos Pydantic v2, entre ellos `ErrorResponse`.
4. [x] `contracts/examples/` tiene 21 JSON válidos y cubre todos los requests y responses.
5. [x] `contracts/tests/` valida cada ejemplo y comprueba que se rechaza un ejemplo al que le falta un campo obligatorio.
6. [x] `contracts/requirements.txt` contiene `pydantic>=2.12,<3`.
7. [x] Los supuestos S1 (multipart con `file` y `name`) y S2 (`last_messages`, máximo 10, `{role, text, at}`) están documentados y aplicados en `MAX_LAST_MESSAGES` y `LastMessage`.

## Tasks completas

- T1–T19: [x] (todas marcadas en `specs/contratos_servicios/tasks.md`)

## Conformidad con design / architecture / conventions

- Los archivos coinciden con la tabla de `design.md` §2. Solo se tocó `contracts/`, más una línea añadida al final de `requirements-dev.txt` (`git diff` confirma que las líneas que ya existían no cambiaron).
- Las firmas de `common.py`, `messages.py`, `search.py`, `manuals.py` y `cases.py` coinciden con el esbozo normativo de `design.md` §3: tipos, límites, `extra="forbid"`, `RootModel` para `SearchResponse` y `Identifier | None = None` para `category`.
- Los módulos siguen la convención: docstring de una línea, `from __future__ import annotations`, imports ordenados, comillas dobles y nada de sintaxis de 3.13+. Los comentarios solo enlazan con los supuestos `S<n>`, que es un por qué válido.
- `contracts/` no tiene `print()`, `eval`/`exec` ni TODOs.
- Los ejemplos usan datos ficticios (ids `111111111`, fechas `2026-10-30T19:0x:00Z`).
- Los `__pycache__/` generados están ignorados por `.gitignore`.

## Checkpoints

- C1: [x] Los archivos base y los docs existen, y `./init.sh` sale con exit 0.
- C2: [x] Solo la feature #1 está `in_progress`. Ninguna feature está `done`. `progress/current.md` describe la sesión activa.
- C3: [x] Solo se crearon archivos en `contracts/`, como prevé §1. Ningún servicio importa otro (aún no existen servicios). Las 8 rutas están en `CONTRATOS.md`. `pydantic` está acotado y declarado en `design.md` §8 (licencia MIT). No hay GPL/AGPL ni código copiado. No hay variables de entorno nuevas (justificado en design §9), y `.env` no está en git.
- C4: [x] Hay tests sin red ni base de datos: 273, todos verdes. Todavía no hay carpetas en `services/`, así que el punto de los tests por servicio no aplica.
- C5: [x] No hay archivos sin trackear sospechosos. La entrada de `progress/history.md` la escribe el leader al cerrar la sesión, después de esta revisión. El estado de la feature es correcto: `in_progress`, a la espera del cierre.
- C6: [x] `specs/contratos_servicios/` está completo, con EARS y supuestos S1–S10. Todas las tasks están `[x]` y todos los R1–R52 tienen test.

## Observaciones (no bloquean)

1. `.claude/settings.json` tiene cambios sin commitear: `defaultMode: dontAsk`, la lista `ask` pasa a `deny` y se añaden denegaciones de Edit sobre `docs/`, `CLAUDE.md`, `.claude/` y otros. Parece el cambio de modo nocturno que hace `modo.sh`/`nocturno.sh`, no algo del implementer, y `impl_contratos_servicios.md` no lo menciona. El humano debería confirmar que al volver al modo supervisado se restaura (`./modo.sh`) y que no se commitea junto con esta feature.
2. Más adelante (feature 2): decidir cómo llega `lazaro_contracts` a las imágenes Docker. Está documentado en design §1 y en la alternativa 5.

## Cambios requeridos

Ninguno.
