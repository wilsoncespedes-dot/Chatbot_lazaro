# Implementación — despliegue_retencion (#28)

## Resumen

- `render.yaml`: nuevo worker privado `retention-worker` (imagen de handover,
  `python purgar_datos.py --intervalo`, region compartida, sin puertos), y
  variables `PRIVACY_*` en `orchestrator` y `handover` con una única fuente
  `sync: false` para `PRIVACY_RETENTION_DAYS` (handover) y referencia
  `envVarKey` desde el orchestrator.
- `docs/despliegue.md`: worker en §1, variables en la tabla §2 y subsección
  §2.1 con fuente única, `active < retention`, bloqueo hasta que el propietario
  defina los valores con revisión legal y datos personales no cubiertos por la
  purga.
- `scripts/tests/test_render_retencion.py`: tests de R1–R23.
- No se tocó código de servicios, `contracts/`, `scripts/purgar_datos.py`,
  `docker-compose.yml`, `.env.example` ni el Dockerfile (ya copiaba el script).

## Trazabilidad

- R1 → `scripts/tests/test_render_retencion.py::test_r1_retention_worker_uses_handover_image_in_shared_region`
- R2 → `scripts/tests/test_render_retencion.py::test_r2_retention_worker_runs_interval_loop`
- R3 → `scripts/tests/test_render_retencion.py::test_r3_handover_image_copies_purge_script_to_workdir`
- R4 → `scripts/tests/test_render_retencion.py::test_r4_retention_worker_has_no_public_surface`
- R5 → `scripts/tests/test_render_retencion.py::test_r5_retention_worker_joins_shared_env_group`
- R6 → `scripts/tests/test_render_retencion.py::test_r6_handover_url_is_a_private_service_reference`
- R7 → `scripts/tests/test_render_retencion.py::test_r7_orchestrator_url_is_a_web_service_reference`
- R8 → `scripts/tests/test_render_retencion.py::test_r8_retention_worker_matches_env_example_mechanism_values`
- R9 → `scripts/tests/test_render_retencion.py::test_r9_retention_worker_has_minimum_privileges`
- R10 → `scripts/tests/test_render_retencion.py::test_r10_orchestrator_requests_notice_values_from_panel`
- R11 → `scripts/tests/test_render_retencion.py::test_r11_handover_requests_retention_values_from_panel`
- R12 → `scripts/tests/test_render_retencion.py::test_r12_orchestrator_references_handover_retention_days`
- R13 → `scripts/tests/test_render_retencion.py::test_r13_retention_days_has_a_single_source`
- R14 → `scripts/tests/test_render_retencion.py::test_r14_owner_values_are_never_written_in_the_blueprint`
- R15 → `scripts/tests/test_render_retencion.py::test_r15_unrelated_resources_do_not_declare_privacy_variables`
- R16 → `scripts/tests/test_render_retencion.py::test_r16_orchestrator_does_not_receive_active_case_max_days`
- R17 → `scripts/tests/test_render_retencion.py::test_r17_docs_list_retention_worker`
- R18 → `scripts/tests/test_render_retencion.py::test_r18_docs_table_lists_every_sync_false_variable`
- R19 → `scripts/tests/test_render_retencion.py::test_r19_docs_explain_single_retention_source`
- R20 → `scripts/tests/test_render_retencion.py::test_r20_docs_explain_active_case_limit`
- R21 → `scripts/tests/test_render_retencion.py::test_r21_docs_states_owner_defined_values_and_startup_block`
- R22 → `scripts/tests/test_render_retencion.py::test_r22_docs_contain_no_retention_numeric_example`
- R23 → `scripts/tests/test_render_retencion.py::test_r23_docs_list_uncovered_personal_data`
- R24 → `./init.sh` (incluye `scripts/tests/test_render_blueprint.py` sin cambios); lo ejecuta Claude al cerrar la sesión.

## Verificación pendiente

- `./init.sh` lo ejecuta Claude después de esta sesión (el implementer no
  ejecuta shell). No se desplegó ni se ejecutó `purgar_datos.py` contra
  servicios reales.

## Corrección solicitada tras ./init.sh
- Resultado: 1 failed, 1876 passed.
- Falla: `scripts/tests/test_render_retencion.py::test_r21_docs_states_owner_defined_values_and_startup_block`; el texto de `docs/despliegue.md` sí comunica que los valores deben definirse antes del despliegue, pero el salto de línea en Markdown parte el fragmento `antes de desplegar` y la aserción literal falla.
- Ajusta el test para normalizar whitespace Markdown (o verifica tokens con whitespace flexible); no debilites el requisito ni cambies el sentido de la documentación. No ejecutes shell; registra el cambio en este informe.

## Corrección aplicada

- `scripts/tests/test_render_retencion.py`: helper `_docs_text()` que une el
  documento con `" ".join(texto.split())`, de modo que los saltos de línea del
  Markdown no parten frases. Los tests de documentación R17–R23 lo usan; las
  aserciones y su sentido no cambian (R21 sigue exigiendo el fragmento literal
  `antes de desplegar`).
- No se tocó `docs/despliegue.md` ni el resto de la implementación.
- `./init.sh` pendiente de que lo ejecute Claude.
