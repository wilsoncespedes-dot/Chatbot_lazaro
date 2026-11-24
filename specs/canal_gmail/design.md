# Diseño — Canal Gmail

## Alcance

Un buzón de soporte autorizado por OAuth se registra como un canal normal. Un
trabajo periódico sincroniza correo entrante nuevo y el gateway envía las
respuestas del bot/asesor dentro del mismo hilo. Se procesa solo texto. Esta
feature no instala una conexión OAuth en vivo, no hace backfill anterior al
alta, no descarga archivos y no cambia el flujo vigente de consentimiento ni
login.

La sincronización usa polling incremental Gmail `users.history.list`, no
Pub/Sub. Esto evita añadir un servicio, endpoint público o infraestructura GCP
de mensajería al monorepo; el intervalo lo controla el scheduler existente del
despliegue.

## Archivos y firmas

- `services/telegram_gateway/telegram_gateway/adapters/gmail_api.py`: protocolo
  `GmailClient` y cliente HTTP Gmail API/OAuth con `httpx`. Métodos:
  `refresh_access_token`, `profile`, `list_history`, `get_message`, `get_thread`
  y `send_reply`.
- `services/telegram_gateway/telegram_gateway/adapters/gmail_history.py`:
  `GmailHistoryRepository` (`get_cursor`, `set_cursor`, `reset_cursor`), fake
  y PostgreSQL. Nueva tabla `gmail_history_state(channel_id PRIMARY KEY,
  history_id, updated_at)`; inicialización idempotente bajo el advisory lock de
  esquema del gateway.
- `services/telegram_gateway/telegram_gateway/adapters/channels/gmail.py`:
  factory registrada `gmail_api` y canal `GmailChannel`; `config.email_address`
  identifica el buzón; secretos cifrados: `client_id`, `client_secret`,
  `refresh_token`. El canal normaliza mensajes de entrada y responde al último
  remitente externo del `threadId` destino.
- `services/telegram_gateway/telegram_gateway/gmail_sync.py`:
  sincronizador inyectable. `sync(channel_id)` inicia cursor en el `historyId`
  actual si no hay estado, o procesa páginas incrementales; cursor solo avanza
  cuando todos los mensajes de las páginas quedan aceptados por el orquestador.
  `reset(channel_id)` toma el `historyId` actual y descarta explícitamente el
  backlog pendiente.
- `services/telegram_gateway/telegram_gateway/main.py`: rutas internas
  `POST /channels/{channel_id}/gmail/sync` y
  `POST /channels/{channel_id}/gmail/reset-cursor`, ambas protegidas por
  `X-Service-Token`; sync exige canal activo y reset es acción administrativa.
- `services/orchestrator/orchestrator/admin.py` y `admin_channels.py`: el panel
  de canales muestra `email_address` como campo opcional de configuración (se
  valida y guarda para Gmail) y reutiliza la entrada cifrada de credenciales.
- `services/orchestrator/tests/test_admin_canales.py`: cobertura de alta y
  validación de la bandeja Gmail desde el panel.
- `services/telegram_gateway/telegram_gateway/domain.py` y `main.py`: agregar
  los adaptadores/repositorios inyectables sin acoplar el dominio a HTTP.
- `scripts/sincronizar_gmail.py`: consulta `/channels`, sincroniza solo canales
  activos `gmail_api` y falla el proceso si alguna llamada falla.
- `services/telegram_gateway/tests/`: cobertura de API falsa, normalización,
  hilos, cursores, reintentos y autorización HTTP.
- `docs/gmail.md`, `README.md`, `contracts/CONTRATOS.md`,
  `contracts/tests/test_gmail_doc.py`, `.env.example` si el script requiere
  una URL/token de gateway adicionales.

## Flujo de entrada

1. El scheduler ejecuta `scripts/sincronizar_gmail.py` con URL y token de
   servicio; el script pide al gateway sincronizar cada canal Gmail activo.
2. El gateway resuelve credenciales cifradas del canal y renueva el token
   OAuth. La primera ejecución guarda el `historyId` actual y termina sin leer
   correo histórico.
3. En ejecuciones siguientes pide `users.history.list` con `startHistoryId`,
   recoge `messagesAdded` de `INBOX`, pagina todos los resultados y carga cada
   mensaje con `format=full`.
4. Ignora mensajes cuyo `From` coincide con `config.email_address`. Para los
   demás extrae remitente, `threadId`, id, fecha, asunto y cuerpo `text/plain`;
   si no hay texto normaliza como `unsupported`. No solicita partes ni bytes de
   adjuntos.
5. Entrega cada mensaje normalizado con `orchestrator.post_message`. El
   orquestador ya deduplica por `(canal, external_message_id)` y persiste el
   mensaje en su inbox transaccional. Si la petición falla, no se guarda el
   nuevo cursor; al reintentar, la deduplicación del orquestador evita repetir
   los ya aceptados.
6. Solo después de aceptar todos los mensajes, persiste el `historyId` final.
   Un `404` Gmail por cursor vencido devuelve error `gmail_history_expired`;
   no salta mensajes de manera silenciosa. El admin puede ejecutar reset, que
   inicia desde el estado actual y explícitamente ignora mensajes anteriores.

## Flujo de salida

1. El destino del outbox es `NormalizedMessage.external_chat_id` (Gmail
   `threadId`), como en los demás canales.
2. `GmailChannel.enviar_mensaje` obtiene los mensajes del hilo y elige el
   último `From` que no sea el buzón conectado. Usa ese remitente como `To`, y
   los headers `Message-ID`/`References` del correo externo más reciente para
   construir `In-Reply-To` y `References`.
3. Convierte bloques a texto plano (reutiliza `render_blocks`), crea MIME con
   `EmailMessage`, codifica base64url y llama a `users.messages.send` con
   `threadId`. No usa HTML generado por el modelo ni envía adjuntos.

## Seguridad y privacidad

- Los secretos Gmail aprovechan el cifrado y las pistas existentes del
  registro `canales`; nunca se incluyen en `/channels`, logs ni errores.
- Los requests solo usan hosts fijos `oauth2.googleapis.com` y
  `gmail.googleapis.com`; timeout heredado de `HTTP_TIMEOUT_SECONDS`.
- Se solicitan únicamente `gmail.readonly` y `gmail.send`. Google clasifica
  `gmail.readonly` como restringido y `gmail.send` como sensible; el propietario
  debe configurar consentimiento/verificación OAuth y revisar los requisitos
  de seguridad para su despliegue. No se pide `mail.google.com` ni permisos de
  borrado.
- El cuerpo del correo queda sujeto a consentimiento, identidad, retención,
  supresión y logging actuales del orquestador. Correo sin consentimiento
  recibe el aviso vigente y no se responde con contenido del negocio.
- Los logs contienen solo canal, conteos, operación y código HTTP; nunca
  dirección del cliente, asunto, cuerpo, token, refresh token ni payload Gmail.
- La sincronización puede aceptar parte de una página antes de un error; la
  repetición es segura porque el orquestador aplica deduplicación persistente.

## Dependencias

- No se agrega paquete de ejecución: se usa `httpx` existente y módulos de la
  biblioteca estándar (`email`, `base64`, `json`).
- Gmail API REST: `users.getProfile`, `users.history.list`, `users.messages.get`,
  `users.threads.get`, `users.messages.send`; OAuth refresh token endpoint.
- Scopes OAuth: `https://www.googleapis.com/auth/gmail.readonly` y
  `https://www.googleapis.com/auth/gmail.send`.

## Alternativa descartada

Pub/Sub `users.watch` da notificaciones push, pero exige tema, suscripción,
renovación semanal y verificación OIDC pública. Para un primer canal, un cron
que usa Gmail History es más sencillo de desplegar y reintentar. El límite de
notificación no afecta al polling; el scheduler deberá ejecutar el script con
la frecuencia operativa elegida.

## Supuestos a confirmar

- Un canal representa una bandeja compartida/dedicada de soporte, no el Gmail
  personal de cada cliente.
- El dueño/administrador configura OAuth para el buzón y provee
  `client_id`, `client_secret` y un `refresh_token` con los dos scopes
  indicados. La conexión real se habilita solo después de guardar esas
  credenciales cifradas y activar el canal.
- Polling cada 5 segundos es el valor predeterminado para reducir la latencia; la
  frecuencia será responsabilidad del scheduler, sin configuración nueva en
  el gateway.
- Correo solo texto en esta iteración. Mensajes HTML-only o solo con adjuntos
  siguen el rechazo existente de tipo no soportado.

## Fuentes oficiales consultadas

- [Scopes de Gmail API](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Sincronización Gmail](https://developers.google.com/workspace/gmail/api/guides/sync)
- [Enviar mensajes Gmail](https://developers.google.com/workspace/gmail/api/guides/sending)
- [Administrar hilos Gmail](https://developers.google.com/workspace/gmail/api/guides/threads)
