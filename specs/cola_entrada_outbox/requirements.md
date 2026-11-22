# Requirements — #64 `cola_entrada_outbox`

Servicios: **orchestrator** (todo salvo lo indicado), **docker-compose** (R35) y
**contracts** (R42). El gateway de canales no cambia: sigue recibiendo
`POST /send` y respondiendo `422` ante un rechazo definitivo (#61).

Vocabulario: *inbox* = tabla `inbox` (cola de entrada); *outbox* = tabla `outbox`;
*worker de entrada* = `procesar_entrantes`; *worker de salida* = `enviar_salientes`;
*clave de conversación* = `<canal>:<external_user_id>`; *clave de destino* =
`<canal>:<destino>`; *estado terminal* = `done`, `sent` o `failed`.

## Cola de entrada (acceptance 1)

## R1
CUANDO `POST /messages` recibe un mensaje no duplicado que no es una aceptación de consentimiento, el sistema DEBE insertar la fila en `inbox` y la marca de deduplicación en la misma transacción de base de datos.

## R2
CUANDO `POST /messages` encola un mensaje, el sistema DEBE responder `202` con `{"status": "accepted"}` sin ejecutar el flujo del mensaje dentro de la petición.

## R3
El sistema NO DEBE usar `BackgroundTasks` en `services/orchestrator/orchestrator/main.py`.

## R4
CUANDO `POST /messages` recibe un mensaje cuya marca de deduplicación ya existe, el sistema DEBE responder `202` con `{"status": "duplicate"}` sin insertar ninguna fila en `inbox`.

## R5
SI la inserción en `inbox` o la marca de deduplicación falla ENTONCES el sistema DEBE revertir ambas y responder `500` `internal_error`, de modo que el reintento del gateway no sea tomado como duplicado.

## R6
CUANDO `POST /messages` recibe una aceptación de consentimiento (botón o frase de texto pendiente, #35), el sistema DEBE procesarla dentro de la petición HTTP sin insertar fila en `inbox`.

## R7
MIENTRAS el mensaje no tenga consentimiento vigente o el aviso no esté configurado y no sea una aceptación, el sistema DEBE insertar la fila en `inbox` sin guardar la marca de deduplicación persistente.

## R8
El sistema DEBE guardar en cada fila de `inbox` la clave de conversación, el canal, el identificador externo del usuario, el tipo de carga (`legacy` o `channel`) y la carga JSON original del mensaje.

## Worker `procesar_entrantes` (acceptance 2)

## R9
CUANDO el worker de entrada reclama un mensaje, el sistema DEBE seleccionarlo con `FOR UPDATE SKIP LOCKED` y marcarlo `processing` con una concesión (`locked_until`) de `WORKER_LEASE_SECONDS`, en una sola sentencia atómica.

## R10
MIENTRAS exista un mensaje anterior de la misma clave de conversación que no está en estado terminal, el sistema NO DEBE reclamar un mensaje posterior de esa conversación.

## R11
CUANDO el worker de entrada reclama un mensaje, el sistema DEBE ejecutar el flujo actual: `process_message` para carga `legacy` y `process_channel_message` (o `process_message` si el mensaje canónico es representable en el flujo histórico de Telegram, como hoy) para carga `channel`.

## R12
CUANDO el flujo de un mensaje termina sin excepción, el sistema DEBE marcarlo `done` y vaciar su carga JSON.

## R13
SI el flujo de un mensaje lanza una excepción y los intentos son menores que `INBOX_MAX_ATTEMPTS` ENTONCES el sistema DEBE devolverlo a `pending` con `next_attempt_at` calculado por el backoff y registrar el código de la excepción.

## R14
SI el flujo de un mensaje lanza una excepción y los intentos alcanzan `INBOX_MAX_ATTEMPTS` ENTONCES el sistema DEBE marcarlo `failed`, guardar el nombre de la excepción en `last_error` y vaciar su carga JSON.

## R15
SI una fila `processing` tiene `locked_until` vencido (worker caído) ENTONCES el sistema DEBE volver a reclamarla contándola como un intento más, sin perder el mensaje.

## R16
MIENTRAS un mensaje de una conversación está esperando su reintento, el sistema DEBE seguir procesando los mensajes de otras conversaciones.

## Outbox (acceptance 3)

## R17
CUANDO el bot responde a un cliente y guarda su mensaje, el sistema DEBE insertar la fila de `outbox` en la misma transacción que el mensaje guardado en `messages`.

## R18
CUANDO un asesor envía una respuesta o plantilla a un cliente y se guarda su mensaje, el sistema DEBE insertar la fila de `outbox` en la misma transacción que el mensaje guardado.

## R19
CUANDO el flujo envía un aviso sin mensaje guardado (aviso de consentimiento, texto fijo de contenido no soportado, aviso de identidad, aviso de vencimiento, aviso de supresión, respuesta a un comando de asesor), el sistema DEBE insertar una fila de `outbox` en lugar de llamar al gateway.

## R20
SI la inserción en `outbox` falla ENTONCES el sistema DEBE revertir también el mensaje guardado en `messages` de esa operación.

## R21
El sistema NO DEBE llamar a `POST /send` del gateway desde una petición HTTP del orquestador ni desde el worker de entrada.

## Worker `enviar_salientes` (acceptance 3, 4 y 5)

## R22
CUANDO el worker de salida reclama una fila de `outbox`, el sistema DEBE entregarla al gateway con `send_channel_blocks` y, si la entrega termina, marcarla `sent` y vaciar sus bloques.

## R23
SI el gateway responde con un error transitorio (`ServiceUnavailable`) ENTONCES el sistema DEBE devolver la fila a `pending` con `next_attempt_at = ahora + min(OUTBOX_BACKOFF_MAX_SECONDS, OUTBOX_BACKOFF_BASE_SECONDS * 2^(intentos-1))` multiplicado por un jitter aleatorio dentro de `±OUTBOX_BACKOFF_JITTER`.

## R24
SI una fila alcanza `OUTBOX_MAX_ATTEMPTS` intentos fallidos transitorios ENTONCES el sistema DEBE marcarla `failed` con el nombre de la excepción en `last_error`.

## R25
SI el gateway rechaza el envío con `422` (`ChannelRejected`: ventana cerrada, plantilla no aprobada, canal inactivo) ENTONCES el sistema DEBE marcar la fila `failed` con `last_error = "ChannelRejected"` sin reintentarla.

## R26
MIENTRAS exista una fila anterior de la misma clave de destino que no está en estado terminal, el sistema NO DEBE reclamar una fila posterior de ese destino.

## R27
CUANDO varias instancias del worker de salida reclaman a la vez, el sistema DEBE entregar cada fila a una sola instancia (`FOR UPDATE SKIP LOCKED` con concesión `locked_until`).

## R28
SI una fila `sending` tiene `locked_until` vencido ENTONCES el sistema DEBE volver a reclamarla y reenviarla (entrega al menos una vez).

## Panel de envíos fallidos (acceptance 6)

## R29
CUANDO un perfil `admin` o `supervisor` abre `GET /admin/envios`, el sistema DEBE listar las filas `failed` de `outbox` más recientes primero, con identificador, canal, destino enmascarado, tipo, intentos, motivo y fecha de creación.

## R30
El sistema NO DEBE mostrar en `GET /admin/envios` el texto ni los bloques del mensaje ni el destino completo.

## R31
CUANDO un perfil `admin` o `supervisor` envía `POST /admin/envios/{id}/reintentar` con CSRF válido para una fila `failed`, el sistema DEBE devolverla a `pending` con intentos en cero y `next_attempt_at` igual a la hora actual.

## R32
CUANDO se pide un reintento manual, el sistema DEBE registrar una entrada en `panel_audit` con acción `outbox_retry`, el id de la fila como `target` y el resultado (`ok`, `not_found`, `not_failed`, `forbidden`).

## R33
SI un perfil con rol `asesor` o `responsable_datos`, o sin sesión válida, accede a las rutas de `/admin/envios` ENTONCES el sistema DEBE responder `403` (o redirigir al login sin sesión) y no modificar ninguna fila.

## R34
SI el id del reintento no existe o la fila no está `failed` ENTONCES el sistema DEBE responder `404` o `409` respectivamente sin modificar ninguna fila.

## Despliegue, configuración y retención (acceptance 7)

## R35
El sistema DEBE definir en `docker-compose.yml` los servicios `procesar_entrantes` y `enviar_salientes` con la imagen `services/orchestrator/Dockerfile`, `env_file: [.env]`, `depends_on: [orchestrator]`, `restart: unless-stopped` y un `command` que ejecuta el modo correspondiente de `orchestrator.workers`.

## R36
El sistema DEBE leer de `Settings` y documentar en `.env.example` las variables `INBOX_MAX_ATTEMPTS`, `INBOX_BACKOFF_BASE_SECONDS`, `OUTBOX_MAX_ATTEMPTS`, `OUTBOX_BACKOFF_BASE_SECONDS`, `OUTBOX_BACKOFF_MAX_SECONDS`, `OUTBOX_BACKOFF_JITTER`, `WORKER_POLL_SECONDS` y `WORKER_LEASE_SECONDS` con valores por defecto seguros.

## R37
SI una de esas variables está fuera de rango (enteros menores que 1, segundos no positivos, jitter fuera de `[0, 1]`) ENTONCES el sistema DEBE rechazar la configuración al arrancar con el nombre de la variable.

## R38
CUANDO se ejecuta `purge_personal_data`, el sistema DEBE borrar las filas de `inbox` y `outbox` creadas antes del corte de retención y reportar los conteos en `deleted` con las claves `inbox` y `outbox`.

## R39
CUANDO se ejecuta la supresión de un contacto (`delete_contact_content`), el sistema DEBE borrar las filas de `inbox` y `outbox` de ese contacto (por clave de conversación, `contact_id` y destino).

## R40
El sistema DEBE crear las tablas `inbox` y `outbox` y sus índices (`IF NOT EXISTS`) al inicializar el esquema del repositorio.

## Observabilidad y contrato (acceptance 8)

## R41
El sistema NO DEBE escribir en logs, `last_error` ni el panel el texto de mensajes, bloques, identificadores de usuario ni destinos completos de las filas de cola; solo ids de fila, canal y nombre de excepción.

## R42
El sistema DEBE documentar en `contracts/CONTRATOS.md` la semántica `202` de `POST /messages`, la entrega al menos una vez, la ventana de duplicado, el bloqueo por orden y las variables de la cola.
