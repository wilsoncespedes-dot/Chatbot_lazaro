# #52 asignacion_automatica_carga — Requirements

Servicios: **orchestrator** (modo, presencia, elegibilidad, panel) y **handover**
(elección por carga y asignación atómica). `contracts/` gana dos modelos.

Definiciones:

- **Modo de asignación**: ajuste operativo `assignment.mode` ∈ {`manual`, `automatica`}.
- **Asesor disponible**: perfil atendedor (`ATTENDING_ADVISOR_ROLES`) con presencia efectiva `available` (#49).
- **Carga**: número de casos del asesor en estado `assigned` (no cerrados).
- **Caso elegible**: caso recién escalado, `open` y sin asesor, que no es de supresión y se escala dentro del horario de atención.

## Modo (orchestrator)

### R1
El sistema DEBE ofrecer en `/admin/ajustes` el ajuste `assignment.mode` con los valores `manual` y `automatica`.

### R2
El sistema DEBE usar `manual` como valor por defecto cuando no hay valor guardado ni `ASSIGNMENT_MODE` en el entorno.

### R3
CUANDO un administrador guarda `assignment.mode`, el sistema DEBE aplicar el nuevo valor a los escalamientos siguientes sin reiniciar el servicio y registrar el cambio en `panel_audit`.

### R4
SI el valor enviado para `assignment.mode` no es `manual` ni `automatica` ENTONCES el sistema DEBE rechazarlo con `422` sin modificar el valor guardado.

### R5
MIENTRAS el modo es `manual`, el sistema NO DEBE invocar la asignación automática y DEBE dejar los casos escalados sin asignar, como hoy.

## Asignación por carga

### R6 (orchestrator)
MIENTRAS el modo es `automatica`, CUANDO handover responde `queued` a un escalamiento con caso elegible, el orquestador DEBE solicitar la asignación automática enviando los ids de los asesores disponibles.

### R7 (handover)
CUANDO handover recibe una solicitud de asignación automática, DEBE asignar el caso al candidato registrado con menor carga.

### R8 (handover)
SI varios candidatos tienen la misma carga ENTONCES handover DEBE elegir el de menor `advisor_id` en orden lexicográfico.

### R9 (handover)
El sistema DEBE ignorar en la elección a los candidatos que no estén en el roster de handover o que no sean asesores atendedores.

### R10 (orchestrator)
SI no hay ningún asesor disponible ENTONCES el orquestador NO DEBE llamar a la asignación automática y el caso DEBE quedar `open` sin asignar en la cola actual con su flujo de espera y vencimiento.

### R11 (handover)
SI la lista de candidatos de la solicitud queda vacía tras filtrar (R9) ENTONCES handover DEBE responder `status="queued"` sin modificar el caso.

### R12 (orchestrator)
SI falla la llamada de asignación automática (`ServiceUnavailable` o error) ENTONCES el orquestador NO DEBE propagar el error al cliente, DEBE registrar el evento `auto_assign_failed` y el caso DEBE seguir en cola.

## Atomicidad

### R13 (handover)
El sistema DEBE elegir y asignar en una sola transacción serializada, de modo que dos asignaciones automáticas simultáneas cuenten la carga ya confirmada por la otra y no asignen el mismo caso dos veces.

### R14 (handover)
SI el caso ya no está `open` y sin asesor al ejecutar la escritura (asignado, respondido o cerrado por una persona) ENTONCES handover NO DEBE modificarlo y DEBE responder `status="skipped"`.

### R15 (handover)
SI el caso no existe ENTONCES handover DEBE responder `404` `not_found`; SI está cerrado, `409` `case_closed`.

## Exclusiones

### R16 (orchestrator)
El orquestador NO DEBE solicitar asignación automática para casos creados por la herramienta de supresión; DEBEN quedar en su cola como hoy.

### R17 (orchestrator)
MIENTRAS el horario de atención está habilitado y el instante del escalamiento está fuera de él, el orquestador NO DEBE solicitar asignación automática y el caso DEBE seguir en cola con el aviso de fuera de horario actual.

### R18 (orchestrator)
SI el caso reutilizado ya estaba asignado (el cliente reescala con un caso activo) ENTONCES el sistema NO DEBE reasignarlo automáticamente.

## Registro y visibilidad

### R19 (handover)
CUANDO handover asigna automáticamente un caso, DEBE guardar un registro con `case_id`, `advisor_id`, motivo `auto` y fecha, en la misma transacción que la asignación.

### R20 (orchestrator)
CUANDO handover responde `assigned` a la asignación automática, el orquestador DEBE registrar el evento `auto_assigned` con `case:<id> advisor:<id> reason:auto`, sin texto del cliente.

### R21 (orchestrator)
CUANDO un caso fue asignado automáticamente, la bandeja `/asesor` del asesor asignado DEBE mostrarlo como caso asignado a él.

### R22 (orchestrator)
CUANDO un supervisor reasigna un caso asignado automáticamente, el sistema DEBE permitirlo con la reasignación existente (#49), sin reglas adicionales.

## Supuesto sobre la cola

### R23 (orchestrator, handover)
CUANDO un asesor vuelve a estar disponible o cambia su presencia, el sistema NO DEBE asignar automáticamente casos que ya estaban en cola; solo un asesor (al tomarlo) o un supervisor (al reasignar/asignar) DEBEN poder asignarlos.

## Configuración y contrato

### R24 (contracts, handover)
El sistema DEBE exponer `POST /cases/{case_id}/auto-assign` con `X-Service-Token` válido y cuerpo `CaseAutoAssignRequest{candidate_ids}` (1–200 ids), y responder `CaseAutoAssignResponse{status: assigned|queued|skipped, case_id, advisor_id|null}`.

### R25 (handover)
SI la petición a `POST /cases/{case_id}/auto-assign` llega sin `X-Service-Token` válido ENTONCES el sistema DEBE responder `401` `{"error": "unauthorized"}`.

## Pruebas

### R26
El sistema DEBE tener pruebas que cubran modo manual sin cambios, reparto por carga, desempate, sin asesores disponibles, concurrencia, supresión, fuera de horario y `./init.sh` verde.
