# Tasks — contrato_asignar_caso (feature #9)

> Orden pensado para que cada paso sea verificable. Solo se toca `contracts/`
> (ver `design.md` §1). Cambio aditivo: en los tests existentes solo se añaden
> entradas a dicts/listas/conjuntos; no se borra ni relaja ninguna aserción.
> Cada test nuevo lleva en su docstring el `R<n>` que cubre (con el prefijo
> `contrato_asignar_caso` para no confundirlo con los `R<n>` de la #1, p. ej.
> `"""contrato_asignar_caso R16: ..."""`).

## Modelos

- [x] T1 — Añadir `CaseAssignRequest` y `CaseAssignResponse` en `contracts/lazaro_contracts/cases.py` tras `CaseCloseResponse`, según `design.md` §3; ampliar la docstring de módulo con `/cases/{id}/assign`. Cubre: R15, R17, R18, R20, R21.
- [x] T2 — Importar ambos modelos en `contracts/lazaro_contracts/__init__.py` y añadirlos a `__all__` tras `"CaseCloseResponse"`. Cubre: R22.

## Ejemplos

- [x] T3 — Crear `contracts/examples/case_assign_request.json` y `contracts/examples/case_assign_response.json` (UTF-8, 2 espacios, valores de `design.md` §2). Cubre: R23, R24.

## Documento

- [x] T4 — Añadir en `contracts/CONTRATOS.md` la sección `### POST /cases/{id}/assign` al final de `## Rutas` (tras `### POST /cases/check-timeouts`), con el texto de `design.md` §4. No mencionar `timed_out` (fuera de alcance, `design.md` §1). Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11.
- [x] T5 — En la tabla de errores de `## Reglas comunes`: añadir la fila `409 | case_closed` tras la 404. La fila `404 | not_found` existente NO se toca (R13 retirado). Cubre: R12.
- [x] T6 — Añadir la fila `S11` al final de la tabla de `## Supuestos a confirmar`. Cubre: R14.

## Tests — ampliación de los existentes

- [x] T7 — `contracts/tests/test_contratos_doc.py`: añadir `"POST /cases/{id}/assign": "handover"` a `ROUTES`, `"POST /cases/{id}/assign": "200"` a `SUCCESS_CODES` y `"POST /cases/{id}/assign": [("404", "not_found"), ("409", "case_closed")]` a `OWN_ERRORS`. Así `test_doc_has_a_section_per_route` (R1), `test_route_names_exposing_service[POST /cases/{id}/assign]` (R2), `test_route_names_models_in_package[…]` (R4), `test_request_table_lists_every_request_field[…]` (R5), `test_response_section_has_success_code_and_fields[…]` (R6), `test_errors_table_has_common_rows[…]` (R7) y `test_errors_table_has_route_specific_rows[…]` (R8) cubren la ruta nueva. Cubre: R1, R2, R4, R5, R6, R7, R8.
- [x] T8 — En el mismo archivo, añadir `("409", "case_closed")` al conjunto `expected` de `test_common_rules_document_error_shape_and_codes`. Cubre: R12.
- [x] T9 — `contracts/tests/test_examples.py`: importar los dos modelos; añadir `"case_assign_request.json": CaseAssignRequest` y `"case_assign_response.json": CaseAssignResponse` a `EXAMPLES`, y `"CaseAssignRequest"`, `"CaseAssignResponse"` a `MODEL_NAMES`. Así `test_every_example_validates_against_its_model[case_assign_request.json]` (R23), `…[case_assign_response.json]` (R24), `test_every_example_file_is_mapped` y `test_every_model_has_an_example` (R25) los cubren. Cubre: R23, R24, R25.
- [x] T10 — `contracts/tests/test_models.py`: importar los dos modelos; añadir a `BASE_EXAMPLES` `CaseAssignRequest: ("case_assign_request.json", None)` y `CaseAssignResponse: ("case_assign_response.json", None)`; añadir a `IDENTIFIER_FIELDS` `(CaseAssignRequest, "advisor_id")` y `(CaseAssignResponse, "case_id")`. Así `test_missing_required_field_is_rejected[CaseAssignRequest.advisor_id]` (R16), `test_unexpected_field_is_rejected[CaseAssignRequest]` y `[CaseAssignResponse]` (R21), `test_invalid_identifier_is_rejected[…-CaseAssignRequest.advisor_id]` (R17) y `[…-CaseAssignResponse.case_id]` (R20) los cubren. Cubre: R16, R17, R20, R21.
- [x] T11 — `contracts/tests/test_packaging.py`: añadir `"CaseAssignRequest"` y `"CaseAssignResponse"` a `MODEL_NAMES`, de modo que `test_model_is_exported_and_is_base_model[CaseAssignRequest]` y `[CaseAssignResponse]` los cubran. Cubre: R22.

## Tests — nuevos

En `contracts/tests/test_contratos_doc.py`:

- [x] T12 — `test_assign_route_is_called_by_orchestrator`: la línea `- **Llama:**` de `POST /cases/{id}/assign` contiene `orchestrator`. Cubre: R3.
- [x] T13 — `test_assign_errors_table_has_internal_error`: la tabla `#### Errores` de la ruta contiene `("500", "internal_error")`. Cubre: R9.
- [x] T14 — `test_assign_section_documents_path_id`: la sección de la ruta contiene `` `{id}` es el `case_id` (identificador, 1–64 caracteres) ``. Cubre: R10.
- [x] T15 — `test_assign_section_documents_s11`: la sección de la ruta contiene `` `assigned` ``, `` `200` ``, «sin cambiar el asesor», `` `closed` ``, `` `409` ``, `` `case_closed` `` y `S11`. Cubre: R11.
- [x] T16 — `test_common_rules_case_closed_row_cites_assign`: la fila `409 | case_closed` de la tabla de `## Reglas comunes` contiene `/cases/{id}/assign`. Cubre: R12.
- [x] T17 — `test_assumptions_include_assign_idempotency`: `_assumption_row("S11")` contiene `` `POST /cases/{id}/assign` ``, `` `assigned` ``, `` `200` ``, «sin cambiar el asesor», `` `closed` ``, `` `409` `` y `` `case_closed` ``. Cubre: R14.

En `contracts/tests/test_models.py`:

- [x] T18 — `test_case_assign_request_requires_advisor_id`: los campos obligatorios de `CaseAssignRequest` son exactamente `{"advisor_id"}`, es subclase de `ContractModel` y `_validate(CaseAssignRequest, {})` lanza `ValidationError`. Cubre: R15, R16.
- [x] T19 — `test_case_assign_response_requires_status_and_case_id`: los campos obligatorios de `CaseAssignResponse` son exactamente `{"status", "case_id"}`, es subclase de `ContractModel` y el ejemplo valida con `status == "assigned"`. Cubre: R18.
- [x] T20 — `test_case_assign_response_rejects_invalid_status` parametrizado con `["open", "timed_out", "closed", "ASSIGNED", ""]`: cada valor lanza `ValidationError`. Cubre: R19.

## Verificación

- [x] T21 — Ejecutar `python -m pytest contracts` y luego la batería completa del repositorio (`python -m pytest`); todo en verde. Comprobar con `git diff` que en `contracts/` la única línea eliminada permitida es la de la docstring de módulo de `cases.py` (`design.md` §1), y que ningún JSON existente cambia. Cubre: R26, R27.
- [x] T22 — Documentar la trazabilidad R1–R12 y R14–R27 → test (R13 retirado, sin test) en `progress/impl_contrato_asignar_caso.md` (R26 y R27 → la batería existente: `test_every_example_validates_against_its_model`, `test_model_is_exported_and_is_base_model`, `test_route_names_exposing_service`, `test_assumptions_mention_s1_to_s10` y el resto de tests previos, más la comprobación de diff de T21). Cubre: R26, R27.
