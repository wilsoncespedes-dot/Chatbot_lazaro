# Requirements — robustez del estado de traspaso automático (#34)

Servicio: `orchestrator`. Se reutiliza el corte vigente de `PRIVACY_RETENTION_DAYS`.

## R1 — Outcomes vencidos
CUANDO el repositorio ejecuta `purge_personal_data(cutoff, ran_at)`, el sistema DEBE eliminar de `auto_handover_outcomes` los registros con `at < cutoff`.

## R2 — Estado de contactos purgados
CUANDO la purga identifica contactos inactivos que va a eliminar, el sistema DEBE eliminar también sus filas de `auto_handover_outcomes` y `auto_handover_streaks`.

## R3 — Atomicidad y conteos
CUANDO se purgan outcomes y rachas, el sistema DEBE hacerlo en la misma transacción que el resto de `purge_personal_data` e incluir ambas cantidades en `deleted` y en `privacy_purge_runs`.

## R4 — Recuperación ante excepción
SI `_handover` lanza una excepción durante un traspaso automático ENTONCES el sistema DEBE marcar la racha como reintentable antes de propagar la excepción.

## R5 — Compatibilidad
CUANDO se verifica esta feature, la suite DEBE probar los cortes de retención, los conteos, rollback ante error, la recuperación del estado `retry` y los flujos existentes de privacidad y handover.

## R6 — Suite completa
CUANDO se ejecuta `./init.sh` después de implementar la feature, el sistema DEBE completar la suite sin fallos.
