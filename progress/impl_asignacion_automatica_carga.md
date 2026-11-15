# Implementación #52 asignacion_automatica_carga

## Resumen
- `contracts/`: modelos `CaseAutoAssignRequest`/`CaseAutoAssignResponse`, ejemplos, sección de `CONTRATOS.md` y supuesto S16.
- `handover`: `POST /cases/{id}/auto-assign`, elección por carga con desempate lexicográfico, escritura condicional bajo `pg_advisory_xact_lock` y registro `auto` en `handover_auto_assignments`.
- `orchestrator`: ajuste `assignment.mode` (`manual` por defecto) editable y auditado desde `/admin/ajustes`; candidatos por presencia efectiva; llamada automática solo en modo `automatica`, sin supresión y dentro de horario; eventos `auto_assigned`/`auto_assign_failed`.
- No se añadieron dependencias ni servicios.

## Trazabilidad
- R1 → `services/orchestrator/tests/test_auto_assign.py::test_settings_page_offers_assignment_mode` y `::test_admin_sets_assignment_mode_applies_without_restart_and_audited`
- R2 → `services/orchestrator/tests/test_auto_assign.py::test_default_mode_is_manual`
- R3 → `services/orchestrator/tests/test_auto_assign.py::test_admin_sets_assignment_mode_applies_without_restart_and_audited`
- R4 → `services/orchestrator/tests/test_auto_assign.py::test_invalid_assignment_mode_422`
- R5 → `services/orchestrator/tests/test_auto_assign.py::test_mode_manual_does_not_auto_assign`
- R6 → `services/orchestrator/tests/test_auto_assign.py::test_automatic_mode_requests_assignment_with_available_advisors`
- R7 → `services/handover/tests/test_auto_assign.py::test_auto_assign_picks_least_loaded`
- R8 → `services/handover/tests/test_auto_assign.py::test_auto_assign_tie_breaks_by_advisor_id`
- R9 → `services/handover/tests/test_auto_assign.py::test_auto_assign_ignores_non_roster_candidates`
- R10 → `services/orchestrator/tests/test_auto_assign.py::test_no_available_advisors_leaves_case_queued`
- R11 → `services/handover/tests/test_auto_assign.py::test_auto_assign_no_valid_candidates_queued`
- R12 → `services/orchestrator/tests/test_auto_assign.py::test_auto_assign_failure_keeps_case_queued`
- R13 → `services/handover/tests/test_auto_assign.py::test_auto_assign_concurrent_no_double_assignment` y `::test_postgres_auto_assign_uses_lock_conditional_update_and_parameters`
- R14 → `services/handover/tests/test_auto_assign.py::test_auto_assign_skips_changed_case`
- R15 → `services/handover/tests/test_auto_assign.py::test_auto_assign_unknown_404_closed_409`
- R16 → `services/orchestrator/tests/test_auto_assign.py::test_suppression_case_not_auto_assigned`
- R17 → `services/orchestrator/tests/test_auto_assign.py::test_out_of_hours_case_not_auto_assigned`
- R18 → `services/orchestrator/tests/test_auto_assign.py::test_reescalation_does_not_reassign`
- R19 → `services/handover/tests/test_auto_assign.py::test_auto_assign_records_auto_reason`
- R20 → `services/orchestrator/tests/test_auto_assign.py::test_auto_assigned_event_logged_without_text`
- R21 → `services/orchestrator/tests/test_auto_assign.py::test_auto_assigned_case_in_advisor_inbox`
- R22 → `services/orchestrator/tests/test_auto_assign.py::test_supervisor_can_reassign_auto_assigned_case`
- R23 → `services/orchestrator/tests/test_auto_assign.py::test_advisor_becoming_available_does_not_assign_queued_case`
- R24 → `contracts/tests/test_auto_assign.py` y `services/handover/tests/test_auto_assign.py`
- R25 → `services/handover/tests/test_auto_assign.py::test_auto_assign_requires_token_401`
- R26 → pruebas anteriores; `./init.sh` lo ejecuta Claude al cerrar la sesión (T20 pendiente de esa ejecución).

## Notas
- La atomicidad de Postgres serializa con `pg_advisory_xact_lock` y un `UPDATE ... WHERE status='open' AND advisor_id IS NULL`; nunca pisa una acción humana.
- Los casos que quedan en cola no se reparten solos cuando un asesor recupera disponibilidad (S1/R23).

## `init.sh` intento 1 — fallo

- Resultado: 1 failed, 3366 passed, 1 skipped. Falla `contracts/tests/test_auto_assign.py::test_route_documents_exposer_caller_models_and_token`: el contrato corta en dos líneas la frase que el test compara como subcadena exacta. Corregir solo la discrepancia de documentación/test y volver a ejecutar `./init.sh`.

## Corrección del fallo de `init.sh` intento 1

- `contracts/CONTRATOS.md` §`POST /cases/{id}/auto-assign`: se reunió en una sola línea la frase `` `{id}` es el `case_id` (identificador, 1–64 caracteres) `` para que coincida con la subcadena exacta que comprueba `test_route_documents_exposer_caller_models_and_token` (R24).
- No se modificó ningún test, modelo, ejemplo ni comportamiento de los servicios; el resto de secciones publicadas queda intacto.
- T20 sigue pendiente de la ejecución de `./init.sh` por Claude en el cierre de sesión.

## Verificación final

`bash ./init.sh`: exit 0, 3367 passed, 1 skipped y 2 avisos de deprecación.
T1–T20 completas; queda pendiente la revisión de código Claude.
