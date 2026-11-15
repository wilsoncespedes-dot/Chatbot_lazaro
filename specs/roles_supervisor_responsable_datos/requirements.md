# Requirements — roles_supervisor_responsable_datos (#49)

Cinco roles: `admin`, `supervisor`, `asesor`, `responsable_datos`, `cliente`.
"Asesor atendedor" = rol `asesor` o `supervisor`.

## Roles y perfiles

### R1
El sistema DEBE admitir los roles `supervisor` y `responsable_datos` además de `admin`, `asesor` y `cliente` en la creación de perfiles (`accounts.ROLES`, `POST /admin/profiles` y el modelo `Role` de `POST /profiles`).

### R2
CUANDO un administrador autenticado cambia el rol de un perfil desde `/admin/profiles/{id}/role` a `supervisor` o `responsable_datos`, el sistema DEBE guardar ese único rol, sustituyendo el anterior, y las opciones del selector de rol DEBEN incluir los cinco roles.

### R3
SI el valor de rol recibido no es uno de los cinco roles ENTONCES el sistema DEBE rechazarlo sin modificar el perfil.

### R4
CUANDO se cambia el rol de un perfil, el sistema DEBE terminar sus sesiones activas, de modo que el nuevo rol solo se aplique tras un nuevo inicio de sesión.

### R5
El rol efectivo de cada petición DEBE leerse del perfil asociado a la sesión en el servidor; el sistema NO DEBE aceptar ningún campo de formulario, query o cabecera como fuente del rol.

## Supervisor: capacidades de asesor, vista global y reasignación

### R6
CUANDO un perfil con rol `supervisor` inicia sesión en `/asesor/login`, el sistema DEBE crear una sesión del panel de asesores.

### R6b
MIENTRAS la sesión es de `supervisor`, el sistema DEBE permitir todas las acciones de asesor (bandeja propia, responder, asignar, transferir, devolver, cerrar, presencia).

### R7
CUANDO handover recibe `POST /advisors/sync`, el sistema DEBE registrar como asesores atendedores los perfiles con rol `asesor` o `supervisor`, conservando el rol de cada uno; los perfiles `admin`, `responsable_datos` y `cliente` NO DEBEN registrarse.

### R8
CUANDO un supervisor abre `/asesor/todos`, el panel DEBE listar todas las conversaciones escaladas en cualquier estado (`open`, `timed_out`, `assigned`, `closed`) y de cualquier asesor, mostrando el asesor asignado, con los filtros de la bandeja existentes.

### R9
CUANDO handover recibe `GET /cases` con `scope=all` y un `advisor_id` cuyo rol registrado es `supervisor`, DEBE responder todos los casos de cualquier estado con `actions` solo de lo que ese supervisor puede hacer según S12.

### R10
SI handover recibe `GET /cases` con `scope=all` y un `advisor_id` que no es supervisor registrado ENTONCES DEBE responder `403` con `error=forbidden`.

### R11
CUANDO un supervisor autenticado envía la reasignación de un caso `assigned` a otro asesor registrado, el orquestador DEBE llamar a `POST /cases/{id}/reassign` de handover con el `profile.id` del supervisor de la sesión y el destino elegido.

### R11b
CUANDO handover responde a una reasignación, el orquestador DEBE mostrar el resultado al supervisor.

### R12
CUANDO handover recibe `POST /cases/{id}/reassign` de un supervisor registrado para un caso `assigned` a un asesor distinto del destino, el sistema DEBE cambiar `advisor_id` al destino con una escritura condicional que solo se aplica si el caso sigue `assigned` al asesor previo leído, sin cambiar el estado.

### R12b
CUANDO la escritura condicional de R12 se aplica, handover DEBE responder `200` con `previous_advisor_id` y `advisor_id`.

### R13
SI la escritura condicional de R12 no se aplica porque el caso fue cerrado, respondido-y-reasignado o transferido entre la lectura y la escritura ENTONCES handover DEBE responder `409` (`case_closed` si está `closed`, `case_changed` en otro caso) sin deshacer el cierre ni la nueva asignación.

### R14
SI el destino de la reasignación no es un asesor atendedor registrado, es el asesor ya asignado, o no tiene presencia efectiva `available` ENTONCES el sistema DEBE rechazarla con `422` sin modificar el caso (supuesto de la #41 aplicado a la reasignación; la presencia la comprueba el orquestador y handover valida el roster).

### R15
SI el caso reasignado está `open`, `timed_out`, `closed` o es huérfano ENTONCES handover DEBE responder `409` (`closed`: `case_closed`; resto: `case_not_assigned`), salvo caso inexistente (`404`); un huérfano `assigned` SÍ puede reasignarse por el supervisor.

### R16
SI `POST /cases/{id}/reassign` la solicita un `advisor_id` que no es supervisor registrado (incluido un asesor con rol `asesor`, un admin o un id inexistente) ENTONCES handover DEBE responder `403` con `error=forbidden` sin modificar el caso, y el orquestador DEBE responder `403` a un perfil sin rol `supervisor` antes de llamar a handover.

### R17
CUANDO una reasignación se completa o se rechaza, el sistema DEBE registrar en la auditoría quién reasignó (supervisor), de qué asesor, a qué asesor, el caso y el resultado, sin contenido de mensajes ni datos del cliente.

### R18
Las respuestas `403` del panel DEBEN usar el mismo contenido sin revelar la existencia del caso ni quién lo tiene.

## Supervisor: métricas y límites

### R19
CUANDO un supervisor abre `/asesor/metricas`, el panel DEBE mostrar las mismas métricas de `/admin/metricas` (#42) en solo lectura, sin formularios ni acciones de modificación, y registrar la lectura en la auditoría.

### R20
El supervisor NO DEBE acceder a ninguna ruta `/admin/**` (clientes, credenciales, textos, plantillas, horarios, parámetros, cuentas, perfiles, supresiones): el sistema DEBE responder como a una sesión no administrativa (redirección a login o `403`).

## Responsable de datos

### R21
CUANDO un perfil con rol `responsable_datos` inicia sesión en `/asesor/login`, el panel DEBE mostrarle únicamente la cola de supresión en `/asesor/supresiones` (casos, fecha límite y resultado) y la acción de ejecutar cada solicitud con CSRF.

### R22
MIENTRAS la sesión es de `responsable_datos`, el sistema NO DEBE permitir `/asesor` (bandeja), `/asesor/todos`, `/asesor/casos/**`, `/asesor/metricas`, acciones de caso, presencia ni `/admin/**`: el sistema DEBE responder `403` a esas rutas.

### R22b
CUANDO la sesión es de `responsable_datos` y solicita `/asesor`, el sistema DEBE redirigir a `/asesor/supresiones`.

### R23
`SUPPRESSION_EXECUTOR_ROLES` DEBE admitir los tokens `responsable_datos`, `admin` y `asesor`.

### R23b
El valor por defecto de `SUPPRESSION_EXECUTOR_ROLES` DEBE seguir siendo `admin`.

### R23c
SI `SUPPRESSION_EXECUTOR_ROLES` contiene un token distinto de los admitidos ENTONCES la configuración DEBE rechazarse.

### R23d
Un rol que no esté en `SUPPRESSION_EXECUTOR_ROLES` NO DEBE ver ni ejecutar la cola de supresión aunque la ruta exista.

### R24
El responsable de datos NO DEBE recibir presencia ni figurar en el roster de handover (R7).

## Matriz de permisos y seguridad

### R25
Cada ruta de `/asesor/**` y `/admin/**` DEBE comprobar en el servidor el rol de la sesión contra su conjunto permitido: bandeja y acciones de caso (`asesor`, `supervisor`); vista global, reasignación y métricas de solo lectura (`supervisor`); cola de supresión (roles de `SUPPRESSION_EXECUTOR_ROLES`); `/admin/**` (`admin`, y para supresiones también los roles configurados). La matriz DEBE ser verificable para los cinco roles.

### R26
SI un asesor con rol `asesor` solicita por URL o formulario un caso de otro asesor, `/asesor/todos`, `/asesor/metricas` o la reasignación ENTONCES el sistema DEBE responder `403`, sin modificar ni revelar datos del caso (prueba de seguridad obligatoria).

### R27
CUANDO una petición `POST` del panel (incluida la reasignación) llega sin token CSRF válido de la sesión, el sistema DEBE rechazarla con `403` sin llamar a handover ni modificar estado.

## Contrato y documentación

### R28
`contracts` DEBE publicar `CaseReassignRequest`/`CaseReassignResponse`, el rol en el roster (`AdvisorRosterEntry`) y el parámetro `scope` de `GET /cases` con ejemplos validados, y `contracts/CONTRATOS.md` DEBE documentar `POST /cases/{id}/reassign` y modificar S12: sustituir «Sin reasignación y sin rol supervisor» por las reglas de supervisor (R9, R12–R16), indicando que cambia la decisión de la #14.

### R29
Las reglas S12 para el rol `asesor` (responder, asignar, cerrar, transferir solo el asignado; huérfanos) DEBEN permanecer sin cambios; el supervisor NO DEBE poder responder, cerrar ni asignar un caso asignado a otro asesor, solo reasignarlo.

## Pruebas

### R30
Las pruebas DEBEN cubrir: matriz de permisos de los cinco roles (R25), reasignación concurrente (R13), auditoría (R17), CSRF (R27), configuración (R23), contratos (R28), y la prueba de seguridad de R26; `./init.sh` DEBE quedar verde.
