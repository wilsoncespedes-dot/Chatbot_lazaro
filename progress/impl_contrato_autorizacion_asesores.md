# Implementación — contrato_autorizacion_asesores (feature #13)

## Resumen

Implementada la feature completa dentro de `contracts/`:

- `lazaro_contracts/cases.py`: `CaseAuthorizeAction`, `CaseAuthorizeRequest`,
  `CaseAuthorizeResponse` y docstring de módulo ampliada.
- `lazaro_contracts/__init__.py`: los tres nombres exportados en `__all__`.
- `examples/`: `case_authorize_request.json` y `case_authorize_response.json`.
- `CONTRATOS.md`: ruta `### POST /cases/{id}/authorize`, fila común `403 forbidden`,
  filas `403` en reply/close/assign, fila `409 case_closed` en reply, supuesto `S12`
  y las dos excepciones cerradas E1 (Dónde de la fila común `409`) y E2 (fila `S11`).
- Tests de contrato: entradas nuevas en `ROUTES`, `OWN_ERRORS`, `SUCCESS_CODES`,
  `EXAMPLES`, `MODEL_NAMES`, `BASE_EXAMPLES` e `IDENTIFIER_FIELDS`, y los tests
  nuevos T13-T38 y T41-T53.

No se ha tocado `feature_list.json`, `progress/current.md`, `progress/history.md`
ni el harness. La feature no se marca `done`.

## Trazabilidad

- R1 → `contracts/tests/test_contratos_doc.py::test_doc_has_a_section_per_route[POST /cases/{id}/authorize]`
- R2 → `test_route_names_exposing_service[POST /cases/{id}/authorize]`
- R3 → `test_route_names_caller[POST /cases/{id}/authorize]`, `test_authorize_route_is_called_by_orchestrator`
- R4 → `test_route_names_models_in_package[POST /cases/{id}/authorize]`
- R5 → `test_request_table_lists_every_request_field[POST /cases/{id}/authorize]`
- R6 → `test_authorize_action_row_lists_reply_and_close`
- R7 → `test_response_section_has_success_code_and_fields[POST /cases/{id}/authorize]`
- R8 → `test_errors_table_has_common_rows[POST /cases/{id}/authorize]`
- R9 → `test_errors_table_has_route_specific_rows[POST /cases/{id}/authorize]`
- R10 → `test_authorize_errors_table_has_internal_error`
- R11 → `test_authorize_section_documents_path_id`
- R12 → `test_authorize_section_documents_allowed_true_or_forbidden`
- R13 → `test_authorize_section_documents_closed_case`
- R14 → `test_common_rules_document_error_shape_and_codes`, `test_common_rules_forbidden_row_cites_case_routes`
- R15 → `test_existing_case_routes_document_forbidden[POST /cases/{id}/reply]`
- R16 → `test_existing_case_routes_document_forbidden[POST /cases/{id}/close]`
- R17 → `test_existing_case_routes_document_forbidden[POST /cases/{id}/assign]`
- R18 → `test_existing_case_routes_keep_their_error_rows` (3 rutas) + T39
- R19 → `test_assumptions_s12_defines_who_is_advisor`
- R20 → `test_assumptions_s12_reply_rules`
- R21 → `test_assumptions_s12_close_rules`
- R22 → `test_assumptions_s12_no_reassignment_nor_supervisor`
- R23 → `test_assumptions_s12_fails_closed`
- R24 → `test_assumptions_s12_applies_to_existing_routes`
- R25 → `test_assumptions_s12_identity_limitation`
- R26 → `test_assumptions_s12_limits_s11_to_assigned_advisor`
- R27 → `contracts/tests/test_models.py::test_case_authorize_action_is_reply_or_close`
- R28 → `test_case_authorize_request_requires_advisor_id_and_action`, `test_case_authorize_request_accepts_valid_action`
- R29 → `test_case_authorize_request_without_advisor_id_is_rejected`, `test_missing_required_field_is_rejected[CaseAuthorizeRequest.advisor_id]`
- R30 → `test_case_authorize_request_without_action_is_rejected`, `test_missing_required_field_is_rejected[CaseAuthorizeRequest.action]`
- R31 → `test_case_authorize_request_accepts_valid_action`, `test_case_authorize_request_rejects_invalid_action`
- R32 → `test_invalid_identifier_is_rejected[CaseAuthorizeRequest.advisor_id-empty]`, `[CaseAuthorizeRequest.advisor_id-too_long]`
- R33 → `test_case_authorize_response_requires_allowed_and_case_id`, `test_missing_required_field_is_rejected[CaseAuthorizeResponse.allowed]`, `[CaseAuthorizeResponse.case_id]`
- R34 → `test_case_authorize_response_rejects_allowed_not_true`
- R35 → `test_invalid_identifier_is_rejected[CaseAuthorizeResponse.case_id-empty]`, `[CaseAuthorizeResponse.case_id-too_long]`
- R36 → `test_unexpected_field_is_rejected[CaseAuthorizeRequest]`, `[CaseAuthorizeResponse]`
- R37 → `contracts/tests/test_packaging.py::test_model_is_exported_and_is_base_model[CaseAuthorizeRequest]`, `[CaseAuthorizeResponse]`, `test_case_authorize_action_is_exported`
- R38 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[case_authorize_request.json]`
- R39 → `test_every_example_validates_against_its_model[case_authorize_response.json]`
- R40 → `test_every_example_file_is_mapped`, `test_every_model_has_an_example`
- R41 → batería previa intacta (tests existentes sin cambios de código ni aserciones) + T39
- R42 → batería completa de tests + T39
- R43 → `test_assumptions_s12_error_precedence`
- R44 → `test_assumptions_s12_close_on_closed_keeps_s8`
- R45 → `test_assumptions_s12_fail_closed_reuses_reply_502`
- R46 → `test_assumptions_s12_reply_on_closed_is_case_closed`
- R47 → `test_assumptions_s12_reply_authorizes_before_case_lookup`
- R48 → `test_reply_errors_table_has_case_closed`
- R49 → `test_common_rules_case_closed_row_cites_reply` + T39
- R50 → `test_assumptions_s11_other_advisor_gets_forbidden` + T39
- R51 → `test_assumptions_s12_documents_s11_change`
- R52 → T39
- R53 → `test_authorize_route_caller_mentions_cerrar_command` (+ T13 para R3)

## Corrección aplicada (verificación T39, intento 1)

`git diff -U0 -- contracts/ | grep -E '^-[^-]'` mostraba una línea eliminada no
permitida por T39: en `contracts/tests/test_models.py` la línea existente
`from typing import Any` se había sustituido por `from typing import Any, get_args`.

Corregido en esta sesión: `from typing import Any` vuelve a estar sin cambios y
`from typing import get_args` se añade en una línea nueva aparte. Así las únicas
líneas eliminadas en `contracts/` quedan: (1) la segunda línea de la docstring de
`cases.py` y (2) las dos líneas «antes» de E1/E2 en `CONTRATOS.md`. No se cambió
nada más.

## Verificación (Claude, implementer puente, 2026-10-31)

- Escritor: OpenCode con `deepseek/deepseek-v4-pro`; la autenticación funcionó.
  Dos ejecuciones: implementación y corrección del import (intento 1 de 3).
- `./init.sh`: **742 passed, 1 warning** (deprecación de Starlette). Antes eran 674.
  El paso 4 de `init.sh` marca FAIL: «Hay 2 features en in_progress (máximo 1)»:
  #13 y #14 `autorizacion_asesores` están `in_progress` en `feature_list.json`.
  OpenCode no lo causó (no tocó `feature_list.json`); lo resuelve el leader.
- T39: `git diff -U0 -- contracts/ | grep -E '^-[^-]'` solo muestra 3 líneas
  eliminadas: la 2.ª línea de la docstring de `cases.py`, la fila común
  `409 | case_closed` antigua (E1) y la fila `S11` antigua (E2). Las líneas
  «después» de E1/E2 están en el diff. `git diff --name-only -- 'contracts/examples/*.json'`
  vacío. Sin cambios en `services/`.
- tasks.md: T1-T53 marcadas `[x]` (T39 la marcó Claude tras verificar).
- Trazabilidad: todas las funciones de test citadas arriba existen en `contracts/tests/`.
- Design §7 (prosa de assign y «Cuándo» de la fila 409) no se editó.
- Observación para el reviewer: OpenCode dijo al empezar que `cases.py` ya estaba
  modificado «por un proceso concurrente». Parece que otra sesión dejó cambios
  previos sin confirmar; el resultado final cumple el spec, pero conviene revisarlo.
- La feature sigue `in_progress`; no se marca `done`.
