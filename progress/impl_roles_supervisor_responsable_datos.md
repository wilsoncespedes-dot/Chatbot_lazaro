# Implementación — roles_supervisor_responsable_datos (#49)

## Resumen

Continuado el trabajo parcial de la sesión anterior (sin revertir ni duplicar). Además de las piezas ya presentes (contratos, handover, rutas/dominio del orquestador), se corrigieron los fallos del informe y se completaron los tests de trazabilidad.

## Correcciones aplicadas

- `contracts/CONTRATOS.md` S12: se restauraron las reglas publicadas de reply/close/assign,
  precedencia de errores, fallo cerrado, limitación de identidad, casos huérfanos y
  retirada de asesor, y se añadieron `case_not_assigned` y `case_changed` con el formato
  que exigen los tests. Se mantiene la prohibición de que el supervisor responda, cierre
  o asigne casos ajenos (solo reasigna).
- `contracts/CONTRATOS.md` `POST /cases/{id}/reassign`: la prosa documenta ahora
  `409 case_not_assigned` y `409 case_changed` con backticks, además de la escritura
  condicional.
- `contracts/examples/case_list_item.json` + mapeo en `contracts/tests/test_examples.py`:
  cada modelo de contrato tiene ejemplo.
- `services/handover/tests/test_reassign.py`: la prueba de bandeja propia usa
  `created_at` explícitos para verificar el orden documentado
  (`created_at`, luego `case_id`) sin depender de ids.
- `services/orchestrator/tests/test_roles_matrix.py`: la invalidación de sesiones
  comprueba que desaparecen las del perfil cambiado y se conserva la del admin; se
  añaden pruebas de login real en `/asesor/login` para supervisor (R6) y responsable de
  datos (R21).
- `services/orchestrator/orchestrator/advisor_routes.py`: la cola de supresión del
  responsable no muestra el enlace de la bandeja (`show_inbox=False`).

## Trazabilidad R<n> → test

- R1 → `services/orchestrator/tests/test_roles_matrix.py::test_roles_constant_has_all_five_roles`; `test_accounts.py` (parámetro de roles).
- R2 → `test_roles_matrix.py::test_admin_role_selector_lists_five_roles`, `::test_changing_role_saves_only_one_role_and_ends_sessions`.
- R3 → `test_roles_matrix.py::test_invalid_role_does_not_modify_profile`.
- R4 → `test_roles_matrix.py::test_changing_role_saves_only_one_role_and_ends_sessions`; `test_accounts.py::test_postgres_sessions_filter_by_roles_and_delete_by_profile`.
- R5 → `test_roles_matrix.py::test_role_is_read_from_session_profile`; `test_accounts.py` (get_session_for_roles).
- R6 → `test_roles_matrix.py::test_supervisor_can_login_at_advisor_login`.
- R6b → `test_roles_matrix.py::test_supervisor_is_attending_advisor_in_roster`; `services/handover/tests/test_reassign.py::test_scope_mine_keeps_existing_behavior_for_supervisor`.
- R7 → `services/handover/tests/test_reassign.py::test_roster_registers_only_asesor_and_supervisor_and_keeps_role`; `test_advisor_roster.py`.
- R8 → `services/orchestrator/tests/test_panel_reassign.py::test_supervisor_all_cases_view_shows_assignee_and_filters`, `::test_all_cases_filters_by_channel_and_assignment`.
- R9 → `services/handover/tests/test_reassign.py::test_supervisor_scope_all_lists_every_state_and_advisor`, `::test_scope_all_respects_case_list_limit`.
- R10 → `services/handover/tests/test_reassign.py::test_scope_all_without_supervisor_returns_403`.
- R11 → `services/orchestrator/tests/test_panel_reassign.py::test_supervisor_reassigns_and_sees_result`.
- R11b → `test_panel_reassign.py::test_reassign_maps_handover_errors`.
- R12, R12b → `services/handover/tests/test_reassign.py::test_supervisor_reassigns_assigned_case`, `::test_supervisor_can_reassign_orphan_case`.
- R13 → `test_reassign.py::test_lost_race_to_closed_returns_case_closed`, `::test_lost_race_to_reply_reassign_returns_case_changed`, `::test_lost_race_to_transfer_returns_case_changed`.
- R14 → `test_reassign.py::test_invalid_target_returns_422_without_changes`; `test_panel_reassign.py::test_reassignment_requires_available_attending_advisor`, `::test_reassign_to_supervisor_target_is_allowed`.
- R15 → `test_reassign.py::test_case_not_assigned_returns_409`, `::test_closed_case_returns_409_case_closed`, `::test_missing_case_returns_404`.
- R16 → `test_reassign.py::test_non_supervisor_gets_403_and_denial`, `::test_supervisor_role_is_read_from_roster_not_from_current_state`; `test_roles_matrix.py::test_advisor_cannot_force_reassign_form`.
- R17 → `test_panel_reassign.py::test_supervisor_reassigns_and_sees_result` (auditoría con from/to), `::test_reassign_maps_handover_errors`.
- R18 → `test_panel_reassign.py::test_forbidden_responses_are_uniform`.
- R19 → `test_panel_reassign.py::test_supervisor_metrics_are_read_only_and_audited`, `::test_supervisor_metrics_rejects_invalid_days`.
- R20 → `test_roles_matrix.py::test_supervisor_cannot_access_admin_routes`.
- R21 → `test_roles_matrix.py::test_data_responsible_login_redirects_to_suppressions`, `::test_data_responsible_sees_only_suppression_queue`.
- R22 → `test_roles_matrix.py::test_panel_permission_matrix`.
- R22b → `test_roles_matrix.py::test_data_responsible_home_redirects_to_suppressions`.
- R23 → `test_memory_config.py::test_r54_suppression_roles_accept_admin_asesor_and_responsable`, `::test_r54_suppression_roles_must_be_allowed`.
- R23b → `test_memory_config.py::test_r23b_suppression_roles_default_is_admin`.
- R23c → `test_memory_config.py::test_r54_suppression_roles_must_be_allowed`.
- R23d → `test_roles_matrix.py::test_data_responsible_not_executor_is_forbidden`.
- R24 → `services/handover/tests/test_reassign.py::test_roster_registers_only_asesor_and_supervisor_and_keeps_role`.
- R25 → `test_roles_matrix.py::test_panel_permission_matrix`.
- R26 → `test_roles_matrix.py::test_advisor_cannot_force_supervisor_urls`, `::test_advisor_cannot_open_another_advisors_case`, `::test_advisor_cannot_force_reassign_form`.
- R27 → `test_roles_matrix.py::test_reassign_without_csrf_is_forbidden`.
- R28 → `contracts/tests/test_reassign.py`, `contracts/tests/test_models.py` (AdvisorRosterEntry), `contracts/tests/test_contratos_doc.py::test_reassign_*`, `::test_assumptions_s14_documents_scope_all`; `contracts/tests/test_examples.py`.
- R29 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_supervisor_cannot_act_on_other_assigned_case`; `services/handover/tests/test_reassign.py::test_scope_mine_keeps_existing_behavior_for_supervisor`.
- R30 → conjunto anterior completo; la verificación final la ejecuta Claude con `./init.sh`.

## Estado

No se ejecutaron comandos (límite del writer). Claude ejecutará `./init.sh` y añadirá el resultado a este informe.

## Corrección 1 (tras pytest dirigido)

`contracts` + `services/handover`: verdes. `services/orchestrator -x` falla en
`tests/test_panel_reassign.py::test_reassignment_requires_available_attending_advisor`:
`UsernameTaken` ('target1') porque el helper `_target` de ese test usa un username fijo y se
llama dos veces. Corregir el helper (username único por llamada). Después, ejecutar solo
`python -m pytest services/orchestrator/tests/test_panel_reassign.py services/orchestrator/tests/test_roles_matrix.py -q`
y corregir lo que falle; no tocar nada más. No ejecutar init.sh.

## Corrección aplicada

- `services/orchestrator/tests/test_panel_reassign.py`: `_target` genera un username único
  por llamada con un contador de módulo (`targetN`), eliminando el `UsernameTaken` al crear
  dos destinos en el mismo test. La vista global comprueba `advisor.username` en lugar del
  nombre fijo `target1`, para no depender del orden de las llamadas.
- Sin cambios fuera de ese archivo de test. La verificación dirigida y `./init.sh` quedan a
  cargo de Claude; no se ejecutaron comandos.

## Verificación por el leader

`bash ./init.sh`: exit 0; 3214 passed, 1 skipped, 2 avisos de deprecación.
La revisión de código de Claude queda pendiente del restablecimiento de su cuota.

## Corrección tras CHANGES_REQUESTED (ciclo 1)

Cambios aplicados solo en `services/orchestrator/tests/test_roles_matrix.py`:

- `test_advisor_cannot_open_another_advisors_case` (R18, R26): ahora afirma que el 403
  no contiene el id del caso (`case-other`), ni el nombre (`asesor2`) ni el id (`701`)
  del asesor ajeno, y que su cuerpo es idéntico al 403 de un caso inexistente, de modo
  que no se revela la existencia del caso.
- `test_client_role_cannot_login_to_advisor_panel` (R25): crea el perfil `cliente` con
  `hash_password(...)` y la contraseña correcta mediante `_login_with_password`, comprueba
  `401`, ausencia de cookie `advisor_session` y el mensaje de login rechazado; además
  contrasta con un `asesor` de la misma contraseña que sí recibe `303` y cookie. Así el
  rechazo depende del rol y no de credenciales inválidas.

Trazabilidad actualizada: R18 → `test_advisor_cannot_open_another_advisors_case`;
R25 → `test_client_role_cannot_login_to_advisor_panel`; R26 →
`test_advisor_cannot_open_another_advisors_case`.

Sin cambios fuera de ese archivo de test. La verificación dirigida y `./init.sh` quedan a
cargo de Claude; no se ejecutaron comandos.

## Resultado init.sh (ciclo 1)
`bash ./init.sh`: 3214 passed, 1 skipped, exit OK. Trazabilidad R18/R25/R26 -> tests corregidos.
