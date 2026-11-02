# Implementación — contrato_conversacion_caso (feature #15)

## Resumen

Implementada dentro del alcance de `design.md` §1 y §2, solo en `contracts/`:

- `lazaro_contracts/cases.py`: `CaseClientMessageRequest`,
  `CaseClientMessageResponse` y docstring de módulo ampliada con
  `/cases/{id}/client-message`.
- `lazaro_contracts/__init__.py`: ambos modelos exportados en `__all__`.
- `examples/`: `case_client_message_request.json`,
  `case_client_message_response.json` y
  `case_client_message_response_not_assigned.json`.
- `CONTRATOS.md`: sección `### POST /cases/{id}/client-message` al final de
  `## Rutas`, línea `- **Llama:**` de `### POST /cases/{id}/close` ampliada con
  `orchestrator` y fila `S13` al final de `## Supuestos a confirmar`.
- Tests de contrato: entradas nuevas en `ROUTES`, `OWN_ERRORS`,
  `SUCCESS_CODES`, `EXAMPLES`, `MODEL_NAMES`, `BASE_EXAMPLES` e
  `IDENTIFIER_FIELDS`, más los tests nuevos T11-T27 y T31-T34.

No se ha tocado `feature_list.json`, `progress/current.md`,
`progress/history.md`, `services/`, `eval/`, `scripts/`, `docker-compose.yml`
ni el harness. La feature no se marca `done`.

## Trazabilidad

Archivos abreviados: `doc` = `contracts/tests/test_contratos_doc.py`,
`ex` = `contracts/tests/test_examples.py`, `mod` =
`contracts/tests/test_models.py`, `pkg` = `contracts/tests/test_packaging.py`.

- R1 → doc `test_doc_has_a_section_per_route[POST /cases/{id}/client-message]`
- R2 → doc `test_route_names_exposing_service[POST /cases/{id}/client-message]`
- R3 → doc `test_route_names_caller[POST /cases/{id}/client-message]`,
  `test_client_message_route_is_called_by_orchestrator`
- R4 → doc `test_route_names_models_in_package[POST /cases/{id}/client-message]`
- R5 → doc `test_request_table_lists_every_request_field[POST /cases/{id}/client-message]`
- R6 → doc `test_response_section_has_success_code_and_fields[POST /cases/{id}/client-message]`
- R7 → doc `test_errors_table_has_common_rows[POST /cases/{id}/client-message]`
- R8 → doc `test_errors_table_has_route_specific_rows[POST /cases/{id}/client-message]`
- R9 → doc `test_client_message_errors_table_has_internal_error`
- R10 → doc `test_client_message_section_documents_path_id`
- R11 → doc `test_client_message_section_documents_statuses`
- R12 → doc `test_client_message_upstream_error_row_mentions_advisor`
- R13 → doc `test_client_message_error_codes_are_declared_in_common_rules`
- R14 → doc `test_close_route_is_also_called_by_orchestrator`
- R15 → doc `test_assumptions_include_client_message_forwarding`
- R16 → doc `test_assumptions_s13_forward_failure_does_not_fall_back_to_rag`
- R17 → doc `test_assumptions_s13_advisor_commands_use_messages_route`
- R18 → doc `test_assumptions_s13_advisor_id_is_telegram_sender`
- R19 → mod `test_case_client_message_request_requires_text_and_at`
- R20 → mod `test_case_client_message_request_requires_text_and_at`,
  `test_missing_required_field_is_rejected[CaseClientMessageRequest.text]`
- R21 → mod `test_case_client_message_request_requires_text_and_at`,
  `test_missing_required_field_is_rejected[CaseClientMessageRequest.at]`
- R22 → mod `test_case_client_message_request_rejects_naive_at`
- R23 → mod `test_case_client_message_request_rejects_invalid_text[empty]`,
  `[too_long]`, `test_case_client_message_request_accepts_text_at_max_length`
- R24 → mod `test_case_client_message_response_requires_status_and_case_id`,
  `test_case_client_message_response_accepts_valid_status[forwarded]`,
  `[not_assigned]`,
  `test_missing_required_field_is_rejected[CaseClientMessageResponse.status]`,
  `[CaseClientMessageResponse.case_id]`
- R25 → mod `test_case_client_message_response_rejects_invalid_status[assigned|open|closed|FORWARDED|sent|'']`
- R26 → mod `test_invalid_identifier_is_rejected[empty-CaseClientMessageResponse.case_id]`,
  `[too_long-CaseClientMessageResponse.case_id]`
- R27 → mod `test_unexpected_field_is_rejected[CaseClientMessageRequest]`,
  `[CaseClientMessageResponse]`
- R28 → pkg `test_model_is_exported_and_is_base_model[CaseClientMessageRequest]`,
  `[CaseClientMessageResponse]`; `test_all_names_are_importable`
- R29 → ex `test_every_example_validates_against_its_model[case_client_message_request.json]`
- R30 → ex `test_every_example_validates_against_its_model[case_client_message_response.json]`
- R31 → ex `test_every_example_validates_against_its_model[case_client_message_response_not_assigned.json]`
- R32 → ex `test_every_example_file_is_mapped`,
  `test_every_model_has_an_example`
- R33 → mod `test_message_request_requires_its_fields`,
  `test_message_response_accepts_valid_status`; doc
  `test_route_names_exposing_service[POST /messages]`; además la comprobación
  de diff de T29 (pendiente del puente Claude)
- R34 → batería previa sin cambios de aserciones ni de comportamiento; además
  la comprobación de diff de T29 (pendiente del puente Claude)
- R35 → batería completa de tests (T28, pendiente del puente Claude)
- R36 → doc `test_assumptions_s13_non_command_advisor_message_follows_current_flow`
- R37 → doc `test_assumptions_s13_advisor_list_matches_sender_user_id`
- R38 → doc `test_assumptions_s13_advisor_commands_follow_s12`
- R39 → doc `test_assumptions_s13_group_ids_cannot_use_commands`

## Tasks

- Completadas por el escritor: T1-T27 y T30.
- Pendientes del puente Claude (requieren shell): T0 (línea base; en
  `progress/current.md` consta 385 passed en `contracts`), T28 (`pytest`) y
  T29 (`git diff`). Se dejan sin marcar para no afirmar una verificación no
  ejecutada.
- Tests nuevos esperados: 49 (`doc` 22, `ex` 3, `mod` 22, `pkg` 2); el total
  esperado en `contracts` es 385 + 49 = 434.

## Notas

- La única edición de texto publicado con efecto en el contrato es la línea
  `- **Llama:**` de `### POST /cases/{id}/close` (R14). No se tocaron
  `## Reglas comunes`, `### POST /messages` ni `messages.py`.
- `S13` se añadió al final de la tabla de supuestos (después de `S12`) y no
  contiene `|` internos, de modo que `_assumption_row("S13")` la lee entera.
- Sin dependencias nuevas ni variables de entorno nuevas.

## Verificación (puente Claude, 2026-11-01)

- T0: precondición #13 cumplida (`S12` en supuestos, `403 | forbidden` en
  `## Reglas comunes`, `### POST /cases/{id}/authorize` presente). Línea base
  `.venv/Scripts/python.exe -m pytest contracts` → 385 passed.
- T28: `.venv/Scripts/python.exe -m pytest contracts` → 434 passed
  (385 + 49 nuevos). `bash ./init.sh` → 1014 passed, 1 warning
  (deprecación de `starlette.testclient`, ajena a la feature); entorno OK.
- T29: respecto al estado previo del árbol de trabajo, la única línea eliminada
  nueva en `contracts/` es la `- **Llama:**` de `### POST /cases/{id}/close`
  (la docstring de `cases.py` solo cambia una línea aún no commiteada).
  `contracts/examples/*.json` existentes sin cambios (solo 3 archivos nuevos
  sin seguimiento). `services/` y `feature_list.json` sin cambios (checksum del
  diff idéntico antes y después del escritor). `### POST /messages`,
  `## Reglas comunes` y `messages.py` intactos.
- Trazabilidad R1–R39 → test completa (sección «Trazabilidad»).
- Estado: implementado, pendiente de revisión. No marcado `done`.
