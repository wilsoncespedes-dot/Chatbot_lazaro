# Review — feature #52 asignacion_automatica_carga

**Veredicto:** APPROVED

`./init.sh` tras la corrección: exit 0, 3367 passed, 1 skipped. No he repetido la suite.

## Trazabilidad requirements ↔ tests
- R1: [x] `orchestrator/tests/test_auto_assign.py::test_settings_page_offers_assignment_mode`
- R2: [x] `test_default_mode_is_manual`
- R3: [x] `test_admin_sets_assignment_mode_applies_without_restart_and_audited`
- R4: [x] `test_invalid_assignment_mode_422`
- R5: [x] `test_mode_manual_does_not_auto_assign`
- R6: [x] `test_automatic_mode_requests_assignment_with_available_advisors`
- R7: [x] `handover/tests/test_auto_assign.py::test_auto_assign_picks_least_loaded`
- R8: [x] `test_auto_assign_tie_breaks_by_advisor_id`
- R9: [x] `test_auto_assign_ignores_non_roster_candidates`
- R10: [x] `test_no_available_advisors_leaves_case_queued`
- R11: [x] `test_auto_assign_no_valid_candidates_queued`
- R12: [x] `test_auto_assign_failure_keeps_case_queued`
- R13: [x] `test_auto_assign_concurrent_no_double_assignment` y `test_postgres_auto_assign_uses_lock_conditional_update_and_parameters`
- R14: [x] `test_auto_assign_skips_changed_case`
- R15: [x] `test_auto_assign_unknown_404_closed_409`
- R16: [x] `test_suppression_case_not_auto_assigned`
- R17: [x] `test_out_of_hours_case_not_auto_assigned`
- R18: [x] `test_reescalation_does_not_reassign`
- R19: [x] `test_auto_assign_records_auto_reason`
- R20: [x] `test_auto_assigned_event_logged_without_text`
- R21: [x] `test_auto_assigned_case_in_advisor_inbox`
- R22: [x] `test_supervisor_can_reassign_auto_assigned_case`
- R23: [x] `test_advisor_becoming_available_does_not_assign_queued_case`
- R24: [x] `contracts/tests/test_auto_assign.py` (8 tests)
- R25: [x] `test_auto_assign_requires_token_401`
- R26: [x] cubierto por las pruebas anteriores y `./init.sh` verde

## Tasks completas
- T1–T20: [x] todas en `[x]` en `specs/asignacion_automatica_carga/tasks.md`. T20 está respaldada por el init.sh verde.

## Atomicidad y carreras
- `repository.py` `auto_assign_least_loaded` (Postgres, ~795-847):
  - Toma `pg_advisory_xact_lock` al inicio de la transacción.
  - Valida el roster y calcula la carga dentro de esa transacción.
  - Escribe con `UPDATE … WHERE status='open' AND advisor_id IS NULL`.
  - Inserta el registro `auto` y hace commit en la misma transacción.
  - Hace rollback si falla algo o si el caso ya cambió. Una acción humana nunca se pisa (R14).
  - La consulta usa parámetros, sin SQL concatenado.
- El fake usa lock, y la prueba con hilos comprueba que no hay doble asignación.
- La prueba de Postgres solo verifica el SQL con un cursor simulado. No ejecuta contra una base real, lo que encaja con C4.

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x]
- C4: [x]
- C5: [x]
- C6: [x]

## Cambios requeridos
Ninguno.
