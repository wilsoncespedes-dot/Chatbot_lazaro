# Tasks — despliegue_retencion (feature #28)

- [x] T1 — Añadir el servicio `retention-worker` a `render.yaml` según design §2.1 (tipo, imagen, región, comando, `fromGroup`, URLs `hostport`, las dos variables del mecanismo). Cubre: R1, R2, R4, R5, R6, R7, R8, R9.
- [x] T2 — Añadir en `orchestrator` las cuatro variables del aviso con `sync: false` y `PRIVACY_RETENTION_DAYS` por `fromService` + `envVarKey` hacia handover. Cubre: R10, R12, R13, R16.
- [x] T3 — Añadir en `handover` `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS` con `sync: false`; no tocar env groups, gateway, rag ni `timeouts-worker`. Cubre: R11, R13, R14, R15.
- [x] T4 — `docs/despliegue.md` §1: añadir `retention-worker` (comando, orden handover → orchestrator, sin puertos). Cubre: R17.
- [x] T5 — `docs/despliegue.md` §2: añadir las seis `PRIVACY_*` a la tabla y un párrafo sobre la fuente única de `PRIVACY_RETENTION_DAYS` (redesplegar ambos), `active < retention` con cierre sin aviso, el bloqueo hasta que el dueño defina los valores con revisión legal y los datos que la purga no cubre. Sin valores numéricos de plazos. Enlazar a `specs/privacidad_y_retencion_datos/design.md` en lugar de repetirlo. Cubre: R18, R19, R20, R21, R22, R23.
- [x] T6 — Crear `scripts/tests/test_render_retencion.py` con tests del worker: R1, R2, R3 (COPY del Dockerfile), R4, R5, R6, R7, R8 (comparado con `.env.example`), R9. Cubre: R1–R9.
- [x] T7 — Añadir en el mismo archivo tests de variables: R10, R11, R12, R13 (una sola entrada `sync: false`), R14, R15, R16. Cubre: R10–R16.
- [x] T8 — Añadir en el mismo archivo tests de documentación: R17–R23 (R22 con regex). Cubre: R17–R23.
- [x] T9 — Ejecutar `./init.sh` (incluye `test_render_blueprint.py` sin cambios) y registrar el mapa R→test en `progress/impl_despliegue_retencion.md`. No desplegar ni ejecutar `purgar_datos.py` contra servicios reales. Cubre: R24.
