# Implementación — #69 `estrategias_asignacion`

Implementadas T1–T12 de `specs/estrategias_asignacion/tasks.md`. T13 queda
parcial: la trazabilidad está registrada aquí; `./init.sh` lo ejecuta Claude al
cerrar la sesión del implementer (OpenCode no tiene shell).

## Cambios

- `contracts/lazaro_contracts/cases.py`: `CaseAutoAssignRequest.strategy`
  (default `por_carga`, patrón `^[a-z_]{1,32}$`) y `ASSIGNMENT_STRATEGIES`.
- `contracts/lazaro_contracts/__init__.py`: exporta `ASSIGNMENT_STRATEGIES`.
- `contracts/CONTRATOS.md` y `contracts/examples/case_auto_assign_request.json`:
  documentan `strategy` y las dos estrategias.
- `services/handover/handover/strategies.py` (nuevo): `ContextoAsignacion`,
  `EstrategiaAsignacion`, `ESTRATEGIAS`, `registrar_estrategia`,
  `obtener_estrategia`, `UnknownStrategy`, `PorCarga` y `RoundRobin`.
- `services/handover/handover/adapters/repository.py`: `auto_assign(...)` en
  Protocol, Fake (con `pointers`) y Postgres; tabla
  `handover_assignment_pointer` actualizada en la misma transacción/lock.
- `services/handover/handover/domain.py` + `main.py`: resolución por registro y
  `UnknownStrategy` → `422 validation_error`.
- `services/orchestrator/orchestrator/config.py`: `ASSIGNMENT_STRATEGY`
  (default `por_carga`, validado).
- `services/orchestrator/orchestrator/administration.py` y `admin_routes.py`:
  ajuste `assignment.strategy` (enum, default, fallback y valor efectivo).
- `services/orchestrator/orchestrator/domain.py` y `adapters/handover.py`:
  la estrategia vigente se lee en cada escalamiento y viaja en
  `CaseAutoAssignRequest.strategy`.
- `.env.example` y `render.yaml`: `ASSIGNMENT_STRATEGY=por_carga`.

## Trazabilidad

- R1 → `services/handover/tests/test_strategies.py::test_interfaz_estrategia_elige_entre_candidatos`
- R2 → `services/handover/tests/test_strategies.py::test_por_carga_regression`
- R3 → `services/handover/tests/test_strategies.py::test_round_robin_reparte_en_orden_y_vuelve_al_inicio`
- R4 → `services/handover/tests/test_strategies.py::test_registro_sin_ramas_estrategia_nueva`
- R4 → `services/handover/tests/test_strategies.py::test_registro_coincide_con_contrato`
- R5 → `services/handover/tests/test_strategies.py::test_estrategia_desconocida_422`
- R6 → `services/handover/tests/test_strategies.py::test_puntero_persiste_y_no_cambia_si_skipped`
- R6 → `services/handover/tests/test_auto_assign.py::test_postgres_auto_assign_uses_lock_conditional_update_and_parameters`
- R7 → `services/handover/tests/test_strategies.py::test_round_robin_concurrente_sin_repetir`
- R7 → `services/handover/tests/test_auto_assign.py::test_postgres_auto_assign_uses_lock_conditional_update_and_parameters`
- R8 → `services/handover/tests/test_strategies.py::test_puntero_persiste_y_no_cambia_si_skipped`
- R9 → `services/handover/tests/test_strategies.py::test_round_robin_concurrente_sin_repetir`
- R10 → `services/handover/tests/test_strategies.py::test_round_robin_salta_no_validos`
- R11 → `services/handover/tests/test_strategies.py::test_round_robin_salta_no_validos`
- R12 → `services/orchestrator/tests/test_auto_assign.py::test_suppression_case_not_auto_assigned`
- R12 → `services/orchestrator/tests/test_auto_assign.py::test_out_of_hours_case_not_auto_assigned`
- R13 → `services/handover/tests/test_strategies.py::test_caso_asignado_por_persona_skipped`
- R13 → `services/handover/tests/test_auto_assign.py::test_auto_assign_unknown_404_closed_409`
- R14 → `services/handover/tests/test_strategies.py::test_sin_candidatos_queued_sin_tocar_puntero`
- R15 → `services/orchestrator/tests/test_auto_assign.py::test_admin_sets_assignment_strategy_applies_without_restart_and_audited`
- R15 → `services/orchestrator/tests/test_auto_assign.py::test_invalid_assignment_strategy_422`
- R15 → `services/orchestrator/tests/test_auto_assign.py::test_settings_page_offers_assignment_strategy`
- R16 → `services/orchestrator/tests/test_auto_assign.py::test_default_strategy_is_por_carga`
- R16 → `services/orchestrator/tests/test_auto_assign.py::test_automatic_mode_requests_assignment_with_available_advisors`
- R17 → `services/orchestrator/tests/test_auto_assign.py::test_invalid_stored_strategy_falls_back`
- R18 → `services/orchestrator/tests/test_auto_assign.py::test_strategy_change_applies_between_escalations`
- R19 → `services/orchestrator/tests/test_auto_assign.py::test_mode_manual_does_not_auto_assign`
- R20 → `contracts/tests/test_auto_assign.py::test_strategy_defaults_to_por_carga_and_is_backwards_compatible`
- R20 → `contracts/tests/test_auto_assign.py::test_strategy_rejects_invalid_format`
- R20 → `contracts/tests/test_auto_assign.py::test_assignment_strategies_constant_is_exported`
- R20 → `contracts/tests/test_auto_assign.py::test_request_table_lists_candidate_ids`
- R20 → `contracts/tests/test_auto_assign.py::test_examples_validate_against_their_models`
- R21 → pendiente de `./init.sh` (lo ejecuta Claude y añade el resultado).

## Notas para el reviewer

- El Fake del orquestador conserva `auto_assigned` como `(case_id, candidates)`
  y añade `auto_assign_strategies` en paralelo para no romper tests existentes.
- `por_carga` también persiste puntero (aunque lo ignora) para que la escritura
  sea genérica sin ramas por nombre, según `design.md`.

## Fallo de init.sh (intento 1)

4 fallos en services/handover/tests/test_repository.py (test_postgres_schema_adds_claim_and_role_columns_if_not_exists, test_postgres_repository_connects_lazily_and_once, test_postgres_repository_connects_once_with_concurrent_first_use, test_postgres_creates_requests_table_if_not_exists): el esquema ahora ejecuta 9 sentencias y los tests esperan 8 (`assert 9 == 8`). Corregir: ajustar las expectativas de esos tests a la nueva sentencia (o consolidar el DDL), sin romper nada más. Resto: 4419 passed.

## Corrección (intento 2)

Causa: la tabla nueva `handover_assignment_pointer` (R6, T5) añade una novena
sentencia `CREATE TABLE` al esquema. Los cuatro tests citados fijaban el número
de tablas en 8.

- `services/handover/tests/test_repository.py`: las cuatro aserciones de
  recuento de `CREATE TABLE` pasan de 8 a 9. No cambia ninguna otra expectativa
  (columnas de `handover_requests`, ALTER aditivos ni orden CREATE→ALTER).
- No se consolida el DDL: la tabla nueva es independiente y el diseño la exige
  como `CREATE TABLE IF NOT EXISTS handover_assignment_pointer`.

`./init.sh` queda pendiente de que Claude lo ejecute y registre el resultado.

## Resultado de init.sh

- Intento 1: 4 fallos (esquema con 9 sentencias, tests esperaban 8). Corregido por OpenCode (1 ciclo).
- Intento final: 4423 passed, 1 skipped; entorno listo. Trazabilidad R1..R20 -> test presente arriba (R21 = este resultado).
