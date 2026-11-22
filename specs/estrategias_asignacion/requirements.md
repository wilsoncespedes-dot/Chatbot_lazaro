# Requirements — #69 estrategias_asignacion

Servicios: **handover** (estrategias, registro, puntero), **orchestrator**
(ajuste operativo y envío de la estrategia), **contracts** (campo y constante).
Reglas de #52 que se conservan: `docs/proyecto.md` y `specs/asignacion_automatica_carga/`.

## Interfaz y registro (handover)

## R1
El sistema DEBE definir en handover la interfaz `EstrategiaAsignacion` con un método puro `elegir(candidatos, contexto)` que devuelve el `advisor_id` elegido entre los candidatos válidos.

## R2
El sistema DEBE proveer la estrategia `por_carga`, que elige al candidato con menos casos `assigned` y, a igual carga, el menor `advisor_id` lexicográfico (comportamiento idéntico al de #52).

## R3
El sistema DEBE proveer la estrategia `round_robin`, que elige al primer candidato válido cuyo `advisor_id` es mayor que el último asignado por esa estrategia (orden lexicográfico) y, si no existe, al menor de todos (vuelta al inicio).

## R4
El sistema DEBE resolver la estrategia por nombre mediante un registro (`ESTRATEGIAS: dict[str, EstrategiaAsignacion]` con decorador `registrar_estrategia`) sin ramas `if/else` por nombre en el flujo de asignación.

## R5
SI `POST /cases/{id}/auto-assign` recibe un `strategy` que no está en el registro ENTONCES handover DEBE responder `422` con `error` = `validation_error` sin modificar el caso.

## Puntero persistente y atomicidad (handover)

## R6
El sistema DEBE guardar el último asesor asignado por cada estrategia en la tabla `handover_assignment_pointer (strategy PK, last_advisor_id, updated_at)`, de modo que sobreviva a reinicios.

## R7
CUANDO una asignación automática se confirma, handover DEBE actualizar el puntero en la misma transacción y bajo el mismo candado que la escritura del caso.

## R8
SI la escritura del caso no se realiza (el caso ya no está `open` o ya tiene asesor) ENTONCES handover NO DEBE modificar el puntero.

## R9
MIENTRAS dos solicitudes de `round_robin` se ejecutan concurrentemente sobre casos distintos, handover DEBE asignarlas a asesores consecutivos del turno sin repetir ni saltar a ninguno.

## Reglas de #52 (handover y orchestrator)

## R10
El sistema DEBE aplicar `por_carga` y `round_robin` solo sobre candidatos que son atendedores del roster y que el orquestador marcó con presencia `available`, sin repetidos.

## R11
SI un candidato del turno de `round_robin` no es válido o no está disponible ENTONCES la estrategia DEBE saltarlo y elegir al siguiente en el orden circular.

## R12
SI el motivo del escalamiento es una supresión, o el momento está fuera del horario hábil configurado ENTONCES el orquestador NO DEBE invocar la asignación automática con ninguna estrategia.

## R13
SI el caso ya tiene asesor, ya no está `open` o fue cerrado entre la lectura y la escritura ENTONCES handover NO DEBE modificarlo con ninguna estrategia y DEBE responder `skipped` (o `409 case_closed` si está cerrado).

## R14
SI no hay candidatos válidos ENTONCES handover DEBE responder `queued` sin modificar el caso ni el puntero.

## Ajuste operativo (orchestrator y contracts)

## R15
El sistema DEBE ofrecer el ajuste operativo `assignment.strategy` (enum `por_carga` | `round_robin`) editable en el panel de ajustes y auditado como el resto de ajustes operativos.

## R16
MIENTRAS `assignment.strategy` no tenga valor guardado en `app_settings`, el orquestador DEBE usar `por_carga` (default de la variable `ASSIGNMENT_STRATEGY`, en `.env.example` y `config.py`).

## R17
SI el valor guardado de `assignment.strategy` es inválido ENTONCES el orquestador DEBE usar el default `por_carga` y registrar una advertencia sin romper el flujo.

## R18
CUANDO el orquestador solicita una asignación automática, DEBE leer `assignment.strategy` en ese momento y enviarla en el campo `strategy` de `CaseAutoAssignRequest`, de modo que el cambio surta efecto sin redeploy ni reinicio.

## R19
El sistema DEBE mantener `assignment.mode` con los valores `manual` y `automatica` y su default actual `manual`, y MIENTRAS el modo sea `manual` el orquestador NO DEBE invocar ninguna estrategia.

## R20
El contrato `CaseAutoAssignRequest` DEBE aceptar el campo opcional `strategy` (default `por_carga`), mantener compatibilidad con peticiones sin él, y documentarse en `contracts/CONTRATOS.md` con ejemplo actualizado.

## Pruebas

## R21
El sistema DEBE tener pruebas automatizadas que verifiquen R1-R20 (reparto round-robin, salto de no disponibles, concurrencia, cambio de estrategia en caliente y regresión de `por_carga`) con `./init.sh` verde.
