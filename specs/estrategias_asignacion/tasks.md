# Tasks — #69 estrategias_asignacion

- [x] T1 — Añadir `strategy` a `CaseAutoAssignRequest` y la constante `ASSIGNMENT_STRATEGIES` en `contracts/lazaro_contracts/cases.py` y `__init__.py`. Cubre: R20.
- [x] T2 — Documentar `strategy` en `contracts/CONTRATOS.md` y actualizar `contracts/examples/case_auto_assign_request.json`. Cubre: R20.
- [x] T3 — Test de contrato: default `por_carga`, petición sin `strategy` válida, formato inválido rechazado, tabla de CONTRATOS lista `strategy` (`contracts/tests/test_auto_assign.py`). Cubre: R20.
- [x] T4 — Crear `services/handover/handover/strategies.py` con `ContextoAsignacion`, `EstrategiaAsignacion`, registro, `registrar_estrategia`, `obtener_estrategia`, `UnknownStrategy`, `PorCarga` y `RoundRobin`. Cubre: R1, R2, R3, R4, R11.
- [x] T5 — Migrar `auto_assign_least_loaded` a `auto_assign(..., strategy, at)` en el Protocol, `FakeCaseRepository` y el repositorio Postgres; añadir tabla `handover_assignment_pointer` y actualización del puntero en la misma transacción. Cubre: R6, R7, R8, R9, R10, R13, R14.
- [x] T6 — Adaptar `auto_assign_case` en `handover/domain.py` y `post_auto_assign` en `main.py` (resolver estrategia, mapear `UnknownStrategy` a `422`). Cubre: R4, R5, R13, R14.
- [x] T7 — Añadir `ASSIGNMENT_STRATEGY` a `config.py` (validador), `.env.example` y `render.yaml`. Cubre: R16.
- [x] T8 — Añadir `SettingSpec` `assignment.strategy`, `OperationalSettings.assignment_strategy` y fallback con advertencia en `administration.py`; valor actual en `admin_routes.py`. Cubre: R15, R16, R17.
- [x] T9 — Pasar `strategy` desde `_try_auto_assign` (`domain.py`) y en `adapters/handover.py` (Protocol, HTTP, Fake); conservar condiciones de modo, supresión y horario. Cubre: R12, R18, R19.
- [x] T10 — Pruebas handover `services/handover/tests/test_strategies.py`: `test_por_carga_regression` (R2), `test_round_robin_reparte_en_orden_y_vuelve_al_inicio` (R3), `test_round_robin_salta_no_validos` (R10, R11), `test_puntero_persiste_y_no_cambia_si_skipped` (R6, R8), `test_round_robin_concurrente_sin_repetir` con hilos (R7, R9), `test_registro_sin_ramas_estrategia_nueva` con una clase de prueba registrada (R4), `test_registro_coincide_con_contrato` (R4), `test_estrategia_desconocida_422` (R5), `test_sin_candidatos_queued_sin_tocar_puntero` (R14), `test_caso_asignado_por_persona_skipped` (R13). Cubre: R1-R11, R13, R14.
- [x] T11 — Migrar los tests existentes de handover que usan `auto_assign_least_loaded` a `auto_assign` con `por_carga`. Cubre: R2, R13.
- [x] T12 — Pruebas orquestador en `services/orchestrator/tests/test_auto_assign.py`: ajuste guardable/auditado/default/inválido (R15-R17), cambio en caliente entre dos escalamientos envía estrategias distintas (R18), `manual` no invoca (R19), supresión y fuera de horario no invocan (R12). Cubre: R12, R15-R19.
- [ ] T13 — Ejecutar `./init.sh` y registrar la trazabilidad R→test en `progress/impl_estrategias_asignacion.md`. Cubre: R21. (trazabilidad registrada; `./init.sh` lo ejecuta Claude al cerrar la sesión del implementer, que no tiene shell)

