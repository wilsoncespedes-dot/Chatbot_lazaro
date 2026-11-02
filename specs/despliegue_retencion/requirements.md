# Requirements — despliegue_retencion (feature #28)

Alcance: integrar en el Blueprint de Render (`render.yaml`) la purga de la #27
(`scripts/purgar_datos.py`) y su configuración `PRIVACY_*`, y documentarlo en
`docs/despliegue.md`. No cambia código de servicios ni del script. No despliega
ni ejecuta purgas. Nombres de variables y semántica: `specs/privacidad_y_retencion_datos/`.

## Worker de retención (`render.yaml`)

### R1
El Blueprint DEBE declarar un servicio `retention-worker` de `type: worker`, con
`runtime: docker`, `dockerContext: .`, `dockerfilePath: services/handover/Dockerfile` y la
misma `region` que el resto de recursos.

### R2
El servicio `retention-worker` DEBE tener `dockerCommand: python purgar_datos.py --intervalo`.

### R3
El `services/handover/Dockerfile` DEBE copiar `scripts/purgar_datos.py` al archivo
`purgar_datos.py` del directorio de trabajo que ejecuta el `dockerCommand` de R2.

### R4
El servicio `retention-worker` NO DEBE declarar `healthCheckPath`, `port` ni ningún dominio
público; los únicos servicios `web` DEBEN seguir siendo `telegram-gateway` y `orchestrator`.

### R5
El servicio `retention-worker` DEBE enlazar el env group `lazaro-compartido` (fuente de
`SERVICE_TOKEN` y `APP_ENV`).

### R6
El servicio `retention-worker` DEBE obtener `HANDOVER_URL` con `fromService`
(`type: pserv`, `name: handover`, `property: hostport`), sin `value` literal.

### R7
El servicio `retention-worker` DEBE obtener `ORCHESTRATOR_URL` con `fromService`
(`type: web`, `name: orchestrator`, `property: hostport`), sin `value` literal.

### R8
El servicio `retention-worker` DEBE declarar `PRIVACY_PURGE_INTERVAL_SECONDS` y
`PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS` con los mismos valores que `.env.example`.

### R9
El servicio `retention-worker` NO DEBE declarar `DATABASE_URL`, `REDIS_URL` ni ninguna
variable `PRIVACY_*` distinta de las de R8.

## Variables `PRIVACY_*` (`render.yaml`)

### R10
El servicio `orchestrator` DEBE declarar `PRIVACY_NOTICE_TEXT`, `PRIVACY_NOTICE_VERSION`,
`PRIVACY_ACCEPT_PHRASE` y `PRIVACY_ACCEPTED_REPLY`, cada una con `sync: false` y sin `value`.

### R11
El servicio `handover` DEBE declarar `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS`,
cada una con `sync: false` y sin `value`.

### R12
El servicio `orchestrator` DEBE obtener `PRIVACY_RETENTION_DAYS` con `fromService`
(`type: pserv`, `name: handover`, `envVarKey: PRIVACY_RETENTION_DAYS`), sin `value` ni `sync`.

### R13
El Blueprint DEBE declarar `PRIVACY_RETENTION_DAYS` con `sync: false` en exactamente un
servicio (`handover`); toda otra aparición DEBE ser una referencia `fromService` a esa.

### R14
El Blueprint NO DEBE contener `value` ni `generateValue` para `PRIVACY_NOTICE_TEXT`,
`PRIVACY_NOTICE_VERSION`, `PRIVACY_ACCEPT_PHRASE`, `PRIVACY_ACCEPTED_REPLY`,
`PRIVACY_RETENTION_DAYS` ni `PRIVACY_ACTIVE_CASE_MAX_DAYS` en ningún servicio ni env group.

### R15
Los servicios `telegram-gateway`, `rag`, `timeouts-worker` y los env groups NO DEBEN declarar
ninguna variable `PRIVACY_*`.

### R16
El orchestrator NO DEBE recibir `PRIVACY_ACTIVE_CASE_MAX_DAYS` en el Blueprint.

## Documentación (`docs/despliegue.md`)

### R17
`docs/despliegue.md` DEBE listar `retention-worker` entre los recursos del Blueprint, con su
comando `python purgar_datos.py --intervalo`, el orden handover → orchestrator y que no expone
puertos.

### R18
`docs/despliegue.md` DEBE incluir en la tabla de variables `sync: false` cada una de
`PRIVACY_NOTICE_TEXT`, `PRIVACY_NOTICE_VERSION`, `PRIVACY_ACCEPT_PHRASE`,
`PRIVACY_ACCEPTED_REPLY`, `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS` con el
servicio donde se rellena.

### R19
`docs/despliegue.md` DEBE explicar que `PRIVACY_RETENTION_DAYS` se rellena solo en `handover`,
que el orchestrator lo hereda por referencia y que tras cambiarlo hay que redesplegar ambos
servicios.

### R20
`docs/despliegue.md` DEBE indicar que `PRIVACY_ACTIVE_CASE_MAX_DAYS` debe ser estrictamente
menor que `PRIVACY_RETENTION_DAYS` y que al vencer cierra y borra casos activos sin avisar al
cliente ni al asesor.

### R21
`docs/despliegue.md` DEBE indicar que el texto del aviso, la frase de aceptación, la respuesta
de confirmación, la versión y los plazos los define el propietario (con revisión legal) antes
de desplegar, y que mientras falten orchestrator y handover no arrancan en producción.

### R22
`docs/despliegue.md` NO DEBE contener un valor numérico de ejemplo para
`PRIVACY_RETENTION_DAYS` ni para `PRIVACY_ACTIVE_CASE_MAX_DAYS`.

### R23
`docs/despliegue.md` DEBE enumerar los datos personales que la purga no cubre: logs de la
plataforma Render, copias de seguridad de Postgres, `privacy_consents` y solicitudes
individuales de supresión o revocación.

## Verificación

### R24
CUANDO se ejecuta `./init.sh`, el sistema DEBE terminar con exit code 0 con los tests de
R1–R23 incluidos y los tests existentes de `scripts/tests/test_render_blueprint.py` en verde.
