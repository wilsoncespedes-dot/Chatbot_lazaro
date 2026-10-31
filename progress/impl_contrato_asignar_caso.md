# Implementación — #9 contrato_asignar_caso

Estado: implementada, pendiente de reviewer (NO marcada `done`).
Spec: `specs/contrato_asignar_caso/{requirements,design,tasks}.md` (R13 retirado).
T1–T22 marcadas `[x]` en `tasks.md`. Sin bloqueos ni desviaciones del spec.

## Archivos tocados (solo `contracts/`)

| Archivo | Cambio |
|---------|--------|
| `contracts/lazaro_contracts/cases.py` | `CaseAssignRequest`, `CaseAssignResponse` tras `CaseCloseResponse` (design §3); docstring de módulo ampliada con `/cases/{id}/assign` (partida en 2 líneas para respetar el límite de 100 caracteres de `docs/conventions.md`) |
| `contracts/lazaro_contracts/__init__.py` | import de los dos modelos y alta en `__all__` tras `"CaseCloseResponse"` |
| `contracts/examples/case_assign_request.json` | nuevo: `{"advisor_id": "222222222"}` |
| `contracts/examples/case_assign_response.json` | nuevo: `{"status": "assigned", "case_id": "6f1c2a3e-0000-4000-8000-000000000001"}` |
| `contracts/CONTRATOS.md` | sección `### POST /cases/{id}/assign` al final de `## Rutas` (texto de design §4, sin mencionar `timed_out`); fila `409 \| case_closed` tras la 404 en `## Reglas comunes` (fila 404 intacta); fila `S11` en `## Supuestos a confirmar` |
| `contracts/tests/test_contratos_doc.py` | entradas nuevas en `ROUTES`, `OWN_ERRORS`, `SUCCESS_CODES`, conjunto `expected`; 6 tests nuevos (T12–T17) |
| `contracts/tests/test_examples.py` | imports, `EXAMPLES` y `MODEL_NAMES` ampliados |
| `contracts/tests/test_models.py` | imports (`CaseAssignRequest`, `CaseAssignResponse`, `ContractModel`), `BASE_EXAMPLES`, `IDENTIFIER_FIELDS` ampliados; 3 tests nuevos (T18–T20) |
| `contracts/tests/test_packaging.py` | `MODEL_NAMES` ampliado |

Fuera de `contracts/`: solo `progress/current.md` (anotación de sesión), `specs/contrato_asignar_caso/tasks.md` (checkboxes) y este archivo. `services/` sin tocar.

## Trazabilidad R → test

Archivos: `doc` = `contracts/tests/test_contratos_doc.py`, `ex` = `contracts/tests/test_examples.py`, `mod` = `contracts/tests/test_models.py`, `pkg` = `contracts/tests/test_packaging.py`.

| R | Test(s) |
|---|---------|
| R1 | doc `test_doc_has_a_section_per_route` (ROUTES incluye la ruta) |
| R2 | doc `test_route_names_exposing_service[POST /cases/{id}/assign]` |
| R3 | doc `test_assign_route_is_called_by_orchestrator`; `test_route_names_caller[POST /cases/{id}/assign]` |
| R4 | doc `test_route_names_models_in_package[POST /cases/{id}/assign]` |
| R5 | doc `test_request_table_lists_every_request_field[POST /cases/{id}/assign]` |
| R6 | doc `test_response_section_has_success_code_and_fields[POST /cases/{id}/assign]` (SUCCESS_CODES = 200) |
| R7 | doc `test_errors_table_has_common_rows[POST /cases/{id}/assign]` |
| R8 | doc `test_errors_table_has_route_specific_rows[POST /cases/{id}/assign]` (404 not_found, 409 case_closed) |
| R9 | doc `test_assign_errors_table_has_internal_error` |
| R10 | doc `test_assign_section_documents_path_id` |
| R11 | doc `test_assign_section_documents_s11` |
| R12 | doc `test_common_rules_case_closed_row_cites_assign`; `test_common_rules_document_error_shape_and_codes` (ampliado con `("409", "case_closed")`) |
| R13 | Retirado por el humano; sin test. La fila 404 de Reglas comunes no cambia (ver diff abajo) |
| R14 | doc `test_assumptions_include_assign_idempotency` |
| R15 | mod `test_case_assign_request_requires_advisor_id`; pkg `test_model_is_exported_and_is_base_model[CaseAssignRequest]` |
| R16 | mod `test_case_assign_request_requires_advisor_id`; `test_missing_required_field_is_rejected[CaseAssignRequest.advisor_id]` |
| R17 | mod `test_invalid_identifier_is_rejected[empty-CaseAssignRequest.advisor_id]`, `[too_long-CaseAssignRequest.advisor_id]` |
| R18 | mod `test_case_assign_response_requires_status_and_case_id`; `test_missing_required_field_is_rejected[CaseAssignResponse.status]`, `[CaseAssignResponse.case_id]` |
| R19 | mod `test_case_assign_response_rejects_invalid_status[open|timed_out|closed|ASSIGNED|'']` |
| R20 | mod `test_invalid_identifier_is_rejected[empty-CaseAssignResponse.case_id]`, `[too_long-CaseAssignResponse.case_id]` |
| R21 | mod `test_unexpected_field_is_rejected[CaseAssignRequest]`, `[CaseAssignResponse]` |
| R22 | pkg `test_model_is_exported_and_is_base_model[CaseAssignRequest]`, `[CaseAssignResponse]`; `test_all_names_are_importable` |
| R23 | ex `test_every_example_validates_against_its_model[case_assign_request.json]` |
| R24 | ex `test_every_example_validates_against_its_model[case_assign_response.json]` |
| R25 | ex `test_every_example_file_is_mapped`, `test_every_model_has_an_example` |
| R26 | batería previa intacta: `test_every_example_validates_against_its_model`, `test_model_is_exported_and_is_base_model`, `test_route_names_exposing_service`, `test_assumptions_mention_s1_to_s10`, etc.; más la comprobación de diff de T21 |
| R27 | batería completa en verde (565 previos + 33 nuevos = 598) sin tests eliminados ni aserciones relajadas; comprobación de diff de T21 |

## Verificación

- `python -m pytest contracts` (con `.venv`): **306 passed**.
- `./init.sh`: **exit 0**, `598 passed, 1 warning` (warning preexistente de starlette/httpx), "Entorno listo".
- Línea base 565 → 598 (+33: doc 13, examples 2, models 16, packaging 2).

### Comprobación `git diff` de T21

Líneas eliminadas en `contracts/` (`git diff -U0 -- contracts/ | grep -E '^-[^-]'`):

```
-"""Modelos de /handover, /cases/{id}/reply, /cases/{id}/close y /cases/check-timeouts."""
```

Única línea eliminada: la docstring de módulo de `cases.py` (permitida, design §1).

`git diff --numstat -- contracts/`:

```
38	0	contracts/CONTRATOS.md
4	0	contracts/lazaro_contracts/__init__.py
16	1	contracts/lazaro_contracts/cases.py
62	0	contracts/tests/test_contratos_doc.py
6	0	contracts/tests/test_examples.py
34	0	contracts/tests/test_models.py
2	0	contracts/tests/test_packaging.py
```

Nuevos sin seguimiento: `contracts/examples/case_assign_request.json`, `contracts/examples/case_assign_response.json`.
`git diff --name-only -- 'contracts/examples/*.json'`: vacío (ningún JSON existente cambia).
`git status -- services/`: sin cambios.

## Notas

- La fila `404 | not_found` de `## Reglas comunes` no se tocó (R13 retirado): `CONTRATOS.md` tiene 0 líneas eliminadas.
- Sin dependencias nuevas ni variables de entorno nuevas.
