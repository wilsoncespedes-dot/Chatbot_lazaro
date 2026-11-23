# Requisitos — Canal Gmail

## Gateway de canales

### R1 — Credenciales OAuth
El gateway DEBE almacenar `client_id`, `client_secret` y `refresh_token` del canal Gmail en el almacén de credenciales cifrado de `canales`.

### R2 — Configuración del buzón
CUANDO se cree o edite un canal `gmail_api`, el gateway DEBE validar que `config.email_address` sea una dirección de correo válida.

### R3 — Preparación de sincronización
CUANDO se sincronice por primera vez un canal Gmail activo, el gateway DEBE guardar el `historyId` actual de Gmail sin procesar correos anteriores.

### R4 — Recepción incremental
CUANDO el gateway sincronice un canal Gmail ya inicializado, DEBE obtener los mensajes nuevos de `INBOX` desde su `historyId` guardado y convertir cada correo de texto en un `NormalizedMessage` con `external_user_id` igual al remitente, `external_chat_id` igual al hilo Gmail y `external_message_id` igual al id Gmail.

### R5 — Avance de cursor
CUANDO el orquestador acepte todos los mensajes de una sincronización Gmail, el gateway DEBE avanzar el cursor de historial después de procesar todas las páginas de cambios.

### R6 — Reintento
SI el orquestador falla al aceptar un mensaje Gmail ENTONCES el gateway DEBE conservar el cursor anterior para reintentar.

### R7 — Mensajes propios
SI un cambio corresponde a un mensaje enviado desde el propio buzón ENTONCES el gateway DEBE ignorarlo.

### R8 — Respuesta en el hilo
CUANDO el gateway envíe una respuesta a un destino Gmail, DEBE responder al último remitente externo del hilo indicado y conservar `threadId`, `In-Reply-To` y `References`.

### R9 — Contenido de salida
El gateway DEBE representar los bloques de respuesta del núcleo como texto de correo.

### R10 — No descargar ni ejecutar contenido
El gateway NO DEBE incluir contenido HTML ejecutable en sus respuestas ni descargar adjuntos entrantes.

### R11 — Acceso al buzón
CUANDO se invoquen sincronización, reinicio de cursor o envío Gmail, el gateway DEBE exigir `X-Service-Token` válido.

### R12 — Estado activo
CUANDO se sincronice un canal Gmail, el gateway DEBE exigir que el canal esté configurado y activo.

### R13 — Preservar cursor vencido
SI Gmail informa que el `historyId` guardado expiró ENTONCES el gateway DEBE conservar el cursor guardado.

### R14 — Error de cursor vencido
SI Gmail informa que el `historyId` guardado expiró ENTONCES el gateway DEBE devolver el error `gmail_history_expired` que requiere reinicio administrativo.

### R15 — Protección de secretos
El gateway DEBE excluir tokens OAuth, cuerpos de correo y contenido de respuestas de los logs.

## Scripts y documentación

### R16 — Ejecución de sincronización
CUANDO se ejecute el script de sincronización, este DEBE solicitar al gateway la sincronización de cada canal Gmail activo usando `X-Service-Token`.

### R17 — Error de sincronización
SI falla la sincronización de algún canal ENTONCES el script DEBE devolver código distinto de cero.

### R18 — Configuración segura
La documentación DEBE explicar la configuración del proyecto Google Cloud, OAuth, Gmail API, scopes mínimos de lectura y envío, alta de un canal y ejecución periódica del sincronizador, e indicar que el código no conecta una cuenta por sí solo.

## Trazabilidad prevista

- R1-R2: pruebas del registro de canales y del adaptador Gmail.
- R3-R7, R13-R15: pruebas del sincronizador y repositorio de cursores.
- R8-R10: pruebas del adaptador Gmail de salida.
- R11-R12: pruebas HTTP del gateway.
- R16-R17: pruebas del script.
- R18: prueba de documentación del contrato/guía.
