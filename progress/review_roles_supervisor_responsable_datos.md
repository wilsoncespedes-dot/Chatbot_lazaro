# Review — feature 49 (roles_supervisor_responsable_datos)

**Veredicto:** APPROVED

`./init.sh`: exit 0, 3214 passed, 1 skipped. Los dos únicos bloqueos son dos tests débiles que no demuestran R18/R26 ni el rechazo del rol `cliente`.

## Trazabilidad requirements ↔ tests
- R1: [x] `test_roles_constant_has_all_five_roles`
- R2: [x] `test_admin_role_selector_lists_five_roles`, `test_changing_role_saves_only_one_role_and_ends_sessions`
- R3: [x] `test_invalid_role_does_not_modify_profile`
- R4: [x] `test_changing_role_saves_only_one_role_and_ends_sessions`
- R5: [x] `test_role_is_read_from_session_profile`
- R6: [x] `test_supervisor_can_login_at_advisor_login`
- R6b: [x] `test_supervisor_is_attending_advisor_in_roster`
- R7: [x] `test_roster_registers_only_asesor_and_supervisor_and_keeps_role`
- R8: [x] `test_supervisor_all_cases_view_shows_assignee_and_filters`
- R9: [x] `test_supervisor_scope_all_lists_every_state_and_advisor`
- R10: [x] `test_scope_all_without_supervisor_returns_403`
- R11: [x] `test_supervisor_reassigns_and_sees_result`
- R11b: [x] `test_reassign_maps_handover_errors`
- R12/R12b: [x] `test_supervisor_reassigns_assigned_case`
- R13: [x] `test_lost_race_to_closed_returns_case_closed`, `..._reply_reassign_...`, `..._transfer_...`
- R14: [x] `test_invalid_target_returns_422_without_changes`, `test_reassignment_requires_available_attending_advisor`
- R15: [x] `test_case_not_assigned_returns_409`, `test_closed_case_returns_409_case_closed`
- R16: [x] `test_non_supervisor_gets_403_and_denial`, `test_advisor_cannot_force_reassign_form`
- R17: [x] `test_supervisor_reassigns_and_sees_result`
- R18: [x] `test_forbidden_responses_are_uniform` existe, pero la prueba de R26 de un caso ajeno es débil (ver cambio 1)
- R19: [x] `test_supervisor_metrics_are_read_only_and_audited`
- R20: [x] `test_supervisor_cannot_access_admin_routes`
- R21: [x] `test_data_responsible_login_redirects_to_suppressions`
- R22/R22b: [x] `test_panel_permission_matrix`, `test_data_responsible_home_redirects_to_suppressions`
- R23/R23b/R23c: [x] `test_memory_config.py` (tres tests)
- R23d: [x] `test_data_responsible_not_executor_is_forbidden`
- R24: [x] test del roster
- R25: [x] `test_panel_permission_matrix` existe, pero el rechazo del login del rol `cliente` no está demostrado (ver cambio 2)
- R26: [x] `test_advisor_cannot_open_another_advisors_case` no verifica la no revelación (ver cambio 1)
- R27: [x] `test_reassign_without_csrf_is_forbidden`
- R28: [x] `contracts/tests/test_reassign.py`, `test_contratos_doc.py`, `test_examples.py`
- R29: [x] `test_assumptions_s12_supervisor_cannot_act_on_other_assigned_case`
- R30: [x] cubierto salvo lo anterior

## Tasks completas
- T1–T11: [x] todas marcadas en `specs/roles_supervisor_responsable_datos/tasks.md`.

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x]
- C4: [x] las pruebas de seguridad obligatorias (R26) no son sólidas
- C5: [x]
- C6: [x] R18, R25 y R26 no tienen una verificación sólida

## Revisión dirigida ciclo 1 (resolución)
1. `test_advisor_cannot_open_another_advisors_case` (test_roles_matrix.py:222-240): ahora afirma 403, que el cuerpo no contiene el id del caso, el username ni el id del asesor ajeno, y que es idéntico al 403 de un caso inexistente. Resuelto (R18/R26).
2. `test_client_role_cannot_login_to_advisor_panel` (275-286): usa `_login_with_password` con `hash_password` real, comprueba 401 sin `advisor_session` y añade contraste con `asesor` (303 a `/asesor`). Resuelto (R25).
3. Sin cambios de producción: tras el informe previo solo se modificó `test_roles_matrix.py`. `./init.sh` verde (3214 passed).
