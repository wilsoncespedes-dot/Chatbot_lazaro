# Requirements — #61 `registro_canales_gateway`

Fase 2 de la ampliación multicanal genérica (`docs/especificacion.md`,
«Ampliación multicanal genérica y multiagente»). El gateway de canales pasa a
arquitectura hexagonal: puerto `Canal`, `ChannelRegistry`, tabla `canales` en
Postgres con secretos cifrados, siembra de Telegram y WhatsApp desde las
variables actuales, degradación de bloques por capacidades y rutas internas de
administración de canales. Depende de #60 (`done`).

Fuera de alcance: `POST /webhooks/{canal_id}`, firma y callback (#62); adaptador
simulado (#63); cola y outbox (#64); núcleo sin nombres de canal y retiro de
`ATTENDED_CHANNELS` (#65); interfaz del panel y 404 de los webhooks heredados al
desactivar un canal (#66).

Quién cumple cada requirement:

- **contracts** (`contracts/lazaro_contracts`, `contracts/CONTRATOS.md`): R1–R4.
- **telegram_gateway**: R5–R50.
- **Configuración y despliegue** (`docker-compose.yml`, `render.yaml`,
  `requirements.txt`, `config.py`, `.env.example`): R51–R54.
- **Todos**: R55.

Definiciones:

- **Canal gestionado por el entorno**: canal cuyo tipo de adaptador lee sus
  credenciales de variables de entorno (`telegram`, `whatsapp_cloud`); no se
  crea por API ni guarda secretos.
- **Disponibilidad del adaptador**: Telegram siempre está disponible; WhatsApp
  lo está si el gateway tiene adaptador de WhatsApp (`Adapters.whatsapp` no es
  `None`, es decir `WHATSAPP_ENABLED=true` en producción).
- **Clave válida**: `CHANNEL_SECRETS_KEY` no vacía que `cryptography.fernet.Fernet`
  acepta (32 bytes en base64 url-safe, 44 caracteres).
- **Secreto de canal**: `secrets.token_urlsafe(32)` (32 bytes aleatorios, 43
  caracteres `[A-Za-z0-9_-]`).
- **Almacén de canales**: el repositorio de la tabla `canales`
  (`PostgresChannelRepository`; `FakeChannelRepository` en pruebas).

## Cobertura del acceptance de #61

| Criterio del acceptance | Requirements |
|---|---|
| Puerto `Canal` y un módulo por canal en `adapters/channels/` | R5, R9, R12–R14 |
| `ChannelRegistry` sin `if/else` por canal; desconocido o duplicado falla cerrado | R6–R10, R22 |
| Tabla `canales`, secretos cifrados con `cryptography`, nunca en logs ni listados | R27, R33–R37, R39 |
| Siembra de `telegram` y `whatsapp`, WhatsApp inactivo sin `WHATSAPP_ENABLED`, idempotente, sin cambios manuales | R29–R32, R34 |
| Migración sin perder funcionalidad; webhooks iguales; `/send` por el registry | R11, R14, R15, R22–R26, R55 |
| Degradación pura por capacidades | R16–R21 |
| Rutas internas con `X-Service-Token` documentadas en `CONTRATOS.md` | R1–R4, R38–R49 |
| Pruebas pedidas y batería actual verde | R55 (y la prueba de cada R) |
| Decisiones registradas: Postgres con `pg8000`, `cryptography`, salud y despliegue | R50–R54 |

## contracts

**R1.** El paquete `lazaro_contracts` DEBE exportar en `__all__` los modelos
`ChannelInfo`, `ChannelListResponse`, `ChannelCreateRequest`,
`ChannelCreateResponse`, `ChannelUpdateRequest`, `ChannelActiveRequest` y
`ChannelSecretResponse`, definidos en `lazaro_contracts/channel_registry.py`
con `extra="forbid"`.

**R2.** SI un cuerpo viola los límites del contrato de canales (`id` no es slug
de canal; `name` fuera de 1–60 caracteres, con caracteres de control o solo
espacios; `icon` fuera de 1–32 caracteres o con controles; `color` que no cumple
`^#[0-9A-Fa-f]{6}$`; `config` de más de 4096 bytes en JSON compacto o
profundidad mayor que 5; más de 20 `credentials`, nombre que no cumple
`^[a-z][a-z0-9_]{0,63}$` o valor fuera de 1–4096 caracteres; `secret` que no
cumple `^[A-Za-z0-9_-]{43}$`; `ChannelUpdateRequest` sin ningún campo; `active`
no booleano) ENTONCES el modelo DEBE lanzar `ValidationError`.

**R3.** `CONTRATOS.md` DEBE documentar `GET /channels`, `POST /channels`,
`PATCH /channels/{channel_id}`, `PATCH /channels/{channel_id}/active`,
`POST /channels/{channel_id}/secret` y `GET /channels/{channel_id}/secret` con el
formato de las demás rutas (`- **Expone:** telegram_gateway`, `- **Llama:**`,
`- **Modelos:**` con nombres de `__all__`, `#### Request` con todos los campos del
modelo, `#### Respuesta` con código de éxito y campos, `#### Errores` con
`401 unauthorized`, `422 validation_error` y los códigos propios) y un ejemplo
JSON por ruta que valide contra su modelo.

**R4.** `CONTRATOS.md` DEBE describir el comportamiento de #61: en `POST /send`,
canal sin fila → `422 validation_error`, canal inactivo → `422 channel_inactive`,
adaptador no disponible → `502 upstream_error`, almacén caído →
`503 channel_store_unavailable` y secretos ilegibles →
`503 channel_secrets_unavailable`; la tabla de degradación por capacidades; la
salud del gateway con Redis y PostgreSQL; los códigos nuevos en la tabla común
de errores; y S17 y la fila de `ImageBlock` sin el rechazo temporal de imágenes.

## telegram_gateway — puerto y registry

**R5.** `TelegramChannel` y `WhatsAppCloudChannel` DEBEN implementar el
protocolo `runtime_checkable` `Canal` de `telegram_gateway/ports/canal.py`
(`recibir_mensaje`, `enviar_mensaje`, `identificar_usuario`, `capacidades`), de
modo que `isinstance(instancia, Canal)` sea verdadero.

**R6.** CUANDO una clase se registra con `ChannelRegistry.register(<tipo>)`,
`ChannelRegistry.get(<tipo>)` DEBE devolver esa clase.

**R7.** SI se registra un `tipo_adaptador` ya registrado ENTONCES el registry
DEBE lanzar `DuplicateAdapterType` y conservar la clase registrada antes.

**R8.** SI se pide un `tipo_adaptador` no registrado ENTONCES
`ChannelRegistry.get` DEBE lanzar `UnknownAdapterType`.

**R9.** El registry por defecto `CHANNEL_REGISTRY` DEBE asociar exactamente
`telegram` → `TelegramChannel` y `whatsapp_cloud` → `WhatsAppCloudChannel`,
registrados con el decorador en `adapters/channels/telegram.py` y
`adapters/channels/whatsapp_cloud.py`.

**R10.** `main.py`, `registry.py` y `channel_service.py` NO DEBEN contener
comparaciones con nombres de canal concretos (`==`/`!=`/`in` contra `"telegram"`
o `"whatsapp"`), comprobado por una prueba que inspecciona el código fuente.

## telegram_gateway — Telegram y WhatsApp a través del puerto

**R11.** `capacidades(destino)` de `TelegramChannel` y de `WhatsAppCloudChannel`
DEBE informar de forma explícita `supports_buttons=true`, `supports_images=false`,
`supports_files=false` y `supports_audio=false`, conservando los demás campos
actuales (en WhatsApp, la ventana de 24 h del destino).

**R12.** CUANDO se llama `recibir_mensaje(payload)`, el adaptador DEBE devolver
el mismo `NormalizedMessage` que produce hoy la normalización del webhook
(Telegram: `message` de texto → `text`, sin texto → `unsupported`,
`callback_query` → `button` con `button_proof`; WhatsApp: un objeto `message` de
Meta con `normalize_message`) o `None` si el payload no trae un mensaje válido,
sin lanzar excepciones.

**R13.** CUANDO se llama `identificar_usuario(payload)`, el adaptador DEBE
devolver como texto el id externo del remitente (Telegram: el usuario de
`message` o `callback_query` con las reglas de respaldo de `extract_incoming` y
`extract_callback`; WhatsApp: `from`) o `None` si no existe.

**R14.** CUANDO se llama `enviar_mensaje(destino, bloques)`, el adaptador DEBE
delegar en el cliente vigente con el mismo efecto que hoy (Telegram:
`send_message(int(destino), render_blocks(bloques),
reply_markup=build_inline_keyboard(bloques))`; WhatsApp: `ChannelAdapter.send`)
y devolver su estado de entrega.

**R15.** `/telegram/webhook` y `/whatsapp/webhook` NO DEBEN consultar el almacén
de canales: con el almacén fallando responden y reenvían al orquestador igual
que antes.

## telegram_gateway — degradación (`domain.py`, sin IO)

**R16.** SI un `OptionsBlock` llega a un canal sin `supports_buttons` o con más
opciones que `max_options` ENTONCES `degrade_blocks` DEBE sustituirlo por un
`TextBlock` con las opciones numeradas (`1. A`, `2. B`, … separadas por salto de
línea).

**R17.** SI un `ListBlock` tiene menos opciones que `min_list_options` o más que
`max_list_options` ENTONCES `degrade_blocks` DEBE sustituirlo por un `TextBlock`
con las opciones numeradas.

**R18.** SI un `ImageBlock` llega a un canal sin `supports_images` ENTONCES
`degrade_blocks` DEBE sustituirlo por `LinkBlock(text=alt_text, url=url)` si el
canal tiene `supports_links`, o por `TextBlock("<alt_text>: <url>")` si no.

**R19.** SI un `LinkBlock` llega a un canal sin `supports_links` ENTONCES
`degrade_blocks` DEBE sustituirlo por `TextBlock("<text>: <url>")`, o por dos
`TextBlock` (texto y URL, en ese orden) si el texto combinado supera 4096
caracteres.

**R20.** `degrade_blocks` DEBE ser una función pura: conserva el orden y los
bloques que el canal admite, no modifica la lista de entrada y devuelve el mismo
resultado para la misma entrada, probado sobre combinaciones de
`supports_buttons`, `supports_images`, `supports_links` y límites de lista.

**R21.** CUANDO se envía una respuesta (`send_response` o `POST /send`), el
sistema DEBE aplicar `degrade_blocks` con las capacidades del destino antes de
las comprobaciones de ventana y plantilla, de modo que un bloque `image` por
Telegram o WhatsApp se entrega como enlace en lugar de responder `422`.

## telegram_gateway — `POST /send` por el registry

**R22.** CUANDO llega `POST /send`, el sistema DEBE obtener la fila de `canales`
del `channel` (`telegram` para el `SendRequest` legacy), construir su adaptador
con el registry y enviar los bloques con `enviar_mensaje`.

**R23.** SI el `channel` no tiene fila en `canales` ENTONCES `POST /send` DEBE
responder `422 validation_error` (`UnknownChannel`) sin enviar nada por ningún
canal.

**R24.** SI el `tipo_adaptador` de la fila no está registrado o su adaptador no
está disponible ENTONCES `POST /send` DEBE responder `502 upstream_error` sin
enviar nada, comprobación que precede a la de canal inactivo.

**R25.** SI el canal está inactivo ENTONCES `POST /send` DEBE responder
`422 channel_inactive` sin enviar nada.

**R26.** SI el almacén de canales falla ENTONCES `POST /send` y las rutas
`/channels…` DEBEN responder `503 channel_store_unavailable` sin enviar nada y
sin incluir el texto de la excepción.

## telegram_gateway — tabla `canales` y siembra

**R27.** CUANDO `PostgresChannelRepository` abre una conexión nueva, DEBE
ejecutar `CREATE TABLE IF NOT EXISTS canales` (`id` PK, `nombre`,
`tipo_adaptador`, `icono`, `color`, `config` JSONB, `activo`, `creado_en`) y
`ALTER TABLE canales ADD COLUMN IF NOT EXISTS` para `config_secreta` y
`activo_segun_entorno`, y todas sus consultas DEBEN usar parámetros `%s`.

**R28.** SI una operación falla por error de conexión (`OSError` o
`InterfaceError`) o la conexión lleva más de 10 s sin uso y no responde a
`SELECT 1` ENTONCES el repositorio DEBE descartarla y abrir otra en la siguiente
operación.

**R29.** CUANDO el gateway arranca (o, si no pudo, en el primer uso del
almacén), el sistema DEBE crear las filas que falten de `BUILTIN_CHANNEL_SEEDS`
(`telegram`: «Telegram», `telegram`, ícono `telegram`, `#1B6FA8`; `whatsapp`:
«WhatsApp», `whatsapp_cloud`, ícono `whatsapp`, `#0E7A5F`) con `config={}`, sin
secretos, `activo_segun_entorno=true` y `activo` igual a la disponibilidad de su
adaptador.

**R30.** MIENTRAS una fila tenga `activo_segun_entorno=true`, cada siembra DEBE
igualar su `activo` a la disponibilidad de su adaptador (WhatsApp se activa al
pasar `WHATSAPP_ENABLED` a `true` y se desactiva al volver a `false`, sin
cambios manuales).

**R31.** CUANDO la siembra se repite, el sistema NO DEBE crear duplicados ni
cambiar nombre, ícono, color, `config`, secretos ni el `activo` de una fila con
`activo_segun_entorno=false`.

**R32.** SI el almacén no está disponible al arrancar ENTONCES el gateway DEBE
arrancar igualmente, registrar `channels_seed_deferred` (solo el tipo de la
excepción) y reintentar la siembra en el siguiente uso del almacén.

## telegram_gateway — secretos

**R33.** CUANDO se guardan el secreto o las credenciales de un canal, el sistema
DEBE persistir en `canales.config_secreta` solo un token Fernet de
`{"secret", "credentials"}` cifrado con `CHANNEL_SECRETS_KEY`, que con la misma
clave se descifra a los valores originales.

**R34.** MIENTRAS `CHANNEL_SECRETS_KEY` esté vacía o no sea una clave válida, en
cualquier `APP_ENV`, el gateway DEBE arrancar y atender `/telegram/webhook`,
`/whatsapp/webhook`, `POST /send` por canales sin secretos, `GET /channels`,
`PATCH /channels/{channel_id}` sin `credentials` y
`PATCH /channels/{channel_id}/active`.

**R35.** SI una operación necesita cifrar o descifrar (crear un canal, enviar
`credentials`, regenerar o revelar el secreto, enviar por un canal con secretos
guardados) y la clave falta, no es válida o no descifra el token ENTONCES el
sistema DEBE responder `503 channel_secrets_unavailable` sin persistir cambios.

**R36.** CUANDO se crea la aplicación sin una clave válida, el gateway DEBE
registrar un WARNING `channel_secrets_key_unavailable` con `reason=missing` o
`reason=invalid`, sin el valor.

**R37.** El gateway NO DEBE incluir el secreto, las credenciales, el token de
`config_secreta` ni la clave en logs, mensajes de error, `repr` de sus objetos
ni en las respuestas de listado, edición y activación.

## telegram_gateway — rutas internas

**R38.** SI una petición a `/channels…` llega sin un `X-Service-Token` válido
ENTONCES el sistema DEBE responder `401 unauthorized`.

**R39.** CUANDO llega `GET /channels`, el sistema DEBE responder `200` con
`ChannelListResponse`: cada fila con sus metadatos públicos (`id`, `name`,
`adapter_type`, `icon`, `color`, `config`, `active`, `configured`,
`has_secrets`, `managed_by_environment`, `created_at`) ordenada por `created_at`
e `id`, y `adapter_types` con los tipos registrados que admiten canales nuevos.

**R40.** CUANDO llega un `POST /channels` válido con un tipo registrado no
gestionado por el entorno, el sistema DEBE crear la fila con un secreto de canal
nuevo y las `credentials` cifradas, y responder `201` con `ChannelCreateResponse`
(canal y secreto, que solo se muestra en esta respuesta y en
`GET /channels/{channel_id}/secret`).

**R41.** SI `POST /channels` usa un `id` que ya existe ENTONCES el sistema DEBE
responder `409 channel_exists` sin modificar la fila existente.

**R42.** SI `POST /channels` usa un `adapter_type` no registrado o gestionado por
el entorno ENTONCES el sistema DEBE responder `422 validation_error` sin
persistir nada.

**R43.** CUANDO llega un `PATCH /channels/{channel_id}` válido, el sistema DEBE
actualizar solo los campos enviados (`config` y `credentials` se reemplazan
completos; el secreto de canal se conserva) y responder `200` con `ChannelInfo`.

**R44.** SI se envían `credentials`, se regenera o se revela el secreto de un
canal gestionado por el entorno ENTONCES el sistema DEBE responder
`409 channel_managed_by_environment` sin cambios.

**R45.** CUANDO llega `PATCH /channels/{channel_id}/active`, el sistema DEBE
fijar `activo`, poner `activo_segun_entorno=false` (la siembra ya no lo cambia)
y responder `200` con `ChannelInfo`.

**R46.** CUANDO llega `POST /channels/{channel_id}/secret`, el sistema DEBE
generar un secreto de canal nuevo que reemplaza al anterior (que deja de estar
guardado) conservando las credenciales, y responder `200` con
`ChannelSecretResponse`.

**R47.** CUANDO llega `GET /channels/{channel_id}/secret`, el sistema DEBE
responder `200` con el secreto vigente en `ChannelSecretResponse`.

**R48.** CUANDO se regenera o se revela un secreto, el sistema DEBE registrar un
INFO `channel_secret_regenerated` o `channel_secret_revealed` con el
`channel_id` y sin el valor.

**R49.** SI el `{channel_id}` de una ruta `/channels/{channel_id}…` no existe, o
no tiene secreto guardado en `GET /channels/{channel_id}/secret`, ENTONCES el
sistema DEBE responder `404 not_found`.

## telegram_gateway — salud

**R50.** SI Postgres no responde a `SELECT 1` en una conexión independiente
dentro de `HEALTHCHECK_TIMEOUT_SECONDS` ENTONCES `GET /health` DEBE responder
`503 unhealthy` con `dependencies.postgres = "unavailable"` (y `redis` si también
falla), sin DSN, hostnames ni mensajes de excepción.

## Configuración y despliegue

**R51.** `docker-compose.yml` DEBE hacer depender `telegram_gateway` de
`postgres` con `condition: service_healthy`, además de `redis`.

**R52.** `services/telegram_gateway/requirements.txt` DEBE declarar exactamente
`fastapi`, `httpx`, `pydantic`, `pydantic-settings`, `redis`, `uvicorn`,
`pg8000>=1.31,<2` y `cryptography>=44,<48`, todas con cota doble.

**R53.** `Settings` del gateway DEBE leer `DATABASE_URL` (vacía por defecto) y
`CHANNEL_SECRETS_KEY` (`SecretStr`, vacía por defecto), declaradas en
`.env.example` con `CHANNEL_SECRETS_KEY=` vacía y el comando para generarla.

**R54.** `render.yaml` DEBE dar al servicio `telegram-gateway` `DATABASE_URL`
desde `lazaro-postgres` (`fromDatabase`, `connectionString`) y
`CHANNEL_SECRETS_KEY` con `sync: false`.

## Todos

**R55.** La batería existente de `services/telegram_gateway/tests` y
`contracts/tests` DEBE pasar sin modificaciones, salvo los cuatro tests que
`design.md` §7 sustituye por pruebas del comportamiento nuevo.
