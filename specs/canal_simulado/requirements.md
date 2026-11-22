# Requirements — #63 `canal_simulado`

Fase 3 de la ampliación multicanal genérica. Un adaptador **SIMULADO** del
registry (`tipo_adaptador = simulado`) se hace pasar por cualquier canal (por
ejemplo «TikTok (simulado)») sin credenciales ni red, para demostrar la
plataforma. Sus respuestas salientes quedan en un buzón propio; una página del
panel (admin y supervisor) y `scripts/simular_canal.py` permiten escribir como
cliente. Depende de #60, #61 (registry, `canales`, secretos) y #62 (webhook
genérico firmado), todas `done`.

Fuera de alcance: crear canales desde el panel (#66); cola durable y outbox
(#64); retirada de `ATTENDED_CHANNELS` y recorrido completo del canal simulado
(consentimiento, login, bot, asesor) (#65); etiqueta de origen en bandeja y chat
(#67). Hasta #65 el orquestador responde `422` a los canales que no son
`telegram` ni `whatsapp`; esta feature **no toca esa guarda** y muestra el
rechazo como tal (R22–R24, R33).

Quién cumple cada requirement:

- **contracts** (`contracts/`): R1–R2.
- **telegram_gateway**: R3–R27.
- **orchestrator** (panel): R28–R35.
- **scripts**: R36–R38.
- **Configuración y todos**: R39–R42.

Definiciones:

- **Canal simulado**: fila de `canales` con `tipo_adaptador = simulado`. Nombre,
  ícono y color son las columnas `nombre`, `icono` y `color` de esa fila; las
  capacidades salen de `config.capabilities` (R5). Crear otro canal simulado es
  solo otra fila (`POST /channels`), sin código nuevo.
- **Buzón**: almacén propio del gateway con las entradas del canal simulado:
  `client` (mensaje escrito por el cliente de prueba), `reply` (respuesta
  saliente de la plataforma, bot o asesor, sin distinguirlas) y `rejected` (el
  orquestador no procesó el mensaje).
- **Id externo de prueba**: `external_user_id` del cliente simulado; coincide con
  `destino` de las respuestas.

## Cobertura del acceptance de #63

| Criterio del acceptance | Requirements |
|---|---|
| Adaptador `simulado` con nombre, ícono, color y capacidades de config; palabra SIMULADO en clase, docstring, etiqueta del panel y herramienta | R3–R8, R29, R36, R40 |
| Sin red; buzón consultable con retención corta configurable | R9–R18, R19 |
| Página de prueba (admin y supervisor) y `scripts/simular_canal.py` firmado | R20, R28–R35, R36–R38 |
| Crear un canal simulado nuevo sin código | R3, R27 |
| Rechazo 422 del orquestador visible como tal hasta #65 | R21–R24, R33, R42 |
| Pruebas y marca SIMULADO visible | R1–R2, R40, R41 |

## contracts

**R1.** `lazaro_contracts` DEBE exportar `MailboxEntry` (`id` entero ≥ 1,
`channel`, `destination`, `kind` ∈ `client`/`reply`/`rejected`, `text` de 1 a
`MAX_TEXT_LENGTH` caracteres, `created_at`), `MailboxResponse` (`channel`,
`entries`), `SimulatedInboundRequest` (`external_user_id` con el patrón de id
externo de R30 y `text` de 1 a `MAX_TEXT_LENGTH`) y `SimulatedInboundResponse`
(`status` ∈ `accepted`/`duplicate`, `forwarded` booleano, `reason` opcional de
hasta 200 caracteres); todos con `extra="forbid"`, rechazando valores fuera de
rango.

**R2.** `contracts/CONTRATOS.md` DEBE documentar, en una sección «Canal
simulado», `GET /channels/{channel_id}/mailbox` y `POST
/channels/{channel_id}/simulate` en el formato estándar de rutas (autenticación
`X-Service-Token`, ejemplo JSON de petición y respuesta que valida contra los
modelos de R1, tabla de errores `401`, `404`, `422`, `503`), `config.capabilities`
con sus claves y valores por defecto, los ajustes `SIMULATED_MAILBOX_RETENTION_SECONDS`
y `SIMULATED_MAILBOX_MAX_ENTRIES`, y el rechazo temporal del orquestador hasta
#65.

## telegram_gateway — adaptador `simulado`

**R3.** El `CHANNEL_REGISTRY` por defecto DEBE contener `simulado`
(`managed_by_environment = False`, disponible siempre) además de `telegram`,
`whatsapp_cloud` y `webhook_generico`, y `POST /channels` con ese tipo DEBE
responder `201` con el secreto del canal y listarlo en `adapter_types`.

**R4.** La clase del adaptador DEBE llamarse `SimuladoChannel` (su nombre contiene
«Simulado») y su docstring DEBE contener la palabra `SIMULADO` en mayúsculas.

**R5.** `capacidades()` DEBE leer `config.capabilities` del registro del canal
(objeto con las claves de `ChannelCapabilities`) y, para cada clave ausente,
usar el valor por defecto: `free_text_allowed=true`, `supports_buttons=false`,
`supports_links=false`, `supports_images=false`, `supports_files=false`,
`supports_audio=false`, `requires_template=false`, `max_options=0`,
`min_list_options=0` y `max_list_options=0`. Dos canales simulados con
`config.capabilities` distintas DEBEN informar capacidades distintas.

**R6.** SI `POST /channels` o `PATCH /channels/{id}` de un canal simulado trae un
`config` con una clave distinta de `capabilities`, o un `capabilities` con una
clave desconocida, un tipo erróneo o un valor que `ChannelCapabilities` no
acepta, ENTONCES el sistema DEBE responder `422 validation_error` sin persistir;
un `config` vacío es válido.

**R7.** CUANDO el canal simulado envía bloques que sus capacidades no admiten
(por ejemplo `ImageBlock` con `supports_images=false`), `POST /send` DEBE
degradarlos con la regla de #61 y el buzón DEBE contener el texto degradado.

**R8.** `recibir_mensaje` e `identificar_usuario` DEBEN aceptar el formato
normalizado de entrada del contrato (`direction=inbound`) y devolver `None` sin
lanzar excepciones ante un payload inválido o de salida, igual que el canal
genérico.

**R9.** CUANDO se envía una respuesta por un canal simulado, `enviar_mensaje` DEBE
añadir al buzón una entrada `reply` por cada trozo de texto (cada uno de hasta
`MAX_TEXT_LENGTH`, en orden) con `destination` = destino, devolver `sent` y NO DEBE
abrir ningún socket ni usar `CallbackClient`.

**R10.** SI el buzón falla al escribir ENTONCES `enviar_mensaje` DEBE devolver
`failed`, registrar solo el tipo de la excepción y `POST /send` DEBE responder
`502 upstream_error`.

**R11.** SI `adapters.mailbox` no está disponible al construir el canal ENTONCES
`build` DEBE lanzar `ChannelNotConfigured`.

## telegram_gateway — buzón

**R12.** El puerto `MailboxRepository` DEBE ofrecer `append(channel_id, destination,
kind, text, now) -> int` (devuelve el id creciente) y `list(channel_id, destination,
after_id, limit, now)` que devuelve las entradas del canal con id > `after_id`, en
orden ascendente de id, filtradas por `destination` si se indica; la versión falsa
en memoria DEBE cumplirlo con el mismo comportamiento que la de Postgres.

**R13.** El buzón DEBE conservar cada entrada solo `SIMULATED_MAILBOX_RETENTION_SECONDS`
(por defecto 3600, entre 60 y 86400) y `list` y `append` NO DEBEN devolver ni contar
entradas más antiguas; con un reloj controlado, una entrada de 3601 s ya no se
devuelve.

**R14.** El buzón DEBE conservar como máximo `SIMULATED_MAILBOX_MAX_ENTRIES` entradas por
canal (por defecto 500, entre 10 y 5000), eliminando las más antiguas al superar el
límite.

**R15.** `PostgresMailboxRepository` DEBE crear la tabla `buzon_simulado` con
`CREATE TABLE IF NOT EXISTS` en la primera conexión, usar solo parámetros `%s` en
el SQL y reconectar tras un error de conexión, igual que el repositorio de
canales.

**R16.** `build_default_adapters` DEBE usar el repositorio de Postgres con
`DATABASE_URL`; `create_app` DEBE usar el repositorio en memoria si
`adapters.mailbox` es `None`.

**R17.** El buzón NO DEBE guardar el secreto del canal, firmas ni encabezados; solo
el texto, el destino y el tipo.

**R18.** `Settings` DEBE rechazar con `ValidationError` valores fuera de rango de
`SIMULATED_MAILBOX_RETENTION_SECONDS` y `SIMULATED_MAILBOX_MAX_ENTRIES`.

## telegram_gateway — rutas internas

**R19.** CUANDO se llama `GET /channels/{channel_id}/mailbox` con `X-Service-Token`
y los parámetros opcionales `destination`, `after` (por defecto 0) y `limit` (por
defecto 100, entre 1 y 500), el sistema DEBE responder `200` con `MailboxResponse`;
sin token DEBE responder `401 unauthorized`. SI el canal no existe o su tipo no
tiene buzón ENTONCES DEBE responder `404 not_found` con el mismo cuerpo en ambos
casos; un canal simulado inactivo SÍ se puede leer.

**R20.** CUANDO se llama `POST /channels/{channel_id}/simulate` con `X-Service-Token`
y un `SimulatedInboundRequest`, el sistema DEBE construir un mensaje normalizado
`inbound` (`channel` = canal, `external_user_id` y `external_chat_id` = id de
prueba, `kind` `text`, `external_message_id` único con prefijo `sim-`,
`received_at` = reloj del gateway) y procesarlo por el mismo camino de entrega que
el webhook firmado (deduplicación, buzón, orquestador) sin exigir firma, porque
el token de servicio autentica al panel. SI el canal no existe o no tiene buzón
ENTONCES DEBE responder `404 not_found`; SI está inactivo, `422 channel_inactive`;
sin token, `401`.

**R21.** El camino de entrega compartido DEBE llamar al hook opcional
`registrar_entrada(message)` del adaptador del canal (si lo define) tras
confirmar que el mensaje es nuevo y antes de entregarlo, y al hook opcional
`registrar_rechazo(message, reason)` si el orquestador falla o rechaza el mensaje;
`WebhookService` NO DEBE comparar con nombres de canal concretos y los canales sin
esos hooks DEBEN comportarse exactamente como en #62.

**R22.** CUANDO llega un mensaje nuevo a un canal simulado, el buzón DEBE contener una
entrada `client` con su texto y `destination` = id externo de prueba.

**R23.** SI el orquestador responde `422` (guarda `ATTENDED_CHANNELS`) o falla ENTONCES
el buzón DEBE contener además una entrada `rejected` cuyo texto es el motivo (por
ejemplo «El orquestador respondió 422.», máximo 200 caracteres); el webhook
firmado DEBE seguir respondiendo `200 accepted` (R27 de #62) y `/simulate` DEBE
responder `200` con `forwarded=false` y `reason` con ese motivo.

**R24.** CUANDO el orquestador acepta el mensaje, `/simulate` DEBE responder `200` con
`forwarded=true` y `reason` ausente.

**R25.** CUANDO llega un mensaje duplicado (mismo `external_message_id` por el webhook
firmado), el buzón NO DEBE recibir entradas nuevas.

**R26.** Un fallo al escribir en el buzón desde los hooks NO DEBE impedir la entrega al
orquestador ni cambiar la respuesta; DEBE registrarse como ERROR con el tipo de la
excepción.

**R27.** CUANDO se crean por `POST /channels` dos canales de tipo `simulado` con ids,
nombres y capacidades distintos, el sistema DEBE recibir, firmar, enviar y leer el
buzón de ambos sin ningún módulo, archivo de código ni tipo nuevo.

## orchestrator — página de prueba del panel

**R28.** CUANDO un administrador (panel `/admin`) o un supervisor (panel `/asesor`)
con sesión pide `GET /admin/simulador` o `GET /asesor/simulador`
respectivamente, el sistema DEBE responder `200` con la página; un asesor,
responsable de datos o cliente DEBE recibir la negativa propia de su panel, y sin
sesión DEBE redirigir al acceso, sin llamar al gateway.

**R29.** La página DEBE mostrar la palabra `SIMULADO` en el título y el encabezado,
listar solo los canales con `adapter_type = simulado` (del gateway) con una
etiqueta que contiene `SIMULADO` aunque el nombre del canal no la incluya, y
mostrar un aviso, sin formulario, si no existe ninguno.

**R30.** CUANDO se envía el formulario `POST` de la página con un canal simulado, un
id externo de prueba que cumple `[A-Za-z0-9_.:-]{1,64}` y un texto de 1 a 4096
caracteres, el sistema DEBE llamar a `POST /channels/{id}/simulate`, y responder
`303` a la misma página con el canal y el id seleccionados.

**R31.** SI el formulario trae un token CSRF ausente o incorrecto, un canal que no está
en la lista de canales simulados, un id o un texto inválidos ENTONCES el sistema
NO DEBE llamar al gateway y DEBE responder con el rechazo propio del panel
(CSRF) o `422` con el formulario y el motivo, y `POST` de un asesor, responsable de
datos, cliente o sin sesión DEBE ser rechazado como en R28.

**R32.** CUANDO se elige canal e id, la página DEBE mostrar la conversación leída del
buzón (`GET /channels/{id}/mailbox?destination=…`) en orden: los mensajes del
cliente de prueba, las respuestas de la plataforma («bot o asesor») y los
rechazos; todo el texto DEBE escaparse (un `<script>` en un mensaje no se emite como
HTML).

**R33.** CUANDO el buzón contiene una entrada `rejected`, la página DEBE mostrarla como
rechazo («El orquestador no procesó el mensaje: …») con la nota de que hasta
#65 solo atiende `telegram` y `whatsapp`, y NO DEBE presentarla como respuesta
del bot.

**R34.** SI el gateway no responde o responde error ENTONCES la página DEBE mostrar un aviso
de servicio no disponible con estado `503`, sin trazas ni el token de servicio,
en lugar de `500`.

**R35.** El cliente `SimulatorClient` del orquestador (versión HTTP y falsa) DEBE
enviar `X-Service-Token`, llamar solo a `GET /channels`, `GET
/channels/{id}/mailbox` y `POST /channels/{id}/simulate`, y no recibir nunca
secretos de canal; el panel de administración DEBE enlazar la página («Simulador»)
desde su navegación.

## scripts — `scripts/simular_canal.py`

**R36.** `simular_canal.py` DEBE enviar un mensaje normalizado `inbound` a `POST
{url}/webhooks/{canal}` con `Content-Type: application/json`, `X-Lazaro-Timestamp`
(segundos Unix) y `X-Lazaro-Signature` = HMAC-SHA256 en hex de
`<timestamp>.<cuerpo exacto enviado>` con el secreto del canal, imprimir el
código HTTP y el cuerpo de la respuesta, y salir con código `0` si es `200` y `1`
en otro caso; su `--help` y su docstring DEBEN contener `SIMULADO`.

**R37.** El secreto DEBE leerse de la variable de entorno `LAZARO_CANAL_SECRETO` (o la
indicada con `--secreto-env`), NO DEBE aceptarse como argumento de línea de comandos
ni imprimirse, y si falta el script DEBE salir con código `2` y un mensaje sin el
valor.

**R38.** La firma generada DEBE ser verificada con éxito por `verify_signature` del
gateway y coincidir con el ejemplo firmado de `CONTRATOS.md`; los argumentos
`--usuario`, `--texto`, `--id-mensaje` (reenviar el mismo id provoca `duplicate`) y
`--url` DEBEN existir, y un fallo de red DEBE salir con código `2` sin trazas.

## Configuración y todos

**R39.** `.env.example` DEBE declarar `SIMULATED_MAILBOX_RETENTION_SECONDS=3600` y
`SIMULATED_MAILBOX_MAX_ENTRIES=500` con un comentario que indique que el buzón es
solo de pruebas.

**R40.** La palabra `SIMULADO` DEBE aparecer en el docstring de la clase, la etiqueta del
canal en el panel, el título de la página y la ayuda del script (probado en cada
uno).

**R41.** La batería existente de `services/telegram_gateway/tests`, `services/orchestrator/tests`,
`contracts/tests` y `scripts/tests` DEBE pasar sin modificaciones, salvo los tests que
`design.md` §7 sustituye.

**R42.** El sistema NO DEBE modificar `ATTENDED_CHANNELS` ni el comportamiento de
`POST /messages` del orquestador; una prueba DEBE afirmar que un mensaje de un
canal simulado sigue recibiendo `422` del orquestador real (guarda intacta).
