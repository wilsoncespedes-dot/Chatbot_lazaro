# Review — feature 9 `contrato_asignar_caso`

**Veredicto:** APPROVED

Revisado el 2026-10-30 contra `specs/contrato_asignar_caso/` (R13 retirado por el humano),
`docs/`, `CHECKPOINTS.md` y `progress/impl_contrato_asignar_caso.md`.
`./init.sh` lo ejecutó el reviewer: exit 0, **598 passed** (línea base 565, +33), 1 warning
que ya existía (starlette/httpx), «Entorno listo».

## Trazabilidad requirements ↔ tests

Archivos: `doc` = `contracts/tests/test_contratos_doc.py`, `mod` = `contracts/tests/test_models.py`,
`ex` = `contracts/tests/test_examples.py`, `pkg` = `contracts/tests/test_packaging.py`.

- R1: [x] doc `test_doc_has_a_section_per_route` (`ROUTES` ampliado, l.23)
- R2: [x] doc `test_route_names_exposing_service[POST /cases/{id}/assign]`
- R3: [x] doc `test_assign_route_is_called_by_orchestrator` (l.263) + `test_route_names_caller[...]`
- R4: [x] doc `test_route_names_models_in_package[POST /cases/{id}/assign]`
- R5: [x] doc `test_request_table_lists_every_request_field[POST /cases/{id}/assign]`
- R6: [x] doc `test_response_section_has_success_code_and_fields[...]` (`SUCCESS_CODES` = "200")
- R7: [x] doc `test_errors_table_has_common_rows[POST /cases/{id}/assign]`
- R8: [x] doc `test_errors_table_has_route_specific_rows[...]` (`OWN_ERRORS`: 404 not_found, 409 case_closed)
- R9: [x] doc `test_assign_errors_table_has_internal_error` (l.268)
- R10: [x] doc `test_assign_section_documents_path_id` (l.273)
- R11: [x] doc `test_assign_section_documents_s11` (l.278)
- R12: [x] doc `test_common_rules_case_closed_row_cites_assign` (l.293) + `test_common_rules_document_error_shape_and_codes` (añadido `("409", "case_closed")`)
- R13: retirado por el humano; sin test. Confirmado en el diff: la fila `404 | not_found` de Reglas comunes no cambia
- R14: [x] doc `test_assumptions_include_assign_idempotency` (l.301)
- R15: [x] mod `test_case_assign_request_requires_advisor_id` (subclase de `ContractModel`, obligatorios == {"advisor_id"})
- R16: [x] mod `test_case_assign_request_requires_advisor_id` + `test_missing_required_field_is_rejected[CaseAssignRequest.advisor_id]`
- R17: [x] mod `test_invalid_identifier_is_rejected[empty|too_long-CaseAssignRequest.advisor_id]`
- R18: [x] mod `test_case_assign_response_requires_status_and_case_id`
- R19: [x] mod `test_case_assign_response_rejects_invalid_status[open|timed_out|closed|ASSIGNED|'']`
- R20: [x] mod `test_invalid_identifier_is_rejected[empty|too_long-CaseAssignResponse.case_id]`
- R21: [x] mod `test_unexpected_field_is_rejected[CaseAssignRequest|CaseAssignResponse]`
- R22: [x] pkg `test_model_is_exported_and_is_base_model[CaseAssignRequest|CaseAssignResponse]`
- R23: [x] ex `test_every_example_validates_against_its_model[case_assign_request.json]`
- R24: [x] ex `test_every_example_validates_against_its_model[case_assign_response.json]`
- R25: [x] ex `test_every_example_file_is_mapped`, `test_every_model_has_an_example` (`EXAMPLES` y `MODEL_NAMES` ampliados)
- R26: [x] la batería que ya existía sigue verde, más la comprobación del diff (ver abajo)
- R27: [x] 598/598 en verde; ningún test eliminado ni aserción debilitada (el diff de los tests solo tiene líneas `+`)

Cada test nuevo (6 en doc, 3 en mod) lleva en su docstring el prefijo `contrato_asignar_caso R<n>` y
corresponde a un R real.

## Contrato exacto

- [x] `contracts/lazaro_contracts/cases.py`: `CaseAssignRequest(ContractModel)` con `advisor_id: Identifier`;
  `CaseAssignResponse(ContractModel)` con `status: Literal["assigned"]`, `case_id: Identifier`. Coinciden
  literalmente con `design.md` §3.
- [x] `__init__.py`: se importan y se listan en `__all__` tras `"CaseCloseResponse"`.
- [x] Ejemplos: `case_assign_request.json` = `{"advisor_id": "222222222"}`, `case_assign_response.json` =
  `{"status": "assigned", "case_id": "6f1c2a3e-0000-4000-8000-000000000001"}` (design §2).
- [x] `CONTRATOS.md`: la sección `### POST /cases/{id}/assign` es idéntica a design §4 y no menciona `timed_out`;
  la fila `| 409  | \`case_closed\` | \`/cases/{id}/assign\` | ...` está tras la 404 en Reglas comunes;
  la fila S11 está al final de Supuestos.

## Carácter aditivo (`git diff -- contracts/`)

- [x] Única línea eliminada: la docstring de módulo de `cases.py` (permitida por design §1; ahora ocupa 2 líneas
  para no pasar de 100 caracteres).
- [x] La fila `404 | not_found` de Reglas comunes está intacta (`CONTRATOS.md`: 38 +, 0 −).
- [x] Ningún JSON existente cambia (los 2 JSON son nuevos y sin seguimiento).
- [x] Los tests existentes solo se amplían (entradas en dicts/listas/conjuntos); 0 líneas eliminadas en `contracts/tests/`.
- [x] Fuera de `contracts/` y `progress/`: solo `feature_list.json`, `progress/current.md`,
  `specs/traspaso_asesor/design.md` (cambios del leader: dos supuestos CONFIRMABLE → CONFIRMADO) y
  `specs/contrato_asignar_caso/` (checkboxes de tasks). `services/`, `eval/`, `scripts/`,
  `docker-compose.yml` y `.github/` no tienen cambios.

## Tasks completas

- T1–T22: [x] (todas `[x]` en `specs/contrato_asignar_caso/tasks.md`)

## Checkpoints

- C1: [x] Los archivos del arnés y los docs existen; `./init.sh` exit 0.
- C2: [x] Solo #9 está en `in_progress`; las features `done` siguen en verde; `progress/current.md` describe la sesión activa.
- C3: [x] Sin servicios nuevos; la ruta nueva está en `CONTRATOS.md`; sin dependencias nuevas; ni GPL ni secretos; ni `print`, ni `eval`/`exec`, ni TODOs.
- C4: [x] 598 tests en verde; los tests de contrato no tocan la red ni una base de datos.
- C5: [x] Sin archivos sospechosos sin seguimiento. La entrada de `progress/history.md` para esta sesión la escribe el leader al cerrar, no la implementación.
- C6: [x] `specs/contrato_asignar_caso/` completo; EARS; design con alternativas descartadas y supuestos; tasks `[x]`; cada R vigente tiene test.

## Cambios requeridos

Ninguno.

Observación no bloqueante: el informe de implementación dice que fuera de `contracts/` solo se tocaron
`progress/current.md`, `tasks.md` y el propio informe. Los cambios en `feature_list.json` y
`specs/traspaso_asesor/design.md` son del leader, como indica el encargo.
