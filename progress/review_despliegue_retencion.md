# Review — feature 28 (despliegue_retencion)

**Veredicto:** APPROVED

`./init.sh` en verde según el leader (1877 passed, 1 warning); no se repitieron tests.
No se desplegó nada.

## Hallazgos de corrección

- **Blueprint `retention-worker`** (`render.yaml:158-180`): `type: worker`, `runtime: docker`,
  `region: virginia` (igual que el resto), `dockerContext: .`, imagen de handover,
  `dockerCommand: python purgar_datos.py --intervalo`. Sin `healthCheckPath`, `port` ni
  `domains`. Calca `timeouts-worker` (`render.yaml:143-156`).
- **Comando ejecutable**: `services/handover/Dockerfile:3,10` → `WORKDIR /app` +
  `COPY scripts/purgar_datos.py ./purgar_datos.py`; `/app/lazaro_contracts` disponible (l.7).
  Sin `--intervalo <n>`, el script usa `PRIVACY_PURGE_INTERVAL_SECONDS`
  (`scripts/purgar_datos.py:104-108`). Correcto.
- **Variables requeridas del worker**: el script necesita `HANDOVER_URL`, `ORCHESTRATOR_URL` y
  `SERVICE_TOKEN` (`scripts/purgar_datos.py:142-156`); llegan por `fromService … hostport`
  (l.167-176) y `fromGroup: lazaro-compartido` (l.166). `normalize_service_url` añade el
  esquema a `hostport`, igual que en `timeouts-worker`. `APP_ENV=production` del grupo activa
  la comprobación de longitud del token. Sin `DATABASE_URL`/`REDIS_URL` (mínimo privilegio).
- **Valores del mecanismo**: `86400` / `120` coinciden con `.env.example:115-116`.
- **Fuente única `PRIVACY_RETENTION_DAYS`**: `sync: false` solo en `handover`
  (`render.yaml:138-139`); el orchestrator la referencia con
  `fromService {type: pserv, name: handover, envVarKey}` sin `value`/`sync` (l.96-100).
  Coincide con `REQUIRED_IN_PRODUCTION` de `services/orchestrator/orchestrator/config.py:31-35`
  y `services/handover/handover/config.py:24-25`. `PRIVACY_ACTIVE_CASE_MAX_DAYS` solo en
  handover. Ningún `value`/`generateValue` para variables del propietario; env group y
  gateway/rag/timeouts-worker sin `PRIVACY_*`.
- **Orden y endpoints**: `docs/despliegue.md:17-18` (“handover primero, orchestrator solo si
  handover responde”) coincide con `_run_iteration` (`scripts/purgar_datos.py:83-94`).
- **Exactitud documental**: tabla `docs/despliegue.md:36-41`, §2.1 (l.52-72) cubre fuente
  única + redespliegue de ambos, `active < retention` con cierre/borrado sin aviso, bloqueo
  hasta que el propietario defina valores con revisión legal, `privacy_purge_failed`
  (coherente con el log del script, l.49/75/190) y datos no cubiertos. Sin valores numéricos
  de plazos.

## Observaciones no bloqueantes

1. `docs/despliegue.md:121-122` dice que «el gateway y handover hablan con el orchestrator por
   la red privada»; ahora también lo hace `retention-worker`. Conviene añadirlo en una
   próxima edición documental.
2. `test_r19_docs_explain_single_retention_source` comprueba `"redesplegar"` y `"ambos"` por
   separado; sería más robusto exigir la frase normalizada completa. El texto actual cumple R19.
3. Supuesto S2 (Render resuelve `envVarKey` sobre un `sync: false` de un `pserv`) sigue sin
   validarse con un despliegue real, tal como reconoce el design §6; lo verá el humano al crear
   el Blueprint.

## Trazabilidad requirements ↔ tests
(todos en `scripts/tests/test_render_retencion.py`)
- R1: [x] `test_r1_retention_worker_uses_handover_image_in_shared_region`
- R2: [x] `test_r2_retention_worker_runs_interval_loop`
- R3: [x] `test_r3_handover_image_copies_purge_script_to_workdir`
- R4: [x] `test_r4_retention_worker_has_no_public_surface`
- R5: [x] `test_r5_retention_worker_joins_shared_env_group`
- R6: [x] `test_r6_handover_url_is_a_private_service_reference`
- R7: [x] `test_r7_orchestrator_url_is_a_web_service_reference`
- R8: [x] `test_r8_retention_worker_matches_env_example_mechanism_values`
- R9: [x] `test_r9_retention_worker_has_minimum_privileges`
- R10: [x] `test_r10_orchestrator_requests_notice_values_from_panel`
- R11: [x] `test_r11_handover_requests_retention_values_from_panel`
- R12: [x] `test_r12_orchestrator_references_handover_retention_days`
- R13: [x] `test_r13_retention_days_has_a_single_source`
- R14: [x] `test_r14_owner_values_are_never_written_in_the_blueprint`
- R15: [x] `test_r15_unrelated_resources_do_not_declare_privacy_variables`
- R16: [x] `test_r16_orchestrator_does_not_receive_active_case_max_days`
- R17: [x] `test_r17_docs_list_retention_worker`
- R18: [x] `test_r18_docs_table_lists_every_sync_false_variable`
- R19: [x] `test_r19_docs_explain_single_retention_source`
- R20: [x] `test_r20_docs_explain_active_case_limit`
- R21: [x] `test_r21_docs_states_owner_defined_values_and_startup_block`
- R22: [x] `test_r22_docs_contain_no_retention_numeric_example`
- R23: [x] `test_r23_docs_list_uncovered_personal_data`
- R24: [x] `./init.sh` verde (1877 passed), incluye `test_render_blueprint.py` sin cambios

## Tasks completas
- T1–T9: [x] (todas en `[x]` en `specs/despliegue_retencion/tasks.md`)

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] una sola feature `in_progress` (#28).
- C3: [x] sin código de servicios nuevo ni dependencias nuevas; sin secretos (solo `sync: false`,
  `generateValue` para `SERVICE_TOKEN`); variables nuevas ya en `.env.example`.
- C4: [x] tests de configuración/documentación sin red ni BD reales.
- C5: [x] estado reflejado; cierre de sesión pendiente del leader.
- C6: [x] spec completo, EARS, tasks `[x]`, cada `R<n>` con test.

## Cambios requeridos
Ninguno.
