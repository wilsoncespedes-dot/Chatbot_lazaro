# Implementación — contratos_servicios (feature #1)

- **Estado:** ready_for_review (no marcada `done`).
- **Fecha:** 2026-10-30 (modo nocturno).
- **Tasks:** T1–T19 marcadas `[x]` en `specs/contratos_servicios/tasks.md`.
- **Verificación:** `.venv/Scripts/python.exe -m pytest contracts` → 273 passed;
  `./init.sh` → todo `[OK]`.
- **Dependencia instalada:** `.venv/Scripts/python.exe -m pip install -r contracts/requirements.txt`
  → pydantic 2.14.2 (+ pydantic-core, annotated-types, typing-inspection como
  dependencias transitivas). Nada más instalado.

## Archivos

Creados:
- `contracts/requirements.txt`
- `contracts/CONTRATOS.md`
- `contracts/lazaro_contracts/{__init__,common,messages,search,manuals,cases}.py`
- `contracts/examples/*.json` (21 archivos de `design.md` §6)
- `contracts/tests/{test_examples,test_models,test_contratos_doc,test_packaging}.py`

Modificados:
- `requirements-dev.txt` (añadida `-r contracts/requirements.txt`; líneas previas intactas)

No tocados: `services/`, `eval/`, `scripts/`, `docker-compose.yml`, `.github/`,
`contracts/.gitkeep`, `.env.example`.

## Notas para el reviewer

- `__all__` exporta los 20 modelos, las 6 constantes y además `ContractModel`,
  `Identifier`, `MessageText`, `HandoverReason` (permitido por `design.md` §3).
- En `CONTRATOS.md`, la excepción del webhook de Telegram dice que su protección
  la fija la feature del gateway (no se inventa mecanismo).
- Las filas de error por ruta incluyen también `500 internal_error` (de la tabla §4).
- Tests extra no pedidos explícitamente pero dentro de los R: aceptación de
  valores límite (4096, 64, 200, top_k 1/20, score ±1), rechazo de `category`
  inválida (R22/S7), rechazo de `{"results": [...]}` en `SearchResponse` (R29).
- `contracts/tests/` sin `__init__.py`: con `--import-mode=importlib` no hace falta;
  cada archivo de test define sus propios helpers (no se importan entre sí).

## Trazabilidad R → test

Archivos: `TE` = `contracts/tests/test_examples.py`, `TM` = `test_models.py`,
`TD` = `test_contratos_doc.py`, `TP` = `test_packaging.py`.

| R | Test(s) |
|---|---------|
| R1 | TD `test_doc_has_a_section_per_route` |
| R2 | TD `test_route_names_exposing_service` |
| R3 | TD `test_route_names_caller` |
| R4 | TD `test_route_names_models_in_package` |
| R5 | TD `test_request_table_lists_every_request_field`, `test_manuals_request_table_lists_multipart_parts`, `test_check_timeouts_request_table_has_no_fields_row` |
| R6 | TD `test_response_section_has_success_code_and_fields` |
| R7 | TD `test_errors_table_has_common_rows` |
| R8 | TD `test_errors_table_has_route_specific_rows` |
| R9 | TD `test_common_rules_document_service_token` |
| R10 | TD `test_common_rules_document_error_shape_and_codes` |
| R11 | TD `test_common_rules_document_duplicate_messages` |
| R12 | TD `test_common_rules_document_health` |
| R13 | TD `test_assumptions_include_manuals_multipart` |
| R14 | TD `test_assumptions_include_last_messages` |
| R15 | TD `test_assumptions_mention_s1_to_s10` |
| R16 | TP `test_model_is_exported_and_is_base_model`, `test_all_names_are_importable` |
| R17 | TP `test_pydantic_major_version_is_2`, `test_model_is_exported_and_is_base_model` |
| R18 | TM `test_unexpected_field_is_rejected`, `test_unexpected_field_inside_search_response_element_is_rejected` |
| R19 | TM `test_missing_required_field_is_rejected`, `test_every_model_has_a_required_field_case_except_check_timeouts_request` |
| R20 | TM `test_datetime_without_timezone_is_rejected` |
| R21 | TM `test_invalid_text_is_rejected`, `test_text_at_max_length_is_accepted` |
| R22 | TM `test_invalid_identifier_is_rejected`, `test_invalid_timed_out_case_identifier_is_rejected`, `test_invalid_search_category_identifier_is_rejected` |
| R23 | TM `test_message_request_requires_its_fields`, `test_message_request_rejects_negative_update_id`, `test_message_request_rejects_non_integer_ids` |
| R24 | TM `test_message_response_accepts_valid_status`, `test_message_response_rejects_invalid_status` |
| R25 | TM `test_send_request_requires_chat_id_and_text` |
| R26 | TM `test_sent_must_be_true` |
| R27 | TM `test_search_request_requires_query_and_top_k` |
| R28 | TM `test_search_request_rejects_top_k_out_of_range`, `test_search_request_accepts_top_k_limits` |
| R29 | TM `test_search_response_accepts_empty_list`, `test_search_response_accepts_results`, `test_search_response_rejects_object_body` |
| R30 | TM `test_search_result_rejects_score_out_of_range`, `test_search_result_accepts_score_limits` |
| R31 | TM `test_handover_request_requires_its_fields` |
| R32 | TM `test_handover_request_accepts_valid_reason`, `test_handover_request_rejects_invalid_reason` |
| R33 | TM `test_handover_request_rejects_too_many_last_messages` |
| R34 | TM `test_last_message_accepts_valid_role`, `test_last_message_rejects_invalid_role` |
| R35 | TM `test_handover_response_accepts_valid_status`, `test_handover_response_requires_status_and_case_id` |
| R36 | TM `test_case_reply_request_requires_advisor_id_and_text` |
| R37 | TM `test_manual_upload_request_rejects_invalid_name` |
| R38 | TM `test_manual_upload_response_rejects_zero_chunks` |
| R39 | TM `test_case_close_request_requires_advisor_id` |
| R40 | TM `test_case_close_response_rejects_invalid_status` |
| R41 | TM `test_check_timeouts_request_accepts_empty_object` |
| R42 | TM `test_check_timeouts_response_accepts_empty_list` |
| R43 | TM `test_error_response_rejects_invalid_values` |
| R44 | TM `test_health_response_rejects_invalid_values` |
| R45 | TP `test_constants_have_contract_values` |
| R46 | TP `test_package_imports_only_stdlib_and_pydantic`, `test_package_has_the_expected_modules` |
| R47 | TE `test_every_model_has_an_example`, `test_nested_models_are_covered_by_examples` |
| R48 | TE `test_every_example_validates_against_its_model` |
| R49 | TE `test_every_example_file_is_mapped` |
| R50 | TP `test_contracts_requirements_pins_pydantic_v2` |
| R51 | TP `test_dev_requirements_include_contracts` |
| R52 | TM `test_search_request_category_defaults_to_none` |
