# Review — feature #14 autorizacion_asesores

**Veredicto:** APPROVED

## Verificación
- `.venv/Scripts/python -m pytest services/handover services/orchestrator`: 346 passed.
- `./init.sh`: exit 0, 887 passed, entorno OK.
- Writer: deepseek/deepseek-flash (sesión `ses_e6a8ab727ffes1iFGtW33EjFUR`, export sin otros modelos; ver `progress/impl_autorizacion_asesores.md`).

## Trazabilidad requirements ↔ tests
- R1-R55: [x] cada R tiene al menos un test existente y en verde (mapa en `progress/impl_autorizacion_asesores.md` §Trazabilidad; tests en `services/handover/tests/{test_authorization,test_assign_close_races,test_repository,test_security,test_startup,test_cases}.py` y `services/orchestrator/tests/{test_authorization,test_security,test_case_reply}.py`).
- R36: [x] únicas líneas eliminadas en tests existentes: `"333"`→`"111"` (T7), `== 2`→`== 3` (T9), `[404,409,500]`→`[403,404,409,500]` (T36), `make_env` con parámetros opcionales. Ninguna aserción eliminada ni relajada.

## Tasks completas
- 79/80 `[x]`, en el orden de ejecución declarado.
- T7b: `[ ]` justificado. `services/handover/tests/test_timeout_races.py` no existe y la #12 (`vencimiento_automatico`) sigue `blocked`; anotado en `tasks.md` y en `progress/impl_autorizacion_asesores.md`. Correcto.
- T9: 2→3 `CREATE TABLE` en vez de 3→4 (la #11 no está implementada); documentado. T71 comprueba igualmente el esquema una sola vez.

## Decisiones comprobadas
- C5: `orchestrator/domain.py` `reply_to_case` mapea `case_closed`→`CaseClosed` 409 sin `_record_forbidden` ni envío (R26, R53).
- Escrituras condicionales: `repository.py` `assign_if_unassigned` / `close_if_still_allowed` con `UPDATE ... RETURNING case_id`, solo `%s`, variante `advisor_id IS NULL` para huérfanos nulos. Un cierre que pierde frente a una asignación ajena relee y responde 403 (`_resolve_lost_close`, R55).
- Solo los 403 pasan por `_deny`→`add_denial`; un fallo de `add_denial` sube al handler genérico → `500 internal_error` (`main.py:127`).
- Sin contacto vinculado: solo `logger.warning("advisor_forbidden ...")`, sin evento (R30).
- `lifespan` → `log_orphan_cases` en el threadpool; cuenta `None`; `WARNING orphan_cases_check_failed` sin el texto de la excepción; `create_app` no cuenta.
- `threading.Lock` alrededor de todo `_run`, incluido `_connection()` (R44, R45).
- Huérfanos: cualquier asesor registrado puede cerrarlos (`can_act_on_case`); `reply` y `assign` reciben 403.
- Fallo cerrado: `HttpHandoverClient.authorize` → `ServiceUnavailable` → `502 upstream_error` en cualquier respuesta no contemplada.

## Seguridad
- Los logs no contienen texto ni ids de clientes. Solo aparecen `case_id`/`advisor_id` en `advisor_forbidden` (lo exige R30) y `case_id` en `authorize_failed` (mismo patrón que `assign_failed`). Ni secretos ni dependencias nuevas. No hay código externo.
- `contracts/` sin tocar por la #14: todos sus archivos se modificaron antes de las reviews de la #13 y la #17 (2026-10-31), y los tests de la #14 son del 2026-11-01.

## Checkpoints
- Arquitectura en 3 capas respetada (dominio / adaptadores / main); contratos consumidos sin modificar; tests presentes para cada archivo modificado: [x]

## Notas no bloqueantes
- `orchestrator/adapters/handover.py`: hay líneas en blanco de más entre clases y al final del archivo, y también al final de `orchestrator/domain.py`. Es solo estilo y no afecta a `init.sh`.
