# Requirements — retirar_asesores_telegram

## Orchestrator: entrada por Telegram y panel

### R1
CUANDO el orquestador recibe por `POST /messages` texto que comienza con `/responder` o `/cerrar`, el sistema DEBE tratarlo como texto ordinario del remitente en el flujo habitual de privacidad y conversación.

### R2
SI el orquestador recibe `/responder` o `/cerrar` por `POST /messages` ENTONCES el sistema NO DEBE ejecutar acciones de responder, asignar ni cerrar casos a partir de ese texto.

### R3
MIENTRAS el orquestador procesa `/consultar`, el sistema DEBE conservar el comportamiento existente de la feature #26.

### R4
CUANDO un perfil autenticado con rol `asesor` utiliza una acción del panel, el orquestador DEBE enviar a handover el `profile.id` de la sesión como identidad del asesor.

### R5
CUANDO un perfil con rol `asesor` no tiene `telegram_user_id` vinculado, el panel DEBE permitirle ver y ejecutar las acciones de responder, asignar, transferir y cerrar casos que autorice handover.

### R6
SI handover no responde al autorizar o ejecutar una acción de asesor ENTONCES el orquestador NO DEBE enviar la respuesta del asesor al cliente.

### R7
CUANDO el panel reenvía a handover un mensaje nuevo del cliente de un caso asignado, el orquestador DEBE guardar y mostrar el mensaje en el historial del panel.

### R8
CUANDO el panel reenvía a handover un mensaje nuevo del cliente de un caso asignado, el sistema NO DEBE notificarlo por Telegram a asesores.

## Handover: roster, casos y reglas de autorización

### R9
CUANDO handover recibe una sincronización autenticada del roster, el sistema DEBE persistir los perfiles con rol `asesor` como asesores registrados usando `profile_id` como identificador, sin requerir `telegram_user_id`.

### R10
CUANDO handover recibe `POST /advisors/sync` sin `X-Service-Token` válido, el sistema DEBE responder `401` con `error=unauthorized`.

### R11
CUANDO handover recibe `POST /advisors/sync` con un cuerpo que no valida contra `AdvisorRosterSyncRequest`, el sistema DEBE responder `422` con `error=validation_error`.

### R12
CUANDO handover recibe `POST /advisors/sync` y la persistencia falla, el sistema DEBE responder `500` con `error=internal_error`.

### R13
CUANDO handover arranca o el orquestador cambia el roster de asesores, el sistema DEBE sincronizar el roster antes de aceptar decisiones de disponibilidad de asesores y sin depender de `ADVISOR_CHAT_IDS`.

### R14
CUANDO handover recibe `POST /handover` y existe al menos un perfil registrado con rol `asesor`, el sistema DEBE crear o reutilizar el caso abierto y responder `queued` sin enviar avisos a Telegram.

### R15
CUANDO handover recibe `POST /handover` y no existe ningún perfil registrado con rol `asesor`, el sistema DEBE responder `no_advisors`.

### R16
CUANDO el orquestador recibe `no_advisors` de handover, el sistema DEBE enviar al cliente `NO_ADVISORS_REPLY`.

### R17
MIENTRAS un caso está `open` o `timed_out`, handover DEBE permitir responder, asignar o cerrar el caso a cualquier perfil registrado con rol `asesor`.

### R18
CUANDO un asesor responde por primera vez a un caso `open` o `timed_out`, handover DEBE asignar el caso a ese perfil.

### R19
MIENTRAS un caso está `assigned` a un perfil asesor registrado, handover DEBE permitir responder, transferir o cerrar el caso solo a ese perfil.

### R20
MIENTRAS un caso está `assigned` y su perfil asignado no está en el roster de asesores, handover DEBE tratarlo como huérfano.

### R21
MIENTRAS un caso está huérfano, handover DEBE permitir que cualquier asesor registrado lo cierre.

### R22
MIENTRAS un caso está huérfano, handover DEBE denegar respuesta, asignación y transferencia a cualquier asesor registrado.

### R23
CUANDO handover rechaza una acción por identidad inválida, caso inexistente, caso cerrado o propietario distinto, el sistema DEBE conservar la precedencia de errores publicada en S12.

### R24
CUANDO un asesor cierra un caso ya cerrado, handover DEBE conservar el resultado idempotente publicado en S8.

### R25
CUANDO un asesor asigna un caso ya asignado, handover DEBE conservar el resultado publicado en S11.

### R26
CUANDO el panel lista casos para un perfil autenticado, handover DEBE devolver los casos visibles y acciones permitidas conforme a S12 y S14 usando el `profile_id`, incluyendo casos abiertos, asignados y huérfanos.

### R27
CUANDO handover recibe `POST /cases/{id}/client-message` para un caso asignado, el sistema DEBE responder con `available_in_panel` sin enviar el mensaje a Telegram.

### R28
CUANDO handover recibe `POST /cases/{id}/client-message` para un caso no asignado, el sistema DEBE responder con `not_assigned`.

### R29
CUANDO handover recibe `POST /cases/{id}/authorize`, `/reply`, `/assign`, `/transfer`, `/close` o `GET /cases`, el sistema DEBE exigir un `advisor_id` que corresponda a un perfil asesor registrado y aplicar las reglas de autorización al perfil indicado.

### R30
CUANDO handover migra un caso cuyo `advisor_id` coincide con el `telegram_user_id` de un perfil, el sistema DEBE reemplazar el valor por el `profile_id` de ese perfil.

### R31
CUANDO handover migra un caso cuyo `advisor_id` no coincide con ningún `telegram_user_id` vinculado, el sistema DEBE conservar el estado `assigned` y dejar `advisor_id` nulo para que el caso sea huérfano.

### R32
CUANDO handover migra casos existentes, el sistema DEBE conservar sus identificadores, contactos, estados, motivos, historial, fechas, mensajes y registros operativos existentes.

### R33
CUANDO handover repite la migración del roster, el sistema DEBE conservar el mismo resultado sin volver a interpretar `profile_id` como identificador Telegram.

### R34
CUANDO una instancia del orquestador procesa un handover o una acción de asesor, el sistema DEBE leer de la base de datos compartida el estado y la generación vigente del roster.

### R35
MIENTRAS el estado compartido del roster sea `pending`, cada instancia del orquestador DEBE rechazar handovers y acciones de asesor sin llamar a handover.

### R36
CUANDO handover recibe una operación que depende del roster con una generación distinta a la generación sincronizada, el sistema DEBE rechazarla con `503 roster_out_of_sync`.

### R37
SI la sincronización de roster falla ENTONCES el sistema DEBE conservar `pending` en la base de datos compartida hasta que una instancia complete una sincronización exitosa de la generación vigente.

## Contratos, configuración y despliegue

### R38
CUANDO se publica el cambio, `contracts/CONTRATOS.md` DEBE actualizar S6, S12, S13 y S14 para definir identidad por perfil, reglas, respuestas y errores.

### R39
CUANDO se publica el cambio, `contracts/CONTRATOS.md` DEBE documentar `POST /advisors/sync`, su autenticación, modelos, respuestas y códigos `401`, `422` y `500`.

### R40
CUANDO se publica el cambio, `contracts/CONTRATOS.md` DEBE actualizar las secciones de `/handover`, `/cases/{id}/authorize`, `/reply`, `/assign`, `/transfer`, `/close`, `/client-message` y `GET /cases`.

### R41
CUANDO se publica el cambio, `lazaro_contracts` DEBE definir modelos para la sincronización del roster y estados actualizados de las respuestas de handover y mensaje de cliente.

### R42
CUANDO se publican los modelos de `POST /advisors/sync`, el paquete de contratos DEBE incluir ejemplos válidos para request y response.

### R43
CUANDO se validan los contratos, las pruebas DEBEN aceptar ejemplos válidos y rechazar cuerpos inválidos de `POST /advisors/sync` y estados de respuesta no permitidos.

### R44
CUANDO se inicia handover, el sistema DEBE arrancar sin `ADVISOR_CHAT_IDS` configurada y sin validar ni registrar identificadores Telegram de asesores.

### R45
CUANDO se actualiza la configuración, el sistema DEBE retirar `ADVISOR_CHAT_IDS` y las instrucciones de `/responder` y `/cerrar` de `.env.example`, `docker-compose.yml` y `render.yaml`.

### R46
CUANDO se actualiza la documentación vigente, el sistema DEBE retirar `ADVISOR_CHAT_IDS` y las instrucciones de comandos de asesor, conservando las referencias históricas identificadas como tales.

## Seguridad y verificación

### R47
SI Telegram recibe `/responder <case_id> <texto>` desde un chat que estuvo configurado como asesor ENTONCES el sistema NO DEBE enviar ningún mensaje al cliente por ese comando.

### R48
CUANDO se verifica la feature, las pruebas DEBEN cubrir perfiles sin Telegram, migración asignada y huérfana, autorización S12, listado S14, sincronización del roster, ausencia de configuración Telegram y cambios de contrato.

### R49
CUANDO se verifica `POST /advisors/sync`, las pruebas DEBEN comprobar token ausente, token inválido, cuerpo inválido, persistencia correcta y error de persistencia.

### R50
CUANDO se verifica la coordinación de instancias, las pruebas DEBEN comprobar el bloqueo compartido durante `pending`, la sincronización exitosa y el rechazo de generaciones obsoletas.

### R51
CUANDO se verifica la feature, ninguna prueba de seguridad existente DEBE eliminarse ni debilitarse.

### R52
CUANDO se ejecuta `./init.sh` después de implementar la feature, el sistema DEBE completar todas las verificaciones sin fallos.
