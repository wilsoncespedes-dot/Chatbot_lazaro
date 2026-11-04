# Review — feature 39 `harness_ia_por_estado`

**Veredicto:** APPROVED

`./init.sh` (ejecutado por el reviewer): exit 0, 2573 passed, 1 skipped, 2 warnings (deprecaciones Pydantic/Starlette previas).

## Trazabilidad requirements ↔ tests
Todos los tests citados en `progress/impl_harness_ia_por_estado.md` existen en `services/orchestrator/tests/` y pasan.
- R1–R3, R8, R13, R15, R17–R19: [x] `test_harness_matrix.py` (`test_r1_r3_matrix_decision`, `test_r1_r2_matrix_is_complete_immutable_and_has_six_tools`, `test_r3_unknown_tool_is_denied_in_every_state`, `test_r8_args_sha256_is_canonical_and_hides_values`, `test_r11_r13_matches_any_normalizes_text`, `test_r15_router_prompt_neutralizes_closing_tags`, `test_r17_*`, `test_r18_*`, `test_r19_default_tool_only_for_active`)
- R4–R7, R10–R14, R16, R19–R26, R32–R34, R36–R41, R43–R55, R60, R61: [x] `test_harness_flow.py` (un `test_r<n>_…` por requisito, ver impl)
- R9, R42: [x] `test_privacy_purge.py::test_r9_r42_purge_deletes_old_tool_calls_and_keeps_suppressions`, `test_postgres_purge_deletes_tool_calls_but_not_suppression_requests`
- R27–R31: [x] `test_client_data.py` (`test_r27_r28_order_and_cliente_id_only_as_parameter`, `test_query_error_always_rolls_back_and_closes`, `test_r29_*`, `test_r30_superuser_or_bypassrls_fails_closed`, `test_r31_rls_probe_returning_a_row_fails_closed`)
- R35, R39 (placeholder), R59, R63: [x] `test_harness_config.py`
- R56, R57, R62: [x] `test_harness_eval.py::test_r56_r62_attack_cases`, `test_r56_at_least_two_cases_per_category`; `tests/data/harness_eval_cases.json` con 11 casos (acceso_entre_clientes 3, inyeccion 2, herramienta_prohibida 2, consentimiento 2, fuentes_invalidas 2)
- R58: [x] `./init.sh` verde

## Tasks completas
- T0–T20: [x]
- T21: [ ] en `specs/harness_ia_por_estado/tasks.md:560` — justificado en `progress/impl_harness_ia_por_estado.md` («Resultado de `./init.sh`»): dependía de la ejecución de `./init.sh` por Claude; la trazabilidad R1–R63 está completa y `./init.sh` está verde (confirmado por este reviewer). El leader puede marcarla `[x]` al cerrar.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0
- C2: [x] una sola feature `in_progress` (#39); estado coherente
- C3: [x] sin servicios nuevos ni imports entre servicios; sin contratos ni dependencias nuevas (`requirements.txt` sin cambios); `.env` no trackeado; variables nuevas en `.env.example` (verificado por `test_r59_env_example_declares_every_new_variable`); sin `print`/`eval`/`exec`/TODO en `harness.py`, `states.py`, `adapters/client_data.py`. `cliente_id` va solo como parámetro en `set_config(%s, %s, true)` (`adapters/client_data.py`); el `query.sql` interpolado es SQL ya validado por `validate_sql`, mismo patrón que `adapters/db_query.py:97` (#26)
- C4: [x] tests con fakes (`FakeClientData`, `ScriptedLLM`, cursor falso); pruebas de seguridad aplicables pasan
- C5: [x] sin archivos sospechosos sin trackear; la entrada de `progress/history.md` para #39 la añade el leader al cerrar
- C6: [x] spec completo; EARS revisado en `progress/specreview_harness_ia_por_estado.md`; cada R<n> con test

## Cambios requeridos
Ninguno bloqueante. Al cerrar: marcar T21 `[x]` y añadir entrada de #39 en `progress/history.md`.
