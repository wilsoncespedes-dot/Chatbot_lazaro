# Implementación — robustez del estado de traspaso automático (#34)

## Resumen

- `services/orchestrator/orchestrator/adapters/repository.py`:
  - `FakeRepository` guarda la fecha de cada outcome (`rag_outcome_at`) y, en
    `purge_personal_data`, borra outcomes con `at < cutoff` y outcomes/rachas de
    los contactos inactivos que ya se eliminan. Añade
    `auto_handover_outcomes` y `auto_handover_streaks` a `counts`, que también
    queda en `privacy_purge_runs`.
  - `PostgresRepository.purge_personal_data` ejecuta ambos borrados dentro de la
    misma transacción existente, con SQL parametrizado, y añade las dos
    cantidades a `counts` y a la fila de `privacy_purge_runs`.
- `services/orchestrator/orchestrator/domain.py`: `_auto_handover` marca la
  racha como no completada (`retry`) si `_handover` lanza una excepción y
  después la propaga.
- Sin rutas, contratos, variables ni dependencias nuevas.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_privacy_purge.py::test_outcomes_before_cutoff_are_purged_and_the_boundary_is_kept`
- R2 → `services/orchestrator/tests/test_privacy_purge.py::test_inactive_contact_outcomes_and_streaks_are_purged`
- R3 → `services/orchestrator/tests/test_privacy_purge.py::test_outcomes_before_cutoff_are_purged_and_the_boundary_is_kept`,
  `services/orchestrator/tests/test_privacy_purge.py::test_inactive_contact_outcomes_and_streaks_are_purged`,
  `services/orchestrator/tests/test_privacy_purge.py::test_purge_rolls_back_atomically_when_a_statement_fails`,
  `services/orchestrator/tests/test_privacy_purge.py::test_postgres_purge_uses_the_documented_order_and_parameters`
- R4 → `services/orchestrator/tests/test_auto_handover.py::test_unexpected_handover_exception_leaves_the_streak_in_retry`
- R5 → pruebas existentes de privacidad/handover conservadas:
  `services/orchestrator/tests/test_privacy_purge.py::test_messages_and_events_boundaries`,
  `::test_inactive_contact_is_deleted_with_case_links`,
  `::test_active_contacts_are_preserved`,
  `::test_operational_tables_and_consents_are_preserved`,
  `::test_response_and_purge_run_are_saved`,
  `::test_postgres_purge_uses_the_documented_order_and_parameters`
  y `services/orchestrator/tests/test_auto_handover.py::test_transient_handover_failure_is_retried_on_the_next_failure`,
  `::test_streak_survives_a_restart_and_retry_is_persisted`; más las pruebas
  nuevas de rollback y excepción.
- R6 → pendiente de que Claude ejecute `./init.sh` al cerrar la sesión del
  implementer (el implementer tiene prohibido ejecutar shell). Por eso T4 queda
  sin marcar.

## Notas

- Se actualizaron las expectativas de los conteos en las pruebas existentes de
  purga para incluir las dos claves nuevas; ninguna aserción se elimina.
- El fake refleja los mismos criterios y conteos que el repositorio PostgreSQL:
  corte por `at`, limpieza por contacto inactivo y transacción/auditoría.

Verificación: ./init.sh 2092 passed, 1 skipped. Listo para revisión de código Claude.

## Cierre
- `./init.sh`: 2092 passed, 1 skipped.
- Claude code reviewer: APPROVED (`progress/review_robustez_estado_traspaso_automatico.md`).
- Feature #34 cerrada como done.

Verificación posterior de la suite completa con Redis real y sin skips: 2093 passed.
Suite final del proyecto, con Redis de integración temporal y marca pytest registrada: 2093 passed, 0 skipped, 1 warning deprecado de Starlette/httpx.
