# Requirements — retencion_evidencia_y_privacidad_inicial (feature #57)

> Fuente: acceptance de la #57 en `feature_list.json` y decisión del dueño (2026-11-14), que
> este spec toma como **política aprobada por el dueño** y no modifica. **No** hay revisión
> legal externa ni se afirma una (`docs/proyecto.md` §11, §12). No se inventa razón social
> adicional ni correo: el responsable se nombra solo «Lázaro Software» y las solicitudes se
> hacen por el mismo chat.

## Valores aprobados (input, no se cambian)

| Valor | Aprobado |
|---|---|
| Responsable del aviso | Lázaro Software; solicitudes por el mismo chat |
| `PRIVACY_NOTICE_VERSION` | `1.0` |
| `PRIVACY_ACCEPT_PHRASE` / `PRIVACY_REJECT_PHRASE` | `ACEPTO` / `NO ACEPTO` |
| `PRIVACY_RETENTION_DAYS` | `30` |
| `PRIVACY_ACTIVE_CASE_MAX_DAYS` | `15` |
| `MEMORY_ENABLED` | `true`; memoria hasta supresión (sin purga por retención) |
| Evidencia `privacy_consents` | se borra en supresión y por antigüedad > 30 días con `occurred_at` |

## Glosario

- **Evidencia**: fila de `privacy_consents` (canal, ID externo, versión/hash del aviso,
  resultado, `occurred_at`).
- **Identidades de la solicitud**: pares `(channel, external_user_id)` de los contactos
  (`contacts`) cuyo `id` aparece en `client_sessions` del `profile_id` de la solicitud de
  supresión; incluye varios canales por perfil.
- **Corte**: `clock() - PRIVACY_RETENTION_DAYS días` (ya existente en `purge_personal_data`).

## Blueprint y configuración (Render, `.env.example`)

### R1
El Blueprint `render.yaml` DEBE declarar en el servicio `orchestrator` `PRIVACY_NOTICE_VERSION`
con `value: "1.0"`, `PRIVACY_ACCEPT_PHRASE` con `value: "ACEPTO"` y `PRIVACY_REJECT_PHRASE` con
`value: "NO ACEPTO"`.

### R2
El Blueprint DEBE declarar en `orchestrator` `PRIVACY_NOTICE_TEXT` con un `value` que nombre a
«Lázaro Software» como responsable, indique que las solicitudes se hacen por el mismo chat,
contenga la frase `ACEPTO` y no contenga ningún correo electrónico ni razón social distinta.

### R3
El Blueprint DEBE declarar en `orchestrator` `PRIVACY_ACCEPTED_REPLY` con un `value` no vacío
de como máximo 200 caracteres.

### R4
El Blueprint DEBE declarar en `handover` `PRIVACY_RETENTION_DAYS` con `value: "30"` y
`PRIVACY_ACTIVE_CASE_MAX_DAYS` con `value: "15"`, y `orchestrator` DEBE seguir heredando
`PRIVACY_RETENTION_DAYS` por `fromService`/`envVarKey` (fuente única).

### R5
El Blueprint DEBE declarar en `orchestrator` `MEMORY_ENABLED` con `value: "true"`.

### R6
`.env.example` DEBE contener exactamente los valores de R1, R2, R3, R4 y R5 para las mismas
claves (`MEMORY_ENABLED=true`), y NO DEBE contener `MEMORY_ENABLED=false`.

### R7
Los valores de `.env.example` y del Blueprint, al construir `Settings` del orchestrator y de
handover con `APP_ENV=production`, DEBEN pasar sus validaciones existentes (aviso contiene la
frase, `15 < 30`, enteros ≥ 1).

### R8
`docs/despliegue.md` DEBE declarar que los valores de §2.1 son política aprobada por el dueño
(2026-11-14), que memoria permanece hasta supresión sin purga por retención y que no existe
revisión legal externa de esta política.

## Memoria

### R9
CUANDO corre `purge_personal_data` del orchestrator, el sistema NO DEBE borrar filas de
`client_memory`, sea cual sea su antigüedad.

### R10
CUANDO se ejecuta una supresión, el orchestrator DEBE seguir borrando la fila `client_memory`
del perfil e informarla en `removed_counts["client_memory"]`.

## Supresión: evidencia de consentimiento

### R11
CUANDO se ejecuta una supresión, el orchestrator DEBE borrar todas las filas `privacy_consents`
de cada una de las identidades de la solicitud, sin importar su versión, resultado o fecha.

### R12
CUANDO se ejecuta una supresión de un perfil con sesiones en dos o más canales o contactos,
el orchestrator DEBE borrar la evidencia de todos esos canales/identidades.

### R13
CUANDO se ejecuta una supresión, el orchestrator NO DEBE borrar evidencia de identidades que no
pertenezcan a las sesiones de ese perfil.

### R14
CUANDO se ejecuta una supresión, el orchestrator DEBE incluir en `removed_counts` la clave
`privacy_consents` con el número de filas borradas (0 si no había) además de las claves
existentes.

### R15
CUANDO se ejecuta una supresión, el orchestrator DEBE borrar la evidencia en la misma
transacción que el resto de borrados y la marca `executed` de la solicitud.

### R16
SI el borrado de evidencia falla durante una supresión ENTONCES el orchestrator DEBE revertir
la transacción completa: ningún dato borrado, la solicitud sigue `pending` y no se registra
`removed_counts`.

### R17
CUANDO tras una supresión el cliente escribe de nuevo por una identidad borrada, el orchestrator
DEBE tratarlo como remitente sin consentimiento vigente y enviar el aviso de privacidad.

## Purga automática: evidencia de consentimiento

### R18
CUANDO corre `purge_personal_data` del orchestrator, el sistema DEBE borrar las filas
`privacy_consents` con `occurred_at` anterior al corte.

### R19
CUANDO corre `purge_personal_data`, el sistema NO DEBE borrar filas `privacy_consents` con
`occurred_at` igual o posterior al corte.

### R20
CUANDO corre `purge_personal_data`, el sistema DEBE incluir `privacy_consents` en el diccionario
devuelto, en `deleted` de `PrivacyPurgeResponse` y en `counts` de `privacy_purge_runs`.

### R21
CUANDO corre `purge_personal_data`, el sistema DEBE borrar la evidencia por antigüedad
independientemente de si su contacto es activo o inactivo.

### R22
CUANDO corre `purge_personal_data` con evidencia legada con `occurred_at` nulo, el sistema DEBE
usar `accepted_at` como fecha de antigüedad.

## Paridad, documentación y cierre

### R23
El repositorio falso y el de Postgres DEBEN producir los mismos conteos y borrados para R11–R14
y R18–R22 sobre el mismo escenario.

### R24
La documentación (`docs/despliegue.md`, `contracts/CONTRATOS.md`) DEBE decir que la evidencia
mínima (canal/ID externo, versión/hash del aviso, fecha) sigue el mismo plazo de 30 días y se
elimina antes si se ejecuta supresión, y DEBE dejar de listar `privacy_consents` como no
cubierta por la purga.

### R25
La documentación y los textos de la política NO DEBEN afirmar validación legal independiente;
DEBEN presentar la política como decisión del dueño pendiente de esa validación cuando
corresponda.

### R26
`./init.sh` DEBE terminar con éxito tras la implementación, con los tests de #27, #28, #35, #37
y #40 actualizados donde dependían de los valores anteriores.
