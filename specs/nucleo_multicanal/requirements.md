# Requirements — nucleo_multicanal (feature #36)

> Fuente de verdad: acceptance de la feature #36 en `feature_list.json` y fase
> 1 de `docs/especificacion.md`. La integración con un proveedor real de
> WhatsApp pertenece a #43; aquí se usa `FakeWhatsAppAdapter`.

## R1 — Mensaje normalizado

CUANDO un adaptador recibe un mensaje entrante de Telegram o WhatsApp, el
sistema DEBE convertirlo al mismo modelo normalizado con canal, identificador
externo de usuario y chat, identificador externo del mensaje, tipo, contenido
de texto o botón cuando aplique, y fecha UTC de recepción.

## R2 — Respuesta abstracta

CUANDO el núcleo produce una respuesta, el sistema DEBE representarla como
bloques independientes del canal de texto, opciones, lista, enlace o plantilla,
con los límites de cantidad y longitud definidos en `docs/especificacion.md`.

## R3 — Compatibilidad Telegram

CUANDO el gateway procesa un update válido de Telegram, el adaptador Telegram
DEBE conservar el comportamiento existente de recepción y envío.

## R4 — Adaptador falso de WhatsApp

CUANDO un test inyecta `FakeWhatsAppAdapter`, el adaptador DEBE normalizar
mensajes, informar capacidades y recibir bloques de respuesta sin abrir red
real ni requerir secretos de proveedor.

## R5 — Deduplicación del mismo canal

CUANDO el núcleo recibe un mensaje cuyo par `(canal, mensaje_externo_id)` ya
fue procesado, el sistema DEBE descartarlo sin ejecutar otra vez el flujo.

## R6 — Aislamiento entre canales

CUANDO llega el mismo `mensaje_externo_id` por dos canales distintos, el
sistema DEBE procesar una vez el mensaje de cada canal.

## R7 — Consulta de capacidad

CUANDO el sistema va a enviar texto libre, el núcleo DEBE consultar primero
la capacidad informada por el adaptador de ese canal.

## R8 — Ventana de WhatsApp

MIENTRAS la ventana de atención de WhatsApp de 24 horas esté cerrada, el
adaptador DEBE rechazar texto libre.

## R9 — Plantillas aprobadas

MIENTRAS la ventana de atención de WhatsApp esté cerrada, el adaptador DEBE
permitir únicamente el envío de una plantilla aprobada.

## R10 — Equivalencia

CUANDO los adaptadores falsos procesan el mismo mensaje lógico y la misma
respuesta abstracta, el sistema DEBE conservar el contenido y significado,
permitiendo que cada adaptador represente los bloques según las capacidades
del canal.

## R11 — Aislamiento de las pruebas

CUANDO se ejecutan pruebas de esta feature, el suite DEBE inyectar adaptadores
falsos y no depender de red ni credenciales externas.

## R12 — Estado de entrega

CUANDO el adaptador recibe un estado de entrega, el sistema DEBE representarlo
con el vocabulario común `sent`, `delivered`, `read` o `failed`.

## R13 — Identidad técnica por canal

CUANDO el remitente tiene consentimiento vigente pero aún no ha completado el
login verificado, el repositorio DEBE identificar su contacto con la pareja
`(channel, external_user_id)`.

Antes del consentimiento vigente no se persiste el contacto; R21 define esa
compuerta y la resolución transitoria de identidad.

## R14 — Aislamiento de IDs coincidentes

CUANDO dos canales entregan el mismo valor numérico como `external_user_id`,
el repositorio DEBE mantener contactos distintos para cada canal.

## R15 — Consentimiento por identidad de canal

CUANDO el orquestador consulta o registra consentimiento antes del login,
el repositorio DEBE usar conjuntamente `channel` y `external_user_id` como
clave de la aceptación.

## R16 — No conversión de identidad WhatsApp

SI el orquestador procesa un mensaje de WhatsApp ENTONCES el sistema NO DEBE
guardar ni consultar su `external_user_id` en la columna `telegram_user_id`.

## R17 — Migración de contactos Telegram históricos

CUANDO se migra una instalación con contactos Telegram existentes, el sistema
DEBE asignarles `channel = telegram` y `external_user_id` igual al valor textual
de su `telegram_user_id` sin cambiar sus IDs internos ni sus relaciones,
incluidos al ejecutar el backfill más de una vez.

## R18 — Migración de consentimientos históricos

CUANDO se migra una instalación con consentimientos Telegram existentes, el
sistema DEBE conservar cada consentimiento bajo la clave
`(telegram, str(telegram_user_id))` y su versión, hash de aviso y fecha
originales, incluso al ejecutar la migración más de una vez.

## R19 — Vinculación entre canales

MIENTRAS no exista login verificado conforme a la feature #38, el sistema
DEBE mantener separadas las identidades de canal y no asociarlas a un mismo
`client_id`.

## R20 — Pruebas de identidad y consentimiento

CUANDO se ejecutan pruebas para la identidad multicanal, el suite DEBE cubrir
el lookup de contacto por `(channel, external_user_id)` tras consentimiento,
el mismo ID numérico en Telegram y WhatsApp, consentimiento independiente,
preservación idempotente de contactos/consentimientos Telegram históricos y
ausencia de escritura WhatsApp en `telegram_user_id`.

## R21 — Compuerta antes del consentimiento

CUANDO el orquestador procesa un mensaje de un remitente sin consentimiento
vigente, el sistema DEBE resolver `(channel, external_user_id)` solo en memoria,
no persistir contacto ni otros datos personales y limitar las escrituras de
consentimiento a la evidencia en `privacy_consents` bajo esa pareja.

## R22 — Deduplicación técnica heredada antes del consentimiento

CUANDO el endpoint legacy de Telegram recibe un mensaje sin consentimiento
vigente, el sistema DEBE conservar la excepción autorizada por #35 guardando en
`processed_updates` únicamente `update_id`, sin guardar identidad, texto ni
payload.

## R23 — No persistir deduplicación nueva antes del consentimiento

MIENTRAS un request canónico o de un canal nuevo no tenga consentimiento
vigente, o el aviso de privacidad no esté configurado, el sistema DEBE evitar
guardar su clave en `processed_messages`.
