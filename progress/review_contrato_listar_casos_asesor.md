# Review — feature 33 (contrato_listar_casos_asesor)

**Veredicto:** APPROVED

`./init.sh` verde según el leader (1924 passed, 1 warning); no se repitió.

## Trazabilidad requirements ↔ tests
- R1: [x] `contracts/tests/test_listar_casos_asesor.py::test_route_section_documents_exposer_caller_models_and_token`, `test_route_query_table_lists_advisor_id`, `test_route_response_is_200_and_lists_exactly_four_fields`, `test_route_errors_table_has_401_422_and_500`
- R2: [x] `test_query_requires_advisor_id_and_rejects_unknown_fields`
- R3: [x] `test_item_requires_all_four_fields`, `test_item_rejects_naive_date`, `test_item_rejects_status_outside_the_three_values`, `test_item_rejects_empty_unknown_or_repeated_actions`
- R4: [x] `test_response_limits_items_to_max_and_has_default_constant`
- R5: [x] `test_item_rejects_contact_and_conversation_fields`
- R6: [x] `contracts/tests/test_examples.py` (3 entradas nuevas en `EXAMPLES`, l.74-76)
- R7: [x] `test_assumption_s14_documents_inclusion_actions_order_and_limit`, `test_s1_to_s13_are_unchanged` (compara con `git show HEAD`)
- R8: [x] `services/handover/tests/test_list_cases.py::test_get_cases_without_valid_token_returns_401` + `test_security.py::test_all_non_health_routes_require_service_token`
- R9: [x] `test_get_cases_rejects_invalid_query_with_422` (falta, vacío, 65, extra)
- R10: [x] `test_unregistered_advisor_gets_empty_list_without_querying`
- R11: [x] `test_open_and_timed_out_cases_offer_reply_assign_and_close`
- R12: [x] `test_case_assigned_to_requester_offers_reply_and_close`
- R13: [x] `test_orphan_cases_offer_only_close` (nulo y retirado)
- R14: [x] `test_closed_and_assigned_to_another_registered_advisor_are_excluded`, `test_actions_match_can_act_on_case_and_discard_other_cases` (`_LeakyRepository`)
- R15: [x] `test_cases_are_ordered_by_created_at_then_case_id`; SQL en `test_repository.py::test_postgres_list_cases_for_advisor_is_parameterized_and_ordered`
- R16: [x] `test_limit_applies_after_filtering`
- R17: [x] `test_config.py::test_case_list_limit_rejects_out_of_range` (0, 201, abc)
- R18: [x] `test_response_only_exposes_the_four_contract_fields`
- R19: [x] `test_listing_does_not_modify_cases_or_record_denials` (registrado y no registrado)
- R20: [x] `test_repository_failure_returns_500_internal_error_without_details`
- R21: [x] `test_examples_validate_against_their_models` + `test_examples.py`
- R22: [x] `test_config.py::test_case_list_limit_defaults_to_50`, `test_list_cases.py::test_default_limit_is_50`

## Tasks completas
- T1–T10: [x]
- T11: [ ] justificado: `progress/impl_contrato_listar_casos_asesor.md` («Pendiente para Claude») lo deja pendiente de ejecutar `./init.sh`, que ya pasó. El leader debe marcar T11 `[x]` y añadir el resultado al informe al cerrar.

## Puntos revisados
- Contrato aditivo: `git diff contracts/CONTRATOS.md` = +42/−0; sección `### GET /cases` (l.641-680) y fila S14 añadidas, S1–S13 intactas.
- Modelos (`contracts/lazaro_contracts/cases.py:146-175`): `ContractModel` (extra prohibido), `actions` con `min_length=1` y validador anti-duplicados, `RootModel` con `max_length=MAX_CASE_LIST_LIMIT`. Constantes en `common.py:17-19`, exportadas en `__init__.py`.
- Ejemplos: `case_list_response.json` tiene open / assigned propio / huérfano en orden R15; vacío `[]`.
- Query/límite: `main.py:143-145` usa `Annotated[CaseListQuery, Query()]` → 422 vía el handler existente; `config.py:65-67` `Field(ge=1, le=200)` con default 50; `.env.example` actualizado.
- Token: cubierto por el middleware global `verify_service_token` (`main.py:102`).
- SQL (`repository.py:471-491`): totalmente parametrizado (7 `%s`, `ANY(%s)` con lista), `ORDER BY created_at ASC, case_id ASC LIMIT %s`; sin interpolar datos del usuario (`_CASE_COLUMNS` es constante).
- Actions (`domain.py:180-210`): se derivan de `can_act_on_case` existente, sin reescribir S12; se quita `assign` en `assigned` y se descartan casos sin acciones (defensa en profundidad).
- PII: `CaseListItem` solo con 4 campos; log `cases_listed count=%d` sin ids ni datos.
- Sin escritura: la ruta solo lee; no llama a `_deny` ni registra notificaciones; el asesor no registrado no consulta el repositorio.

## Checkpoints
- C1: [x] archivos base presentes; `./init.sh` verde.
- C2: [x] una sola feature `in_progress` (#33; #29 está en `spec_ready`).
- C3: [x] sin servicios nuevos ni imports entre servicios; ruta en `CONTRATOS.md`; sin dependencias nuevas; `CASE_LIST_LIMIT` en `.env.example`; sin SQL concatenado ni prints.
- C4: [x] tests con adaptadores falsos (`FakeCaseRepository`, `_FakeConn`); prueba obligatoria de token cubierta.
- C5: [x] sin archivos sospechosos; el cierre de estado y `history.md` le corresponden al leader.
- C6: [x] spec completo; R1–R22 cubiertos; T11 justificado.

## Cambios requeridos
Ninguno bloqueante. Al cerrar: marcar T11 `[x]` y añadir el resultado de `./init.sh` a `progress/impl_contrato_listar_casos_asesor.md`.
