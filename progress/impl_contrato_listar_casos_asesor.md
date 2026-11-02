# Implementación — #33 contrato_listar_casos_asesor

Estado: implementado según `specs/contrato_listar_casos_asesor/{requirements,design,tasks}.md`.
Cambio aditivo en `contracts/` y ruta nueva de solo lectura en `handover/`.

## Resumen

- Contrato: `CaseListAction`, `CaseListStatus`, `CaseListQuery`, `CaseListItem`
  (validador sin acciones repetidas) y `CaseListResponse` (arreglo de nivel
  superior, máximo 200) en `lazaro_contracts`, exportados en `__all__`;
  `DEFAULT_CASE_LIST_LIMIT = 50` y `MAX_CASE_LIST_LIMIT = 200` en `common.py`.
  Tres ejemplos nuevos registrados en `test_examples.py` y la sección
  `### GET /cases` más el supuesto `S14` en `CONTRATOS.md`, sin editar filas
  existentes.
- Handover: `CASE_LIST_LIMIT` en `Settings` (default 50, rango 1–200) y en
  `.env.example`; `list_cases_for_advisor` en el Protocol, `FakeCaseRepository`
  y `PostgresCaseRepository` (un `SELECT` parametrizado con filtro, orden y
  `LIMIT`); `list_advisor_cases` calcula `actions` con el `can_act_on_case`
  existente (sin reescribir S12) y descarta los casos sin acciones; ruta
  `GET /cases` con `Annotated[CaseListQuery, Query()]`.
- La ruta no modifica casos ni registra denegaciones o notificaciones; un
  asesor no registrado recibe `200 []` sin consultar el repositorio.

## Trazabilidad

- R1 → `contracts/tests/test_listar_casos_asesor.py::test_route_section_documents_exposer_caller_models_and_token`
- R1 → `contracts/tests/test_listar_casos_asesor.py::test_route_query_table_lists_advisor_id`
- R1 → `contracts/tests/test_listar_casos_asesor.py::test_route_response_is_200_and_lists_exactly_four_fields`
- R1 → `contracts/tests/test_listar_casos_asesor.py::test_route_errors_table_has_401_422_and_500`
- R2 → `contracts/tests/test_listar_casos_asesor.py::test_query_requires_advisor_id_and_rejects_unknown_fields`
- R2 → `contracts/tests/test_listar_casos_asesor.py::test_models_and_constants_are_exported`
- R3 → `contracts/tests/test_listar_casos_asesor.py::test_item_requires_all_four_fields`
- R3 → `contracts/tests/test_listar_casos_asesor.py::test_item_rejects_naive_date`
- R3 → `contracts/tests/test_listar_casos_asesor.py::test_item_rejects_status_outside_the_three_values`
- R3 → `contracts/tests/test_listar_casos_asesor.py::test_item_rejects_empty_unknown_or_repeated_actions`
- R4 → `contracts/tests/test_listar_casos_asesor.py::test_response_limits_items_to_max_and_has_default_constant`
- R4 → `contracts/tests/test_listar_casos_asesor.py::test_models_and_constants_are_exported`
- R5 → `contracts/tests/test_listar_casos_asesor.py::test_item_rejects_contact_and_conversation_fields`
- R6 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[case_list_query.json]`
- R6 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[case_list_response.json]`
- R6 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[case_list_response_empty.json]`
- R6 → `contracts/tests/test_listar_casos_asesor.py::test_examples_validate_against_their_models`
- R7 → `contracts/tests/test_listar_casos_asesor.py::test_assumption_s14_documents_inclusion_actions_order_and_limit`
- R7 → `contracts/tests/test_listar_casos_asesor.py::test_s1_to_s13_are_unchanged`
- R8 → `services/handover/tests/test_list_cases.py::test_get_cases_without_valid_token_returns_401`
- R8 → `services/handover/tests/test_security.py::test_all_non_health_routes_require_service_token`
- R9 → `services/handover/tests/test_list_cases.py::test_get_cases_rejects_invalid_query_with_422`
- R10 → `services/handover/tests/test_list_cases.py::test_unregistered_advisor_gets_empty_list_without_querying`
- R11 → `services/handover/tests/test_list_cases.py::test_open_and_timed_out_cases_offer_reply_assign_and_close`
- R11 → `services/handover/tests/test_list_cases.py::test_actions_match_can_act_on_case_and_discard_other_cases`
- R12 → `services/handover/tests/test_list_cases.py::test_case_assigned_to_requester_offers_reply_and_close`
- R12 → `services/handover/tests/test_list_cases.py::test_actions_match_can_act_on_case_and_discard_other_cases`
- R13 → `services/handover/tests/test_list_cases.py::test_orphan_cases_offer_only_close`
- R13 → `services/handover/tests/test_list_cases.py::test_actions_match_can_act_on_case_and_discard_other_cases`
- R13 → `services/handover/tests/test_repository.py::test_postgres_list_cases_for_advisor_is_parameterized_and_ordered`
- R14 → `services/handover/tests/test_list_cases.py::test_closed_and_assigned_to_another_registered_advisor_are_excluded`
- R14 → `services/handover/tests/test_list_cases.py::test_actions_match_can_act_on_case_and_discard_other_cases`
- R14 → `services/handover/tests/test_repository.py::test_postgres_list_cases_for_advisor_is_parameterized_and_ordered`
- R15 → `services/handover/tests/test_list_cases.py::test_cases_are_ordered_by_created_at_then_case_id`
- R15 → `services/handover/tests/test_repository.py::test_postgres_list_cases_for_advisor_is_parameterized_and_ordered`
- R16 → `services/handover/tests/test_list_cases.py::test_limit_applies_after_filtering`
- R16 → `services/handover/tests/test_repository.py::test_postgres_list_cases_for_advisor_is_parameterized_and_ordered`
- R17 → `services/handover/tests/test_config.py::test_case_list_limit_rejects_out_of_range`
- R18 → `services/handover/tests/test_list_cases.py::test_response_only_exposes_the_four_contract_fields`
- R19 → `services/handover/tests/test_list_cases.py::test_listing_does_not_modify_cases_or_record_denials`
- R20 → `services/handover/tests/test_list_cases.py::test_repository_failure_returns_500_internal_error_without_details`
- R21 → `contracts/tests/test_listar_casos_asesor.py::test_examples_validate_against_their_models`
- R22 → `services/handover/tests/test_config.py::test_case_list_limit_defaults_to_50`
- R22 → `services/handover/tests/test_list_cases.py::test_default_limit_is_50`

## Pendiente para Claude

- T11: ejecutar `./init.sh` y adjuntar el resultado a este informe. No se ha
  ejecutado ningún comando de shell en esta sesión.
## Corrección solicitada tras ./init.sh
- Resultado: 2 failed, 1922 passed.
- services/handover/tests/test_list_cases.py::test_response_only_exposes_the_four_contract_fields: env.add_case ya fija reason; no pasar reason como argumento duplicado. Crea el caso y modifica el campo en el objeto/fixture o adapta el fixture mínimamente sin romper tests existentes.
- contracts/tests/test_listar_casos_asesor.py::test_route_query_table_lists_advisor_id: _first_column_cells elimina formato Markdown y devuelve advisor_id sin backticks; compara el valor normalizado.
- No debilites requisitos ni añadas cambio de funcionalidad. Actualiza los tests y este informe; no ejecutes shell.

## Correcciones aplicadas

- `services/handover/tests/test_list_cases.py::test_response_only_exposes_the_four_contract_fields`:
  se quitó `reason="user_request"` del `env.add_case` (el fixture ya fija `reason` y no
  admite duplicado). El `reason` y `last_messages` de la prueba se aplican después con
  `model_copy(update=...)` sobre el caso guardado, así que las aserciones R18 sobre
  `contact_id`, `chat_id`, `reason` y texto de mensajes se conservan intactas.
- `contracts/tests/test_listar_casos_asesor.py::test_route_query_table_lists_advisor_id`:
  `_first_column_cells` devuelve la primera columna ya sin backticks; la aserción compara
  ahora `"advisor_id"` normalizado. No se cambia el requisito ni el documento.
- Sin cambios de funcionalidad ni de contrato. T11 sigue pendiente de que Claude
  ejecute `./init.sh`.

