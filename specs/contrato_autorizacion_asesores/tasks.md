# Tasks — contrato_autorizacion_asesores (feature #13)

> Orden pensado para que cada paso sea verificable. Solo se toca `contracts/`
> (ver `design.md` §1). Cambio aditivo con dos excepciones cerradas en `CONTRATOS.md`
> (E1: «Dónde» de la fila común `409 | case_closed`; E2: fila `S11`; antes/después en
> `design.md` §1.1). En los tests existentes solo se añaden entradas a
> dicts/listas/conjuntos; no se borra ni relaja ninguna aserción, y las entradas
> existentes de `OWN_ERRORS` no se editan (los tests existentes que leen E1/E2 siguen
> sin cambios: `design.md` §5.1).
> Ids nuevos al final sin renumerar: T41-T45 (tercera vuelta) y T46-T53 (decisiones del
> humano 2026-10-31).
> Cada test nuevo lleva en su docstring el `R<n>` que cubre con el prefijo
> `contrato_autorizacion_asesores` (p. ej.
> `"""contrato_autorizacion_asesores R31: ..."""`).

## Modelos

- [x] T1 — Añadir `CaseAuthorizeAction`, `CaseAuthorizeRequest` y `CaseAuthorizeResponse` en `contracts/lazaro_contracts/cases.py` tras `CaseAssignResponse`, según `design.md` §3; ampliar la docstring de módulo con `/cases/{id}/authorize`. Cubre: R27, R28, R32, R33, R35, R36.
- [x] T2 — Importar los tres nombres en `contracts/lazaro_contracts/__init__.py`; añadir `"CaseAuthorizeRequest"`, `"CaseAuthorizeResponse"` a `__all__` tras `"CaseAssignResponse"` y `"CaseAuthorizeAction"` tras `"HandoverReason"`. Cubre: R37.

## Ejemplos

- [x] T3 — Crear `contracts/examples/case_authorize_request.json` y `contracts/examples/case_authorize_response.json` (UTF-8, 2 espacios, valores de `design.md` §2). Cubre: R38, R39.

## Documento

- [x] T4 — Añadir en `contracts/CONTRATOS.md` la sección `### POST /cases/{id}/authorize` al final de `## Rutas` (tras `### POST /cases/{id}/assign`), con el texto de `design.md` §4.1 (la línea `- **Llama:**` incluye el comando `/cerrar` antes de `POST /cases/{id}/close`). Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R53.
- [x] T5 — En la tabla de errores de `## Reglas comunes`, añadir la fila `403 | forbidden` de `design.md` §4.2 entre la `422 | validation_error` y la `404 | not_found`. Ninguna fila existente se edita en esta task (la «Dónde» de la `409` la cambia T47). Cubre: R14, R18.
- [x] T6 — Añadir la fila `403 | forbidden` (texto de `design.md` §4.3) tras la fila `422` de los `#### Errores` de `### POST /cases/{id}/reply`, `### POST /cases/{id}/close` y `### POST /cases/{id}/assign`. Ninguna línea existente se edita (tampoco las líneas `- **Llama:**`). Cubre: R15, R16, R17, R18.
- [x] T7 — Añadir la fila `S12` de `design.md` §4.4 al final de la tabla de `## Supuestos a confirmar` (incluye la precedencia de errores, close sobre `closed` → S8, reply sobre `closed` → `409 case_closed`, la referencia a la fila `502` de reply y el cambio frente al `200` de S11 de la #9). Cubre: R19, R20, R21, R22, R23, R24, R25, R26, R43, R44, R45, R46, R47, R51.
- [x] T46 — Añadir en los `#### Errores` de `### POST /cases/{id}/reply`, tras la fila `404 | not_found`, la fila nueva `| 409 | case_closed | el caso está cerrado; no se envía nada al cliente (S12) |` (`design.md` §4.3). Cubre: R48, R18.
- [x] T47 — Excepción E1: en la fila `409 | case_closed` de `## Reglas comunes`, sustituir solo la «Dónde» por `` `/cases/{id}/assign`, `/cases/{id}/reply` `` (línea «después» exacta de `design.md` §1.1; el «Cuándo» no cambia). Ninguna otra fila común se edita. Cubre: R49, R18, R52.
- [x] T48 — Excepción E2: sustituir la fila `S11` por la línea «después» exacta de `design.md` §1.1. Ningún otro supuesto ni la prosa de `### POST /cases/{id}/assign` se edita. Cubre: R50, R41, R52.

## Tests — ampliación de los existentes

- [x] T8 — `contracts/tests/test_contratos_doc.py`: añadir `"POST /cases/{id}/authorize": "handover"` a `ROUTES`, `"POST /cases/{id}/authorize": "200"` a `SUCCESS_CODES` y `"POST /cases/{id}/authorize": [("403", "forbidden"), ("404", "not_found"), ("409", "case_closed")]` a `OWN_ERRORS`. Así `test_doc_has_a_section_per_route` (R1), `test_route_names_exposing_service[POST /cases/{id}/authorize]` (R2), `test_route_names_models_in_package[…]` (R4), `test_request_table_lists_every_request_field[…]` (R5), `test_response_section_has_success_code_and_fields[…]` (R7), `test_errors_table_has_common_rows[…]` (R8) y `test_errors_table_has_route_specific_rows[…]` (R9) cubren la ruta nueva. Cubre: R1, R2, R4, R5, R7, R8, R9.
- [x] T9 — En el mismo archivo, añadir `("403", "forbidden")` al conjunto `expected` de `test_common_rules_document_error_shape_and_codes`. Cubre: R14.
- [x] T10 — `contracts/tests/test_examples.py`: importar los dos modelos; añadir `"case_authorize_request.json": CaseAuthorizeRequest` y `"case_authorize_response.json": CaseAuthorizeResponse` a `EXAMPLES`, y `"CaseAuthorizeRequest"`, `"CaseAuthorizeResponse"` a `MODEL_NAMES`. Así `test_every_example_validates_against_its_model[case_authorize_request.json]` (R38), `…[case_authorize_response.json]` (R39), `test_every_example_file_is_mapped` y `test_every_model_has_an_example` (R40) los cubren. Cubre: R38, R39, R40.
- [x] T11 — `contracts/tests/test_models.py`: importar `CaseAuthorizeRequest`, `CaseAuthorizeResponse` y `CaseAuthorizeAction`; añadir a `BASE_EXAMPLES` `CaseAuthorizeRequest: ("case_authorize_request.json", None)` y `CaseAuthorizeResponse: ("case_authorize_response.json", None)`; añadir a `IDENTIFIER_FIELDS` `(CaseAuthorizeRequest, "advisor_id")` y `(CaseAuthorizeResponse, "case_id")`. Así `test_missing_required_field_is_rejected[CaseAuthorizeRequest.advisor_id]` (R29), `[CaseAuthorizeRequest.action]` (R30), `test_unexpected_field_is_rejected[CaseAuthorizeRequest]` y `[CaseAuthorizeResponse]` (R36), `test_invalid_identifier_is_rejected[…-CaseAuthorizeRequest.advisor_id]` (R32) y `[…-CaseAuthorizeResponse.case_id]` (R35) los cubren. Cubre: R29, R30, R32, R35, R36.
- [x] T12 — `contracts/tests/test_packaging.py`: añadir `"CaseAuthorizeRequest"` y `"CaseAuthorizeResponse"` a `MODEL_NAMES`, de modo que `test_model_is_exported_and_is_base_model[CaseAuthorizeRequest]` y `[CaseAuthorizeResponse]` los cubran. Cubre: R37.

## Tests — nuevos

En `contracts/tests/test_contratos_doc.py` (con `AUTHORIZE_ROUTE = "POST /cases/{id}/authorize"`):

- [x] T13 — `test_authorize_route_is_called_by_orchestrator`: la línea `- **Llama:**` de la ruta contiene `orchestrator`. Cubre: R3.
- [x] T14 — `test_authorize_action_row_lists_reply_and_close`: la fila `` | `action` | `` de la tabla `#### Request` contiene `` `reply` `` y `` `close` ``. Cubre: R6.
- [x] T15 — `test_authorize_errors_table_has_internal_error`: la tabla `#### Errores` de la ruta contiene `("500", "internal_error")`. Cubre: R10.
- [x] T16 — `test_authorize_section_documents_path_id`: la sección contiene `` `{id}` es el `case_id` (identificador, 1–64 caracteres) ``. Cubre: R11.
- [x] T17 — `test_authorize_section_documents_allowed_true_or_forbidden`: la sección contiene `` `200` ``, `` `allowed` = `true` ``, `` `403` ``, `` `forbidden` ``, `` `allowed` = `false` `` y `S12`. Cubre: R12.
- [x] T18 — `test_authorize_section_documents_closed_case`: la sección contiene `` `closed` ``, `` `409` `` y `` `case_closed` ``. Cubre: R13.
- [x] T19 — `test_common_rules_forbidden_row_cites_case_routes`: la fila `403 | forbidden` de la tabla de `## Reglas comunes` contiene `/cases/{id}/authorize`, `/cases/{id}/reply`, `/cases/{id}/close` y `/cases/{id}/assign`. Cubre: R14.
- [x] T20 — `test_existing_case_routes_document_forbidden`, parametrizado con `POST /cases/{id}/reply`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `("403", "forbidden")` está en las filas de su tabla `#### Errores`. Cubre: R15, R16, R17.
- [x] T21 — `test_existing_case_routes_keep_their_error_rows`, parametrizado con las mismas tres rutas: las filas previas más `("403", "forbidden")` están incluidas en las filas de `#### Errores` (`previas | {("403", "forbidden")} <= filas`, NO igualdad exacta: otra feature de contrato puede añadir filas sin editar este test). Previas: reply: 401, 422, 404, 502, 500; close: 401, 422, 404, 500; assign: 401, 422, 404, 409, 500. Cubre: R18.
- [x] T22 — `test_assumptions_s12_defines_who_is_advisor`: `_assumption_row("S12")` contiene `` `POST /cases/{id}/authorize` ``, `` `ADVISOR_CHAT_IDS` ``, `` `403` `` y `` `forbidden` ``. Cubre: R19.
- [x] T23 — `test_assumptions_s12_reply_rules`: la fila S12 contiene `` `reply` ``, `` `open` ``, `` `timed_out` ``, «la primera respuesta lo asigna», `` `assigned` `` y «solo lo responde el asesor asignado». Cubre: R20.
- [x] T24 — `test_assumptions_s12_close_rules`: la fila S12 contiene `` `close` ``, «lo cierra cualquier asesor registrado» y «solo lo cierra el asesor asignado». Cubre: R21.
- [x] T25 — `test_assumptions_s12_no_reassignment_nor_supervisor`: la fila S12 contiene «Sin reasignación» y «supervisor». Cubre: R22.
- [x] T26 — `test_assumptions_s12_fails_closed`: la fila S12 contiene «falla cerrado», «no envía», `` `502` `` y `` `upstream_error` ``. Cubre: R23.
- [x] T27 — `test_assumptions_s12_applies_to_existing_routes`: la fila S12 contiene `` `POST /cases/{id}/reply` ``, «sin enviar nada al cliente», `` `POST /cases/{id}/close` ``, `` `POST /cases/{id}/assign` `` y «sin modificar el caso». Cubre: R24.
- [x] T28 — `test_assumptions_s12_identity_limitation`: la fila S12 contiene `` `SERVICE_TOKEN` ``, «suplante» y `` `advisor_id` ``. Cubre: R25.
- [x] T29 — `test_assumptions_s12_limits_s11_to_assigned_advisor`: la fila S12 contiene «(S11)», «al asesor asignado» y «otro asesor recibe `403`». Cubre: R26.

Tests de las decisiones C1, C2, C3, C5 y C6 de `design.md` §7 (decidido por el humano 2026-10-31; T44 reescrita por C5). Ids T41-T45 para no renumerar T30-T40:

- [x] T41 — `test_assumptions_s12_error_precedence`: la fila S12 contiene «Precedencia de errores», `` `POST /cases/{id}/authorize` ``, `` `POST /cases/{id}/close` ``, `` `POST /cases/{id}/assign` `` y «`403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor)». Cubre: R43.
- [x] T42 — `test_assumptions_s12_close_on_closed_keeps_s8`: la fila S12 contiene «`POST /cases/{id}/close` sobre un caso `closed` sigue S8», «`200` sin cambios para cualquier asesor registrado» y «`action` = `close` sobre un caso `closed` responde `409`». Cubre: R44.
- [x] T43 — `test_assumptions_s12_fail_closed_reuses_reply_502`: la fila S12 contiene «la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`», y `("502", "upstream_error")` sigue en las filas de `#### Errores` de `POST /cases/{id}/reply`. Cubre: R45.
- [x] T44 — `test_assumptions_s12_reply_on_closed_is_case_closed` (reescrita 2026-10-31, C5): la fila S12 contiene «`POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente» y «el orquestador propaga el `409` de `authorize`». Cubre: R46.
- [x] T45 — `test_assumptions_s12_reply_authorizes_before_case_lookup` (decisión C6): la fila S12 contiene «En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe» y «un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista». Cubre: R47.

Tests de las decisiones del humano del 2026-10-31 (C5, (d)/R26, D4 de la #16). Ids T49-T53:

- [x] T49 — `test_reply_errors_table_has_case_closed`: `("409", "case_closed")` está en `_error_rows(_subsection("POST /cases/{id}/reply", "Errores"))`. La entrada de `OWN_ERRORS` de reply NO se edita. Cubre: R48.
- [x] T50 — `test_common_rules_case_closed_row_cites_reply`: con el mismo regex que `test_common_rules_case_closed_row_cites_assign` (`^\| 409\s+\| `case_closed`\s+\|(.*)$` sobre `## Reglas comunes`), la columna capturada contiene `/cases/{id}/reply` y `/cases/{id}/assign`. Comprueba inclusión, no la línea entera. Cubre: R49.
- [x] T51 — `test_assumptions_s11_other_advisor_gets_forbidden`: `_assumption_row("S11")` contiene «sin cambiar el asesor asignado cuando quien asigna es el asesor asignado», «si es otro asesor, responde `403` con `error` = `forbidden`» y «(S12, cambio de la #13)». No sustituye a `test_assumptions_include_assign_idempotency` (#9), que se mantiene sin cambios. Cubre: R50.
- [x] T52 — `test_assumptions_s12_documents_s11_change`: la fila S12 contiene «Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor» y «el asesor asignado sigue recibiendo `200` sin cambios». Cubre: R51.
- [x] T53 — `test_authorize_route_caller_mentions_cerrar_command`: la línea `- **Llama:**` de `AUTHORIZE_ROUTE` contiene `` `/cerrar` `` y `` `POST /cases/{id}/close` ``. Cubre: R53.

En `contracts/tests/test_models.py`:

- [x] T30 — `test_case_authorize_action_is_reply_or_close`: `typing.get_args(CaseAuthorizeAction) == ("reply", "close")`. Cubre: R27.
- [x] T31 — `test_case_authorize_request_requires_advisor_id_and_action`: es subclase de `ContractModel`, sus campos obligatorios son exactamente `{"advisor_id", "action"}` y el ejemplo valida. Cubre: R28.
- [x] T32 — `test_case_authorize_request_without_advisor_id_is_rejected`: `_validate(CaseAuthorizeRequest, {"action": "reply"})` lanza `ValidationError`. Cubre: R29.
- [x] T33 — `test_case_authorize_request_without_action_is_rejected`: `_validate(CaseAuthorizeRequest, {"advisor_id": "222222222"})` lanza `ValidationError`. Cubre: R30.
- [x] T34 — `test_case_authorize_request_accepts_valid_action` parametrizado con `["reply", "close"]`: cada valor valida. Cubre: R28, R31.
- [x] T35 — `test_case_authorize_request_rejects_invalid_action` parametrizado con `["assign", "REPLY", "read", ""]`: cada valor lanza `ValidationError`. Cubre: R31.
- [x] T36 — `test_case_authorize_response_requires_allowed_and_case_id`: es subclase de `ContractModel`, sus campos obligatorios son exactamente `{"allowed", "case_id"}` y el ejemplo valida con `allowed is True`. Cubre: R33.
- [x] T37 — `test_case_authorize_response_rejects_allowed_not_true` parametrizado con `[False, None, "false", 0]`: cada valor lanza `ValidationError`. Cubre: R34.

En `contracts/tests/test_packaging.py`:

- [x] T38 — `test_case_authorize_action_is_exported`: `"CaseAuthorizeAction"` está en `lazaro_contracts.__all__` y `lazaro_contracts.CaseAuthorizeAction` existe. Cubre: R37.

## Verificación

- [x] T39 — Ejecutar `python -m pytest contracts` y luego la batería completa (`python -m pytest` o `./init.sh`); todo en verde, y los tests existentes de `design.md` §5.1 sin cambios en su código. Comprobar con `git diff -U0 -- contracts/ | grep -E '^-[^-]'` que las únicas líneas eliminadas en `contracts/` son: (1) la segunda línea de la docstring de módulo de `cases.py` (`design.md` §3); (2) en `CONTRATOS.md`, exactamente las dos líneas «antes» de E1 (fila común `409 | case_closed`) y E2 (fila `S11`) de `design.md` §1.1, comparadas literalmente; y que las líneas añadidas incluyen sus dos líneas «después». Ninguna otra línea de `CONTRATOS.md` eliminada. Ningún JSON existente cambia (`git diff --name-only -- 'contracts/examples/*.json'` vacío). Cubre: R18, R41, R42, R52.
- [x] T40 — Documentar la trazabilidad R1–R53 → test en `progress/impl_contrato_autorizacion_asesores.md`: R1-R40 como en T8-T38; R43-R47 → T41-T45; R48 → T49; R49 → T50 (+ T39); R50 → T51 (+ T39); R51 → T52; R52 → T39; R53 → T53 (+ T13 para R3); R18 → T21 + T39; R41 y R42 → la batería previa intacta (`test_every_example_validates_against_its_model`, `test_model_is_exported_and_is_base_model`, `test_assumptions_mention_s1_to_s10`, `test_assumptions_include_assign_idempotency`, `test_common_rules_case_closed_row_cites_assign`, `test_assign_section_documents_s11`, etc.) más la comprobación de diff de T39. Cubre: R18, R41, R42, R52.
