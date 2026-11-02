# Review — feature #13 contrato_autorizacion_asesores

**Veredicto:** APPROVED

Revisado en modo supervisado el 2026-10-31. Código escrito por OpenCode/DeepSeek.

## Verificación ejecutada

- `.venv/Scripts/python -m pytest contracts`: **374 passed**, 0 failed.
- `./init.sh`: exit 0, **742 passed** (1 warning de deprecación de Starlette, ajeno).
  El paso 4 da OK: ahora solo hay una feature `in_progress` (el FAIL de «2 features
  in_progress» que cita `progress/impl_contrato_autorizacion_asesores.md` ya lo
  resolvió el leader).
- `git diff -U0 -- contracts/ | grep -E '^-[^-]'` devuelve exactamente 3 líneas:
  1. `cases.py:2`, la 2.ª línea de la docstring de módulo (autorizada en design §1 y §3).
  2. `CONTRATOS.md`, la fila común `409 | case_closed` «antes» de E1. Es literal a
     design §1.1 y la línea «después» (`CONTRATOS.md:44`) coincide carácter a carácter.
  3. `CONTRATOS.md`, la fila `S11` «antes» de E2. Es literal y la «después»
     (`CONTRATOS.md:435`) coincide exactamente con design §1.1.
- No se ha editado la prosa de `### POST /cases/{id}/assign` (`CONTRATOS.md:346-349`,
  sigue diciendo «responde igual, `200` …»). Tampoco el «Cuándo» de la fila 409
  («el caso está cerrado (S11)»). Se mantiene la decisión por defecto de design §7, duda 1.
- `git diff --name-only -- 'contracts/examples/*.json'`: vacío. Se crearon dos JSON
  nuevos con los valores de design §2.
- `git diff --stat -- services/ eval/ scripts/ docker-compose.yml .github/`: vacío.
  Nada fuera de `contracts/` cambió por esta feature.
- Secretos: el diff de `contracts/` solo nombra `SERVICE_TOKEN` y `X-Service-Token`
  como texto de documentación, sin valores. `.env` no está trackeado.

## Tests existentes (no debilitados)

`git diff contracts/tests/` solo contiene líneas `+`:
- `test_contratos_doc.py`: entradas nuevas en `ROUTES` (l.24), `OWN_ERRORS` (l.33-37,
  sin editar las entradas existentes de reply/close/assign) y `SUCCESS_CODES` (l.50).
  También `("403", "forbidden")` añadido a `expected` (l.206). Los tests nuevos van a
  partir de l.324.
- `test_examples.py`, `test_models.py` y `test_packaging.py`: solo imports, entradas de
  dicts/listas y tests nuevos. `from typing import Any` sigue intacto y `get_args` va en
  una línea aparte (`test_models.py:8`).
- Los tests de design §5.1 (`test_assumptions_include_assign_idempotency`,
  `test_common_rules_case_closed_row_cites_assign`, `test_assign_section_documents_s11`,
  `test_assumptions_mention_s1_to_s10`, etc.) no cambian de código y pasan.

## Trazabilidad requirements ↔ tests

Todos los tests existen y pasan (56 tests nuevos o parametrizados de la #13 en PASSED).
- R1: [x] `test_doc_has_a_section_per_route` (ROUTES ampliado)
- R2: [x] `test_route_names_exposing_service[POST /cases/{id}/authorize]`
- R3: [x] `test_authorize_route_is_called_by_orchestrator` y `test_route_names_caller[…]`
- R4: [x] `test_route_names_models_in_package[…]`
- R5: [x] `test_request_table_lists_every_request_field[…]`
- R6: [x] `test_authorize_action_row_lists_reply_and_close`
- R7: [x] `test_response_section_has_success_code_and_fields[…]`
- R8: [x] `test_errors_table_has_common_rows[…]`
- R9: [x] `test_errors_table_has_route_specific_rows[…]`
- R10: [x] `test_authorize_errors_table_has_internal_error`
- R11: [x] `test_authorize_section_documents_path_id`
- R12: [x] `test_authorize_section_documents_allowed_true_or_forbidden`
- R13: [x] `test_authorize_section_documents_closed_case`
- R14: [x] `test_common_rules_document_error_shape_and_codes` y `test_common_rules_forbidden_row_cites_case_routes`
- R15-R17: [x] `test_existing_case_routes_document_forbidden[reply|close|assign]`
- R18: [x] `test_existing_case_routes_keep_their_error_rows` (inclusión `<=`, como pide T21) y el diff de T39
- R19: [x] `test_assumptions_s12_defines_who_is_advisor`
- R20: [x] `test_assumptions_s12_reply_rules`
- R21: [x] `test_assumptions_s12_close_rules`
- R22: [x] `test_assumptions_s12_no_reassignment_nor_supervisor`
- R23: [x] `test_assumptions_s12_fails_closed`
- R24: [x] `test_assumptions_s12_applies_to_existing_routes`
- R25: [x] `test_assumptions_s12_identity_limitation`
- R26: [x] `test_assumptions_s12_limits_s11_to_assigned_advisor`
- R27: [x] `test_case_authorize_action_is_reply_or_close`
- R28: [x] `test_case_authorize_request_requires_advisor_id_and_action` y `test_case_authorize_request_accepts_valid_action`
- R29: [x] `test_case_authorize_request_without_advisor_id_is_rejected` y `test_missing_required_field_is_rejected[CaseAuthorizeRequest.advisor_id]`
- R30: [x] `test_case_authorize_request_without_action_is_rejected` y `…[CaseAuthorizeRequest.action]`
- R31: [x] `test_case_authorize_request_rejects_invalid_action` (assign, REPLY, read, "")
- R32: [x] `test_invalid_identifier_is_rejected[…CaseAuthorizeRequest.advisor_id]`
- R33: [x] `test_case_authorize_response_requires_allowed_and_case_id`
- R34: [x] `test_case_authorize_response_rejects_allowed_not_true` (False, None, "false", 0)
- R35: [x] `test_invalid_identifier_is_rejected[…CaseAuthorizeResponse.case_id]`
- R36: [x] `test_unexpected_field_is_rejected[CaseAuthorizeRequest|CaseAuthorizeResponse]`
- R37: [x] `test_model_is_exported_and_is_base_model[…]` y `test_case_authorize_action_is_exported`
- R38: [x] `test_every_example_validates_against_its_model[case_authorize_request.json]`
- R39: [x] `…[case_authorize_response.json]`
- R40: [x] `test_every_example_file_is_mapped` y `test_every_model_has_an_example`
- R41: [x] la batería previa intacta (incluido `test_assumptions_include_assign_idempotency`) y el diff de T39
- R42: [x] la batería completa en verde (742) y el diff de T39
- R43: [x] `test_assumptions_s12_error_precedence`
- R44: [x] `test_assumptions_s12_close_on_closed_keeps_s8`
- R45: [x] `test_assumptions_s12_fail_closed_reuses_reply_502`
- R46: [x] `test_assumptions_s12_reply_on_closed_is_case_closed`
- R47: [x] `test_assumptions_s12_reply_authorizes_before_case_lookup`
- R48: [x] `test_reply_errors_table_has_case_closed`
- R49: [x] `test_common_rules_case_closed_row_cites_reply` y el diff de T39
- R50: [x] `test_assumptions_s11_other_advisor_gets_forbidden` y el diff de T39
- R51: [x] `test_assumptions_s12_documents_s11_change`
- R52: [x] T39, comprobado por mí con el diff (3 líneas eliminadas, todas autorizadas)
- R53: [x] `test_authorize_route_caller_mentions_cerrar_command`

## Tasks completas

- T1-T53: [x] (0 casillas `[ ]` en `specs/contrato_autorizacion_asesores/tasks.md`).
  Contrasté T1-T12, T46-T48 y T39 con el diff real.

## Checkpoints

- C1: [x] el arnés está completo e `init.sh` sale con exit 0.
- C2: [x] una sola feature `in_progress`; `progress/current.md` describe la sesión.
- C3: [x] solo cambia `contracts/`; no hay dependencias nuevas, secretos, `print`, `eval` ni TODOs. La ruta nueva está en `CONTRATOS.md`.
- C4: [x] los tests corren sin red ni BD y todo está en verde.
- C5: [x] no hay archivos temporales sospechosos. (Las entradas de history son del cierre del leader.)
- C6: [x] el spec está completo, R1-R53 cubiertos y T1-T53 en `[x]`.

## Observaciones no bloqueantes (no requieren cambios)

1. `contracts/lazaro_contracts/cases.py:1-2`: la docstring queda
   `…/cases/check-timeouts` + salto de línea + `/cases/{id}/assign y /cases/{id}/authorize.`,
   sin la coma que muestra design §3 al final de la 1.ª línea. Es cosmético. Añadirla
   obligaría a eliminar una línea más de la que T39 permite, así que es correcto dejarla así.
2. `contracts/CONTRATOS.md:436` (S12): el final se aparta de la redacción de design §4.4.
   Pone «responde `502` con `upstream_error` (la fila … de `POST /cases/{id}/reply`)» y
   no «… ; es la fila … cuyo texto no se edita». Además quita «Limitación:» y escribe
   «llega con la #16 (remitente del webhook validado)». Design §4 (l.242-244) permite
   variar la redacción y R23, R25 y R45 se cumplen literalmente. La mención a la #16 es
   coherente con D4 de la #16.
3. `contracts/tests/test_models.py:7-8`: hay dos líneas `from typing import …`. Es
   deliberado para no eliminar líneas (T39). Es aceptable.
4. Según el informe del implementer, al empezar `cases.py` ya tenía cambios «de un
   proceso concurrente». He revisado el diff final completo de `cases.py` y solo contiene
   lo que pide el spec.

## Cambios requeridos

Ninguno.
