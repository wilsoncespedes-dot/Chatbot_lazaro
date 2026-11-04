# Design — nucleo_multicanal (feature #36)

## Alcance

Esta fase introduce el vocabulario común y el límite de adaptadores para ambos
canales. Telegram sigue usando su integración de producción existente. WhatsApp
usa únicamente `FakeWhatsAppAdapter`; el proveedor real y su webhook/credenciales
quedan para #43. No se añade un servicio nuevo ni se decide proveedor.

## Archivos a crear o modificar

- `contracts/CONTRATOS.md`: documentar el formato normalizado y la respuesta
  abstracta usados en los límites gateway/orchestrator.
- `contracts/lazaro_contracts/channels.py` y `contracts/lazaro_contracts/__init__.py`:
  modelos compartidos de canal, mensaje y bloques de respuesta.
- `contracts/lazaro_contracts/messages.py`: conservar el payload legacy de
  `MessageRequest` y añadir `NormalizedMessage` como request canónico para
  `POST /messages`; el validador legacy lo traduce a canal `telegram` y usa
  `update_id` como `external_message_id`. `SendRequest` conserva el formato
  legacy Telegram y añade la variante canónica con canal, destino y bloques.
- `contracts/examples/` y `contracts/tests/`: ejemplos y validación de los
  nuevos modelos/contratos, incluidos los campos obligatorios.
- `services/telegram_gateway/telegram_gateway/domain.py`: normalizar el update
  Telegram al modelo común y construir la respuesta abstracta.
- `services/telegram_gateway/telegram_gateway/adapters/telegram.py`: implementar
  la interfaz común y renderizar bloques compatibles a Telegram conservando
  `FakeTelegramClient` y el cliente real existentes.
- `services/telegram_gateway/telegram_gateway/adapters/whatsapp.py` (nuevo):
  definir protocolo/capacidades y `FakeWhatsAppAdapter`; no contiene HTTP ni
  credenciales de un proveedor real.
- `services/telegram_gateway/telegram_gateway/adapters/dedup.py` y el punto de
  entrada correspondiente: componer la clave de deduplicación con canal e ID
  externo, conservando la caducidad ya configurada.
- `services/orchestrator/orchestrator/domain.py` y
  `services/orchestrator/orchestrator/adapters/repository.py`: usar la clave
  compuesta para deduplicación persistente y conservar el resto del flujo.
- `services/orchestrator/orchestrator/domain.py`: extender `Contact` con
  `channel`, `external_user_id` y `external_chat_id`; mantener `telegram_user_id`
  y `chat_id` opcionales solo para compatibilidad Telegram y no asignar
  `client_id` antes del login.
- `services/orchestrator/orchestrator/adapters/repository.py`: generalizar las
  operaciones `get_or_create_contact`, `has_privacy_consent` y
  `add_privacy_consent` a la identidad `(channel, external_user_id)` en el
  repositorio Postgres y `FakeRepository`; mantener wrappers legacy Telegram.
- Esquema Postgres gestionado desde `repository.py`: migración idempotente de
  `contacts` y `privacy_consents` con `channel` y `external_user_id`, índices
  compuestos, backfill de filas existentes como Telegram y columnas legacy
  `telegram_user_id`/`chat_id` nullable para permitir filas WhatsApp. Añadir
  `external_chat_id` de texto y backfillearlo desde `chat_id`. No se modifica
  `profiles.telegram_user_id`, que sigue identificando personal Telegram.
- Tests de repositorio/privacidad: validar contactos y consentimientos
  separados ante IDs numéricos iguales, migración/backfill repetido, no escritura
  del ID WhatsApp en la columna legacy y ausencia de vínculo antes de #38.
- `services/orchestrator/tests/test_multichannel_identity.py` (nuevo): pruebas
  de colisión numérica, consentimiento por canal, forma de contacto WhatsApp y
  compatibilidad Telegram; incluye lookup de contacto por pareja tras
  consentimiento vigente y flujo sin persistencia de contacto antes del
  consentimiento.
- `services/orchestrator/tests/test_repository_schema.py` (nuevo): pruebas
  unitarias con conexión falsa que ejecutan el DDL/backfill más de una vez y
  comparan datos antes/después; no requiere Postgres.
- Tests de contratos, gateway y orquestador afectados: cubrir los requirements
  sin llamadas de red reales.

## Tipos e interfaces

- `NormalizedMessage`: `channel`, `external_user_id`, `external_chat_id`,
  `external_message_id`, `kind`, `text`/`button_id` opcionales y `received_at`.
  `client_id` queda vacío hasta la fase de identidad. Los adaptadores no lo
  envían ni pueden establecerlo.
- `Contact`: incluye el par de identidad técnica, `external_chat_id` y los
  campos legacy Telegram opcionales. El adaptador WhatsApp no convierte los IDs
  de usuario/chat a enteros.
- `ResponseBlock`: unión discriminada de `TextBlock`, `OptionsBlock`,
  `ListBlock`, `LinkBlock` y `TemplateBlock`, respetando los topes de la
  especificación (opciones: máximo 3, 20 caracteres; lista: 4–10; un enlace).
- `ChannelCapabilities`: indica si texto libre está permitido, límites de
  opciones/lista, soporte de enlaces y si se requiere plantilla.
- `ChannelAdapter` expone normalización de entrada, lectura de capacidades y
  envío de bloques al destino externo y traducción de estados de entrega al
  vocabulario común `sent`, `delivered`, `read`, `failed`. El adaptador falso
  permite configurar ventana abierta/cerrada, plantillas aprobadas, resultado
  de entrega y errores de envío.
- El protocolo `Repository` recibe `get_or_create_contact(channel,
  external_user_id, external_chat_id, now)`, `has_privacy_consent(channel,
  external_user_id, notice_version)` y `add_privacy_consent(channel,
  external_user_id, notice_version, notice_sha256, accepted_at)`. `Contact` y
  `PrivacyConsent` exponen los campos de canal/ID externo además de los campos
  legacy opcionales necesarios para el flujo Telegram.
- La clave persistente de idempotencia es una composición no ambigua de
  `(channel, external_message_id)`, tanto en Redis como en el repositorio del
  orquestador. No se usa el ID externo aislado como clave.
- La identidad técnica y el consentimiento anteriores al login usan
  `(channel, external_user_id)`. Ambos valores son texto: un mismo número en
  Telegram y WhatsApp genera contactos independientes. Una fila WhatsApp deja
  `telegram_user_id` y `chat_id` en NULL y conserva los IDs externos como texto.
- Al procesar un remitente sin consentimiento vigente, la compuerta consulta la
  evidencia con la pareja en memoria y no crea contacto. El único write
  permitido es una fila de evidencia `privacy_consents` asociada a esa pareja.
  Después de consentimiento vigente, el contacto se busca o crea con la misma
  pareja.
- Las aceptaciones antiguas se migran a
  `(telegram, str(telegram_user_id), notice_version)` con fecha, versión y hash
  intactos. Los contactos Telegram conservan su `id` y todas sus relaciones;
  se añaden `external_user_id = str(telegram_user_id)` y
  `external_chat_id = str(chat_id)`, con el par compuesto como clave de
  búsqueda/unicidad. La segunda ejecución no duplica contactos ni reescribe
  relaciones o evidencia.
- En `privacy_consents`, `telegram_user_id` histórico se conserva, se vuelve
  nullable para filas nuevas WhatsApp y se agrega índice de consulta por
  `(channel, external_user_id, notice_version)`; el ID WhatsApp no se castea a
  número.
- Las funciones legacy que reciben un `telegram_user_id` delegan a
  `("telegram", str(telegram_user_id))`; las funciones nuevas reciben ambos
  campos. La compuerta de privacidad consulta o crea evidencia usando la pareja.
- El adaptador no establece `client_id`. La unión entre identidades de canales
  queda para #38, después de login verificado; #36 no implementa credenciales,
  sesiones ni vinculación.

## Compatibilidad y seguridad

- El contrato existente `POST /messages` acepta tanto el payload legacy como
  `NormalizedMessage`; el legacy se convierte al modelo común con `channel =
  telegram` y `external_message_id = str(update_id)`. Las nuevas entradas
  llevan `channel`, `external_user_id`, `external_chat_id`,
  `external_message_id`, `kind`, contenido y `received_at`. El gateway no
  permite que el payload de canal asigne `client_id`.
- `POST /send` mantiene la forma legacy de texto Telegram mientras acepta el
  destino/canal y los bloques abstractos necesarios para el adaptador inyectado.
- El gateway fake no abre sockets ni requiere secretos. El acceso real a
  WhatsApp se implementará exclusivamente en #43.
- Fuera de ventana, la política falla cerrada: `send_text` no se llama; solo se
  aceptan plantillas que el adaptador marca aprobadas.
- La deduplicación de Telegram existente puede seguir en el gateway como
  optimización, pero el registro persistente del orquestador es la barrera
  autoritativa y usa la clave compuesta.
- Para un request Telegram legacy, `external_user_id` se obtiene de
  `telegram_user_id` como texto. El request WhatsApp nunca escribe ni consulta
  esa columna; el vínculo de perfiles staff Telegram permanece igual.
- Antes del consentimiento no se insertan filas en `processed_messages`. Los
  requests canónicos de cualquier canal y los requests cuando privacidad no
  está configurada tampoco persisten claves de deduplicación. Única excepción:
  el endpoint Telegram legacy conserva el comportamiento de #35, que registra
  solo `update_id` en `processed_updates`, sin identidad ni payload.
- La migración de instalación existente debe ser aditiva e idempotente: no
  cambia contact IDs, mensajes, casos ni el historial de consentimientos.

## Excepciones y dependencias

Se reutilizan las respuestas de error actuales (`unauthorized`,
`validation_error`, `upstream_error`/error de adaptador e `internal_error`). No
hacen falta dependencias nuevas. Los fakes se inyectan en las pruebas.

## Alternativa descartada

Se descarta añadir ahora un proveedor WhatsApp concreto: la especificación deja
Cloud API, Twilio y 360dialog sin elegir. La interfaz y el fake permiten probar
la política y el flujo sin convertir esa decisión en un supuesto silencioso.

## Dependencias

- **#35 — `consentimiento_antes_de_datos` (completada):** #36 conserva su
  compuerta preconsentimiento y usa la identidad por canal para consultar o
  escribir la evidencia autorizada; no vuelve a ampliar lo permitido antes de
  aceptar.
- **#38 — `identidad_credenciales` (posterior):** podrá asociar `client_id` a
  identidades de canal solo después del login verificado. #36 no necesita el
  login para separar los pares y no implementa sus endpoints ni sesiones.
- **#43 — `proveedor_whatsapp_real` (posterior):** consumirá la interfaz de
  adaptador; no afecta al esquema de identidad por canal de #36.

## Supuestos a confirmar

Se supone que la instalación actual actualiza el esquema mediante DDL
idempotente al inicializar el repositorio, preservando datos y relaciones
existentes. Los IDs externos son opacos y se almacenan como texto, aunque su
valor parezca numérico.
