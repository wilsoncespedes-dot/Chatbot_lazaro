# Requirements — estados_y_consentimiento (feature #37)

> Fuente de verdad: acceptance de #37, fases 1–2 y tabla de estados de
> `docs/especificacion.md`. Se reutilizan identidad/deduplicación de #36 y la
> compuerta preconsentimiento de #35. Login/credenciales pertenecen a #38.

## Orchestrator — estado y flujo

### R1 — Estados admitidos

El orquestador DEBE representar estos siete estados de conversación:
`nuevo`, `esperando_consentimiento`, `cerrada`, `esperando_inicio_sesion`,
`activa`, `con_asesor` y `sin_acceso`.

### R2 — Inicio sin consentimiento

CUANDO llega un mensaje de texto de una identidad sin consentimiento vigente,
el orquestador DEBE mostrar el saludo, el aviso de tratamiento vigente y los
botones canónicos `privacy.accept` y `privacy.reject` sin persistir contacto,
mensaje, estado de conversación ni llamar al LLM.

### R3 — Pregunta sobre la política

MIENTRAS una identidad espera consentimiento, CUANDO llega texto que no es uno
de los botones de consentimiento, el orquestador DEBE contestar con el texto
vigente de la política y volver a mostrar ambos botones sin llamar al LLM.

### R4 — Aceptación verificable

CUANDO llega el botón `privacy.accept` para la versión vigente del aviso, el
orquestador DEBE registrar la aceptación con canal, ID externo, versión, hash
del texto, ID externo del mensaje/botón y fecha UTC antes de habilitar el flujo
posterior al consentimiento.

### R5 — Rechazo verificable

CUANDO llega el botón `privacy.reject`, el orquestador DEBE registrar el
rechazo con canal, ID externo, versión, hash del texto, ID externo del
mensaje/botón y fecha UTC, y responder con el texto fijo de cierre.

### R6 — Texto afirmativo sin botón

MIENTRAS una identidad espera consentimiento, CUANDO su texto afirma que
acepta la política sin un botón `privacy.accept`, el orquestador DEBE mantener
el estado `esperando_consentimiento` y pedir que confirme usando el botón.

### R7 — Versión nueva

CUANDO la versión vigente del aviso no coincide con la versión aceptada por la
identidad, el orquestador DEBE volver a `esperando_consentimiento` antes de
procesar o persistir mensajes nuevos de esa identidad.

### R8 — Conversación cerrada

MIENTRAS la conversación está `cerrada`, CUANDO llega un mensaje posterior al
rechazo, el orquestador DEBE iniciar una conversación nueva en `nuevo` y volver
a presentar el aviso vigente y sus botones.

### R9 — Espera de inicio de sesión

MIENTRAS la conversación está `esperando_inicio_sesion`, CUANDO llega un
mensaje distinto del evento de login definido por #38, el orquestador DEBE
responder con el recordatorio fijo de inicio de sesión sin ejecutar RAG ni LLM.

### R10 — Conversación activa

MIENTRAS la conversación está `activa`, CUANDO llega texto, el orquestador
DEBE continuar el flujo de atención existente respetando la compuerta de
consentimiento de #35 y la identidad por canal de #36.

### R11 — Traspaso a asesor

CUANDO una conversación activa se escala, el orquestador DEBE cambiarla a
`con_asesor` y dejar de generar respuestas del bot hasta recibir el evento de
resolución o devolución del asesor.

### R12 — Conversación atendida por asesor

MIENTRAS la conversación está `con_asesor`, CUANDO llega texto del cliente, el
orquestador DEBE entregarlo al flujo de atención de asesores sin llamar al LLM.

### R13 — Devolución del asesor

CUANDO el asesor resuelve o devuelve una conversación `con_asesor`, el
orquestador DEBE cambiarla a `activa`.

### R14 — Sin acceso

MIENTRAS la conversación está `sin_acceso`, CUANDO llega texto del cliente,
el orquestador DEBE responder con el mensaje fijo de servicio suspendido sin
ejecutar RAG ni LLM.

### R15 — Contenido no textual

CUANDO llega audio, imagen, documento o sticker en cualquier estado, el
orquestador DEBE responder con el texto fijo de contenido no soportado sin
cambiar el estado ni persistir el contenido recibido.

### R16 — Evento de credencial vigente

CUANDO #38 informa que una credencial vencida fue renovada, el orquestador
DEBE cambiar la conversación de `sin_acceso` a `activa`.

### R17 — Eventos de identidad

CUANDO #38 informa un login verificado con credencial vigente, el orquestador
DEBE cambiar la conversación de `esperando_inicio_sesion` a `activa`.

### R18 — Credencial vencida

CUANDO #38 informa un login verificado con credencial vencida o el vencimiento
de una credencial activa, el orquestador DEBE cambiar la conversación a
`sin_acceso`.

## Panel administrativo — textos del flujo

### R19 — Textos administrables

CUANDO un administrador autenticado guarda los textos del flujo, el panel
DEBE persistirlos en la configuración operativa existente.

### R20 — Texto legal versionado

CUANDO el administrador publica un texto de política con una versión nueva,
el panel DEBE guardar texto y versión juntos para que el orquestador fuerce la
reaceptación conforme a R7.

### R21 — Textos fijos sin generación

CUANDO el orquestador envía saludo, cierre, recordatorio de login, suspensión
o respuesta de contenido no textual, el sistema DEBE leer el texto del panel.

## Privacidad y multicanal — no regresión

### R22 — Compuerta preconsentimiento

MIENTRAS una identidad no tenga aceptación vigente, el orquestador DEBE
preservar las garantías de #35 y #36: no persistir contacto, estado,
conversación ni contenido de usuario; solo registra la decisión de
consentimiento/rechazo en su tabla de evidencia y, para Telegram legacy,
conserva `processed_updates(update_id)` según R22 de #36.

### R23 — Identidad de canal

CUANDO se consulta, registra consentimiento o estado por un mensaje, el
orquestador DEBE usar `(channel, external_user_id)`.

### R24 — Evidencia de botones

CUANDO se registra aceptación o rechazo, el repositorio DEBE conservar el
ID externo del mensaje entrante y el identificador canónico del botón junto
con la versión y el hash del aviso.

### R25 — Acceso a textos sin configuración

MIENTRAS los textos legales requeridos no estén configurados por un
administrador, el orquestador DEBE fallar de forma cerrada y no habilitar
procesamiento posterior al consentimiento.

## Orchestrator — transiciones complementarias

### R26 — Transición tras aceptar

CUANDO se registra una aceptación válida mediante `privacy.accept`, el
orquestador DEBE cambiar la conversación a `esperando_inicio_sesion`.

### R27 — Cierre de sesión o inactividad

CUANDO #38 informa el cierre de sesión o el vencimiento del tiempo de
inactividad de una conversación `activa`, el orquestador DEBE cambiarla a
`esperando_inicio_sesion`.

### R28 — Solicitud de asesor sin acceso

CUANDO una conversación `sin_acceso` recibe el evento de solicitud de asesor
o de supresión, el orquestador DEBE cambiarla a `con_asesor` sin habilitar RAG
ni LLM.

### R29 — Borrado al rechazar

CUANDO una identidad pulsa `privacy.reject`, el sistema DEBE eliminar el
contenido personal de la conversación rechazada y conservar únicamente la
evidencia mínima del rechazo en `privacy_consents`.

### R30 — Texto fijo sin LLM

CUANDO el orquestador envía un texto fijo de este flujo, el sistema NO DEBE
generarlo ni completarlo con el LLM.

### R31 — Sin asociación prelogin

MIENTRAS no existe login verificado conforme a #38, el sistema NO DEBE asociar
identidades de canales distintos al mismo cliente.

### R32 — Lectura dinámica de textos

CUANDO el orquestador necesita un texto fijo, el sistema DEBE leer la última
versión persistida por el panel sin requerir reinicio del servicio.

### R33 — No inventar textos legales

MIENTRAS falta un texto legal requerido en la configuración, el orquestador
NO DEBE reemplazarlo con un valor legal inventado.

### R34 — Aceptaciones históricas sin botón

MIENTRAS una identidad solo tenga aceptación histórica sin evidencia de botón,
el orquestador DEBE solicitar la confirmación mediante `privacy.accept` antes
de habilitar procesamiento posterior al consentimiento.

### R35 — Estado inicial en memoria

CUANDO llega el primer mensaje de una identidad sin consentimiento vigente, el
orquestador DEBE resolver `nuevo → esperando_consentimiento` en memoria sin
persistir el estado ni crear un contacto.

### R36 — Cierre por rechazo en memoria

CUANDO una identidad en `esperando_consentimiento` pulsa `privacy.reject`, el
orquestador DEBE cambiarla a `cerrada` en memoria y no persistir una fila de
estado o contacto; solo conserva la evidencia de rechazo permitida por R5/R29.

### R37 — Vigencia del botón de consentimiento

CUANDO se procesa un botón de consentimiento, el orquestador DEBE comprobar
que la evidencia autenticada corresponde a la misma versión y hash de política
que están vigentes y a la identidad `(channel, external_user_id)` que recibió
el aviso; un botón antiguo, manipulado o reenviado a otra identidad NO DEBE
registrar consentimiento ni cambiar el estado.

### R38 — Botones interactivos de Telegram

CUANDO Telegram presenta las opciones `privacy.accept` y `privacy.reject`, el
adaptador DEBE enviarlas como botones interactivos y convertir el
`callback_query` recibido en un mensaje normalizado con el ID canónico del
botón. El callback debe quedar ligado a la versión/hash, identidad y chat que
recibieron el aviso, de modo que reenviarlo desde otro chat no conceda
consentimiento. El flujo completo webhook → decisión DEBE conservar esa prueba.

### R39 — Desafío de consentimiento de un solo uso

CUANDO el orquestador presenta los botones, DEBE emitir un desafío aleatorio
ligado a esa presentación y conservarlo solo en memoria hasta el primer clic
válido. El desafío se DEBE consumir atómicamente antes de registrar aceptación
o rechazo. Un callback ausente, repetido, de una presentación anterior o
recibido cuando la identidad ya tiene consentimiento vigente NO DEBE registrar
otra decisión, borrar contenido ni cambiar estado.

## Cobertura del acceptance

| Acceptance #37 | Requirements |
|---|---|
| Siete estados y transiciones (transiciones de credenciales implementadas mediante eventos de #38) | R1–R18, R26–R28, R35–R36 |
| Consentimiento con evidencia y cambio de versión | R4–R7, R20, R24, R34 |
| Rechazo, cierre y reinicio; respuesta multimedia sin cambio de estado | R5, R8, R15, R29, R35, R36 |
| Textos fijos administrados por panel, no por IA ni constantes | R19–R21, R25, R30, R32, R33 |
| Preservar compuertas #35 y seguridad/transiciones verificadas | R2–R18, R22–R29, R31 |
| Transporte y vigencia del botón interactivo de Telegram | R4, R5, R7, R20, R24, R37, R38 |
| Desafío efímero de un solo uso y estado elegible | R4, R5, R29, R37, R39 |
| Aislamiento de callback por chat de Telegram | R38, R40 |

### R40 — Chat de origen del botón

CUANDO se valida un callback de Telegram, el orquestador DEBE comprobar que
`external_chat_id` coincide con el chat donde presentó ese desafío; un
callback reenviado a otro chat, aunque tenga el mismo usuario emisor, NO DEBE
consumir el desafío ni registrar decisión.
