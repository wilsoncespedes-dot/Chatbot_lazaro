# Especificación del chatbot multicanal

Nov 3, 2026 · @lazaro

## Resumen y decisiones

Un solo núcleo con IA atiende Telegram y WhatsApp. El cliente acepta el tratamiento de datos, inicia sesión con credenciales de vigencia limitada y conversa con la IA, que puede pasarlo a un asesor en un panel web propio.

| Tema | Decisión |
| --- | --- |
| Canales | Telegram y WhatsApp con la misma lógica. Nada exclusivo de un canal sin su equivalente en el otro. |
| Proveedor de WhatsApp | Capa de abstracción que soporte Cloud API de Meta, Twilio y 360dialog. Se elige uno después. |
| Identidad | Usuario y contraseña que entrega la empresa. Una credencial solo puede tener una sesión activa, en un solo chat. |
| Vigencia | 1 mes. La renueva el administrador cuando el cliente paga. Aviso al cliente 5 días antes. |
| Credencial vencida | El bot avisa que debe pagar para reactivar el servicio, o que puede hablar con un asesor para borrar sus datos. |
| Multimedia | Solo texto. Si llega audio, imagen o documento, el bot pide que escriba. |
| Tratamiento de datos | Si el cliente no acepta, la conversación se cierra. Si vuelve a escribir, empieza de cero. |
| Supresión de datos | El cliente la pide después de iniciar sesión, aunque su credencial esté vencida. La ejecuta una persona, nunca el bot. |
| Consultas de datos | El cliente puede consultar todo lo suyo que haya en la base de datos, y solo lo suyo. |
| Memoria | Memoria permanente de datos relevantes por cliente, más el historial de cada chat. |
| Panel de asesores | Desarrollo propio, tomando Chatwoot como modelo de experiencia. Horario de ejemplo: 6:00 a. m. a 9:00 p. m. |
| Acceso de asesores | Cuentas individuales, roles y registro de auditoría. |
| Contraseñas | Cambio y recuperación fuera del alcance. No se obliga a cambiarla. |
| IA | Interpreta todas las intenciones. El código controla los pasos obligatorios y los permisos. |

## Arquitectura multicanal

El núcleo nunca sabe de qué canal viene un mensaje. Dos capas de adaptadores traducen todo a un formato común: una por canal y, dentro de WhatsApp, una por proveedor.

&#91;embedded content: arquitectura · canales, adaptadores, núcleo y servicios\]

Agregar un canal o cambiar de proveedor de WhatsApp solo toca la columna de adaptadores; el núcleo y los servicios no cambian.

En texto (el diagrama no se conserva al exportar):

- Telegram (Bot API) ↔ Adaptador Telegram ↔ Núcleo
- WhatsApp (Cloud API, Twilio o 360dialog) ↔ Adaptador WhatsApp (un plugin por proveedor, ventana de 24 horas) ↔ Núcleo
- Núcleo (máquina de estados, harness de IA, mensaje normalizado) ↔ RAG, Datos de clientes, Identidad (login web y vigencia), Panel web (asesores y admin)

### Adaptador de proveedor de WhatsApp

Cada proveedor (Cloud API, Twilio, 360dialog) implementa la misma interfaz. Cambiar de proveedor es cambiar de implementación, no tocar el núcleo.

- `recibir_webhook`: valida la firma del proveedor y convierte el evento al mensaje normalizado.
- `enviar_texto`, `enviar_botones`, `enviar_lista`, `enviar_link`.
- `enviar_plantilla(nombre, variables)`: cada proveedor guarda su propio identificador de la plantilla.
- `estado_entrega`: enviado, entregado, leído, fallido.

### Mensaje normalizado (entrada)

| Campo | Contenido |
| --- | --- |
| `cliente_id` | ID interno del cliente. Vacío hasta que inicie sesión. |
| `canal` | `telegram` o `whatsapp` |
| `canal_usuario_id` | ID de Telegram o número de WhatsApp |
| `conversacion_id` | ID interno de la conversación |
| `tipo` | `texto`, `boton` o `no_soportado` (audio, imagen, documento, sticker) |
| `texto` / `boton_id` | Contenido del mensaje |
| `mensaje_externo_id` | ID del proveedor, para descartar duplicados |
| `recibido_en` | Fecha y hora UTC |

Antes del login, la identidad técnica del remitente se distingue por la pareja
`(canal, canal_usuario_id)`. El ID de WhatsApp nunca se guarda ni se consulta
como `telegram_user_id`. El consentimiento también se asocia a esa pareja. La
unión de una identidad de canal con `cliente_id` ocurre solo después del login
verificado de la fase 3.

### Respuesta abstracta (salida)

El núcleo responde con bloques. Cada adaptador los dibuja a su manera.

| Bloque | Regla para el núcleo | Telegram | WhatsApp |
| --- | --- | --- | --- |
| Texto | Formato mínimo: negrita y saltos de línea | Mensaje | Mensaje |
| Opciones | Máximo 3, de 20 caracteres o menos | Teclado inline | Botones de respuesta |
| Lista | De 4 a 10 opciones | Teclado inline | Mensaje de lista |
| Link | Uno por mensaje | Botón URL | Botón URL |
| Plantilla | Solo cuando la ventana está cerrada | Texto normal | Plantilla aprobada |

### Reglas que vienen de WhatsApp

1. **Ventana de 24 horas.** Se guarda la hora del último mensaje del cliente. Con la ventana cerrada solo salen plantillas. El núcleo pregunta al adaptador si puede enviar texto libre antes de cada envío.
2. **Nunca editar mensajes enviados.** Telegram lo permite, WhatsApp no.
3. **Duplicados.** Los proveedores reintentan webhooks. Se descarta todo `mensaje_externo_id` ya procesado.
4. **Plantillas necesarias:** respuesta del asesor fuera de ventana, resultado de una solicitud de supresión y, si se aprueba, aviso de credencial por vencer.

## Identidad y credenciales

El cliente se identifica con usuario y contraseña en una página web externa, nunca dentro del chat. No se exige una vinculación manual ni una comprobación separada del número de teléfono. El ID del canal sirve para enrutar el chat; un enlace firmado de un solo uso lleva al login y, después de validar las credenciales, asocia automáticamente ese chat al `cliente_id`.

### Creación y vigencia

1. El administrador crea el cliente y su credencial: usuario, contraseña, fecha de inicio y fecha de vencimiento. La vigencia por defecto es **1 mes**.
2. Los días restantes se **calculan** como fecha de vencimiento menos la fecha de hoy. No se guarda un contador que se descuente, así el número siempre es correcto aunque un proceso falle un día.
3. Estados de la credencial: **vigente**, **por vencer** (5 días o menos), **vencida** y **revocada**.
4. Cuando el cliente paga, el administrador renueva la credencial por otro mes desde el panel.
5. **Aviso de vencimiento.** Sí se puede: 5 días antes, el bot escribe al último chat que usó el cliente. En Telegram es un mensaje normal. En WhatsApp tiene que ser una plantilla aprobada por Meta, y cada envío tiene costo.
6. Si la credencial vence durante una sesión, el chat pasa a Sin acceso en el siguiente mensaje.

### Inicio de sesión desde el chat

1. El bot envía un link con un token firmado que identifica la conversación. Es de un solo uso y vence a los 15 minutos (valor propuesto).
2. El cliente escribe usuario y contraseña en la página. La contraseña nunca viaja por Telegram ni WhatsApp, porque quedaría guardada en el historial del chat.
3. La página valida usuario y contraseña. Si son correctos y no hay otra sesión activa, crea la sesión y vincula el chat identificado por el token con `cliente_id`; no busca ni compara el número telefónico con otro perfil.
4. Si la credencial está vigente, el chat pasa a Activa. Si está vencida, pasa a Sin acceso: la identidad queda confirmada, pero solo puede pedir un asesor o la supresión de sus datos. Una credencial revocada no puede iniciar sesión.

### Una sesión a la vez

- Una credencial solo puede tener una sesión activa, en un solo chat.
- La sesión se cierra cuando el cliente pide cerrar sesión o tras 1 hora sin mensajes.
- Si alguien intenta iniciar sesión desde otro chat con una sesión activa, la página lo rechaza y le pide cerrar la otra sesión o esperar.
- Al cerrarse la sesión, el chat vuelve a Esperando inicio de sesión. El consentimiento ya aceptado se conserva.
- El historial y la memoria pertenecen al cliente, no al chat. Si inicia sesión desde otro canal, la IA conserva el contexto.

### Seguridad mínima

- Contraseñas guardadas con hash (Argon2 o bcrypt), nunca en texto plano.
- Bloqueo temporal tras 5 intentos fallidos (valor propuesto).
- El administrador puede revocar una credencial o cerrar una sesión activa.
- Cada inicio de sesión, cierre y revocación queda registrado.
- Cambio y recuperación de contraseña están fuera del alcance. No se obliga a cambiarla. Si el cliente la olvidó, el bot le indica que la pida a la empresa.

## Flujo del cliente

El orden es: saludo, tratamiento de datos, inicio de sesión, bienvenida con temas y conversación libre. El consentimiento va antes del inicio de sesión porque desde el primer mensaje ya se recogen datos personales (número, ID de Telegram, lo que escribe).

&#91;embedded content: estados de la conversación · 7 estados\]

El único camino a la conversación libre pasa por el consentimiento y el inicio de sesión; rechazar los datos termina la conversación.

Transiciones en texto (el diagrama no se conserva al exportar):

| Desde | Evento | Hacia |
| --- | --- | --- |
| Nuevo | Primer mensaje: saludo y texto de datos | Esperando consentimiento |
| Esperando consentimiento | Toca Acepto | Esperando inicio de sesión |
| Esperando consentimiento | Toca No acepto | Cerrada |
| Cerrada | Vuelve a escribir | Nuevo (empieza de cero) |
| Esperando inicio de sesión | Login con credencial vigente | Activa |
| Esperando inicio de sesión | Login con credencial vencida | Sin acceso |
| Activa | 1 hora sin mensajes o cierre de sesión | Esperando inicio de sesión |
| Activa | La credencial vence | Sin acceso |
| Activa | La IA o el cliente escala | Con asesor |
| Con asesor | El asesor resuelve o devuelve | Activa |
| Sin acceso | El admin renueva tras el pago | Activa |
| Sin acceso | Pide asesor o borrar datos | Con asesor |

### Qué pasa en cada estado

- **Nuevo.** El cliente escribe cualquier cosa. El bot saluda y muestra el texto de tratamiento de datos con dos botones: Acepto y No acepto.
- **Esperando consentimiento.** Si pregunta algo sobre la política, la IA responde con el texto de la política y vuelve a mostrar los botones. Si escribe "sí, acepto", la IA lo entiende, pero pide confirmar con el botón: el botón es la prueba.
- **Cerrada.** Si toca No acepto, el bot envía un mensaje de cierre fijo y no procesa más. Si vuelve a escribir, empieza de cero en Nuevo.
- **Esperando inicio de sesión.** El bot envía el link. Si el link vence o el cliente lo pide, la IA envía uno nuevo. Cualquier otra pregunta recibe una respuesta corta y el recordatorio de iniciar sesión.
- **Activa.** El bot envía la bienvenida con los temas que puede preguntar. La IA conversa libremente con las herramientas que permite este estado. Tras 1 hora sin mensajes, o si el cliente cierra sesión, vuelve a Esperando inicio de sesión.
- **Con asesor.** La IA deja de responder. Los mensajes del cliente llegan al panel. Cuando el asesor resuelve o devuelve la conversación, vuelve a Activa.
- **Sin acceso.** La credencial está vencida. El bot envía un mensaje fijo: el servicio está suspendido por falta de pago, se reactiva al pagar, y puede hablar con un asesor para pedir que borren sus datos. Cuando el administrador renueva, el chat vuelve a Activa.

### Reglas que aplican en todos los estados

- Si llega audio, imagen, documento o sticker, el bot responde que solo puede leer texto, sin cambiar de estado.
- Los textos legales, el cierre y la lista de temas son fijos y editables desde el panel de administración. La IA no los redacta.
- La IA puede adaptar el tono del saludo y de las respuestas, pero nunca saltarse un estado.

## Tratamiento de datos y supresión

La autorización se pide con un texto fijo y versionado, y se guarda prueba de cada aceptación. La supresión de datos la pide el cliente al bot, pero la ejecuta una persona desde el panel.

### Prueba de la autorización

El Decreto 1377 de 2013 exige pedir la autorización a más tardar al recoger los datos y conservar prueba de ella. Por cada respuesta se guarda:

| Campo | Ejemplo |
| --- | --- |
| `canal_usuario_id` y, al iniciar sesión, `cliente_id` | +57 300…, cliente 1042 |
| Canal | WhatsApp |
| Versión del texto mostrado | politica-v3 |
| Resultado | Acepta / No acepta |
| ID del mensaje y del botón | Del proveedor |
| Fecha y hora UTC | 2026-11-03 16:05:12 |

Si la política cambia de versión, se pide de nuevo la aceptación en el siguiente mensaje del cliente.

### Si el cliente no acepta

La conversación se cierra y su contenido se borra. Solo se conserva el registro del rechazo de la tabla anterior, como prueba (a validar con el área legal). Si vuelve a escribir, empieza de cero.

### Solicitud de supresión

1. El cliente inicia sesión, con credencial vigente o vencida. El inicio de sesión es lo que confirma su identidad.
2. Dice algo como "quiero que borren mis datos". Con la credencial vencida, el bot se lo ofrece en el mensaje de Sin acceso.
3. La IA reconoce la intención y llama a la herramienta `crear_solicitud_supresion`. No tiene ninguna herramienta que borre datos.
4. Se crea un caso de tipo **Supresión** en el panel, con prioridad alta y fecha límite visible.
5. El bot confirma al cliente con el número de caso.
6. Una persona autorizada ejecuta el borrado, que incluye la memoria permanente del cliente, y cierra el caso. El cliente recibe la notificación (por plantilla si la ventana de WhatsApp está cerrada).

La Ley 1581 fija plazos de respuesta para reclamos (15 días hábiles según el artículo 15). Conviene confirmarlo con el área legal y configurarlo como fecha límite del caso.

## Harness de IA

La IA interpreta cada mensaje, pero solo puede usar las herramientas que el estado actual le permite. Los permisos y los pasos obligatorios los aplica el código, no el prompt.

### Instrucciones (prompt de sistema)

- **Rol y alcance:** asistente de la empresa que responde sobre la base de conocimiento y los datos propios del cliente.
- **Tono:** español, claro, mensajes cortos aptos para chat.
- **Prohibido:** inventar respuestas sin fuente, hablar de datos de otro cliente, pedir contraseñas en el chat, prometer borrados o plazos, responder temas fuera de alcance.
- **Sin respuesta:** decirlo y ofrecer un asesor.

### Contexto que recibe en cada turno

- Estado de la conversación y herramientas habilitadas.
- Capacidades del canal: máximo de botones y si la ventana está abierta.
- Memoria permanente del cliente, si hay sesión.
- Últimos mensajes del chat más un resumen de lo anterior.
- Si hay sesión: que existe un cliente autenticado, nunca la credencial.

### Memoria

- **Historial del chat:** los mensajes de la conversación actual, para responder en contexto.
- **Memoria permanente:** al terminar cada conversación, la IA decide qué es relevante (por ejemplo, temas pendientes o acuerdos con asesores) y lo guarda por `cliente_id`.
- La IA recibe esa memoria al inicio de cada sesión, y el asesor la ve en el panel.
- Nunca se guardan contraseñas ni datos sensibles en la memoria.
- La supresión de datos borra también la memoria.
- Conservarla para siempre debe quedar justificado en la política de tratamiento, porque la ley pide guardar los datos solo mientras sean necesarios para su finalidad. A validar con el área legal.

### Herramientas

| Herramienta | Qué hace | Estados donde está disponible |
| --- | --- | --- |
| `buscar_base_conocimiento` | Busca en el RAG y devuelve fragmentos con su fuente | Activa (y la política en Esperando consentimiento) |
| `consultar_mis_datos` | Consulta cualquier dato del cliente en la base de datos | Activa |
| `escalar_a_asesor` | Pasa la conversación al panel con motivo y resumen | Activa, Sin acceso |
| `crear_solicitud_supresion` | Crea el caso de supresión en el panel | Activa, Sin acceso |
| `enviar_link_inicio_sesion` | Genera y envía un link nuevo | Esperando inicio de sesión |
| `cerrar_sesion` | Cierra la sesión para poder usar la credencial en otro chat | Activa, Sin acceso |

**Regla clave para los datos propios:** `consultar_mis_datos` toma el `cliente_id` de la sesión, nunca de lo que escriba la IA. Así, aunque alguien engañe al modelo, la consulta solo puede devolver datos de ese cliente.

Como el cliente puede consultar todo lo suyo, la IA no lee las tablas directamente. Consulta vistas de solo lectura, y la propia base de datos filtra por `cliente_id` (seguridad a nivel de fila). La IA puede armar la consulta SQL sobre esas vistas, pero aunque se equivoque o la engañen, nunca recibe filas de otro cliente. Qué campos internos quedan fuera de las vistas lo define el equipo dueño de la base de datos, fuera del alcance de este proyecto.

### Guardrails

- **Entrada:** límite de longitud, detección de intentos de manipular al bot, rechazo de contenido no textual.
- **Salida:** la respuesta sobre la base de conocimiento debe citar un fragmento recuperado o reconocer que no sabe. Se adapta al canal (botones, longitud).
- **Herramientas:** bloqueadas por estado. Se registra cada llamada con sus argumentos y resultado.

### Cuándo escalar a un asesor

- El cliente lo pide.
- La credencial está vencida y el cliente quiere borrar sus datos.
- La IA no encuentra respuesta dos veces seguidas sobre el mismo tema.
- El cliente muestra frustración.
- Fuera del horario de atención (ejemplo: 6:00 a. m. a 9:00 p. m.), el caso queda en cola y el bot avisa que lo atenderán al abrir.

### Evaluación

Un conjunto de 50 a 100 preguntas reales con su respuesta esperada, más casos de ataque: pedir datos de otro cliente, saltarse el consentimiento, pedir que borre datos. Se corre cada vez que cambia el prompt, el modelo o la base de conocimiento.

## Panel de asesores y administración

El panel es propio y sigue el modelo de bandeja de Chatwoot: todas las conversaciones de ambos canales en un solo lugar, en tiempo real por websockets. Cada persona entra con su propia cuenta.

### Roles

| Rol | Puede |
| --- | --- |
| Asesor | Atender conversaciones asignadas o en cola, notas internas, transferir, resolver, devolver al bot |
| Supervisor | Lo del asesor, más ver todas las conversaciones, reasignar y ver métricas |
| Responsable de datos | Atender y cerrar casos de supresión |
| Administrador | Clientes y credenciales, cuentas de asesores, textos fijos, plantillas, horarios |

Acceso con inicio de sesión individual y segundo factor, o con la cuenta corporativa de Google o Microsoft. Toda lectura y respuesta queda en el registro de auditoría.

### Bandeja

- Filtros: en cola, mías, sin asignar, resueltas, por canal, por etiqueta.
- Cada fila muestra canal, nombre del cliente, último mensaje, tiempo de espera y estado de la ventana de 24 horas.
- Asignación automática por carga, o manual por el supervisor.

### Vista de conversación

- Historial completo: cliente, bot y asesores, marcados de forma distinta.
- Resumen generado por la IA al escalar, con el motivo.
- Panel lateral del cliente: chat de la sesión activa, días de credencial, versión y fecha del consentimiento, y memoria permanente.
- Indicador de ventana de WhatsApp. Con la ventana cerrada, el campo de texto cambia a selector de plantillas.
- Respuestas guardadas, notas internas, transferir, resolver y devolver al bot.

### Administración

- **Clientes y credenciales:** tabla con días restantes y estado (vigente, por vencer, vencida, revocada). Acciones: renovar por 1 mes, revocar y cerrar la sesión activa.
- **Casos de supresión:** cola aparte con fecha límite y estado.
- **Textos fijos versionados:** saludo, política de datos, cierre, lista de temas, mensaje de servicio suspendido, aviso de vencimiento.
- **Plantillas de WhatsApp** y su estado de aprobación.
- **Horarios de atención** (ejemplo: 6:00 a. m. a 9:00 p. m.) y mensaje fuera de horario.
- **Métricas:** tiempo de primera respuesta, conversaciones por asesor, motivos de escalamiento, preguntas sin respuesta de la IA.

## Implementación por fases

Siete fases, en este orden. Cada una depende de las anteriores y se entrega en su propio PR, con pruebas.

| Fase | Entrega | Terminada cuando |
| --- | --- | --- |
| 1. Núcleo multicanal | Mensaje normalizado, respuesta abstracta, adaptador Telegram, interfaz de proveedor WhatsApp con adaptador falso, descarte de duplicados, control de ventana de 24 horas | El mismo mensaje de prueba produce la misma respuesta en Telegram y WhatsApp; la integración con un proveedor real se registra como feature posterior a la elección del proveedor |
| 2. Estados y consentimiento | Los 7 estados, textos fijos versionados y configurables, prueba de autorización, cierre y reinicio, rechazo de contenido no textual | Se recorren todas las transiciones de la tabla de estados, salvo las que dependen de la fase 3 |
| 3. Identidad y credenciales | Servicio de identidad, página de login, token de un solo uso, vigencia de 1 mes, una sesión a la vez, cierre a la hora sin mensajes, vencida a Sin acceso, revocada sin acceso, bloqueo por intentos | Un cliente inicia sesión desde el chat y no puede abrir una segunda sesión en otro chat |
| 4. Harness de IA | Prompt de sistema, herramientas por estado, RAG con fuentes, vistas filtradas por `cliente_id`, guardrails, reglas de escalamiento, conjunto de evaluación | El conjunto de evaluación pasa, incluidos los casos de ataque |
| 5. Memoria | Historial con resumen, memoria permanente por cliente, borrado de la memoria en la supresión | La IA recuerda un dato de una sesión anterior y lo olvida tras una supresión |
| 6. Panel de asesores | Bandeja, vista de conversación, roles, auditoría, tiempo real, selector de plantillas, cola de supresión | Un asesor recibe un escalamiento, responde y devuelve la conversación al bot |
| 7. Administración y avisos | Clientes y credenciales, textos, plantillas, horarios, métricas, aviso de vencimiento 5 días antes | El admin renueva una credencial y el cliente recibe el aviso de vencimiento |

Todos los valores de tiempo (1 hora, 1 mes, 5 días, horario) y los textos legales deben ser configurables, porque la validación legal puede cambiarlos.

## Puntos abiertos

El proveedor real de WhatsApp se elegirá antes de iniciar la feature #43. La
calibración de embeddings requiere manuales de producción. También queda la
validación legal.

- [ ] Validar con el área legal: orden del consentimiento, texto de la política, plazos de supresión, registro del rechazo y memoria permanente.
- [ ] Elegir proveedor WhatsApp para la feature #43: Cloud API de Meta, Twilio o 360dialog.
- [ ] Calibrar el modelo de embeddings y el umbral con un manual real.

### Fuentes

- [Concepto SIC sobre el Decreto 1377 de 2013 (autorización y prueba)](https://www.ambitojuridico.com/sites/default/files/BancoMedios/Archivos/cpto-201811400676461-18.pdf)
- [WhatsApp Cloud API: envío de mensajes y ventana de 24 horas](https://scriptagc.wasmer.app/https_developers_facebook_com/docs/whatsapp/cloud-api/guides/send-messages)
- [Límites de mensajes interactivos de WhatsApp](https://singhamandeep.com/whatsapp-interactive-messages-api/)
- [Chatwoot (repositorio)](https://github.com/chatwoot/chatwoot)
