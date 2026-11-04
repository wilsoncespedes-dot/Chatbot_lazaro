# Implementación — nucleo_multicanal (feature #36)

## Resumen

- Se añadió el vocabulario común en `contracts/lazaro_contracts/channels.py`
  (`NormalizedMessage`, `ResponseBlocks` y sus bloques, `ChannelCapabilities`,
  `ChannelSendRequest` y estados de entrega) y se exportó desde el paquete.
- `POST /messages` acepta el payload Telegram histórico y el `NormalizedMessage`
  canónico. El legacy se traduce a `channel = telegram` con
  `external_message_id = str(update_id)`.
- `POST /send` mantiene `SendRequest` y acepta la variante canónica
  `ChannelSendRequest`; el gateway elige el adaptador y aplica capacidades antes
  de enviar.
- El gateway normaliza updates de Telegram y usa una clave de deduplicación
  `(channel, external_message_id)` en Redis. El orquestador persiste la misma
  clave compuesta en `processed_messages`.
- `FakeWhatsAppAdapter` implementa la interfaz común, la ventana de 24 horas y
  las plantillas aprobadas sin red ni credenciales. Telegram conserva sus
  envíos legacy y renderiza los bloques abstractos.
- No se añadieron dependencias ni variables de entorno.

## Trazabilidad

- R1 → `contracts/tests/test_channels.py::test_normalized_message_accepts_both_channels`, `::test_legacy_message_translates_to_telegram_channel`; `services/telegram_gateway/tests/test_multicanal.py::test_telegram_update_is_normalized_to_common_message`
- R2 → `contracts/tests/test_channels.py::test_text_block_accepts_text`, `::test_options_block_limits_count_and_length`, `::test_list_block_requires_between_four_and_ten_options`, `::test_link_block_requires_text_and_url`, `::test_template_block_accepts_name_and_variables`, `::test_response_blocks_allows_only_one_link`; `services/telegram_gateway/tests/test_multicanal.py::test_telegram_adapter_renders_abstract_blocks`
- R3 → `services/telegram_gateway/tests/test_multicanal.py::test_telegram_adapter_send_keeps_legacy_text_delivery`, `::test_webhook_uses_composed_dedup_key`; `services/telegram_gateway/tests/test_grouping.py::test_single_message_longer_than_contract_limit_is_not_buffered`; tests previos de `test_webhook.py` y `test_send.py`
- R4 → `services/telegram_gateway/tests/test_multicanal.py::test_fake_whatsapp_normalizes_text_and_button_messages`, `::test_fake_whatsapp_sends_text_inside_window`, `::test_canonical_send_uses_injected_whatsapp_adapter`
- R5 → `services/orchestrator/tests/test_multicanal_dedup.py::test_same_channel_same_external_id_is_duplicate`, `::test_legacy_update_id_uses_telegram_channel_key`, `::test_dedup_is_atomic_under_concurrency`, `::test_messages_accepts_canonical_and_detects_duplicate`; `services/telegram_gateway/tests/test_multicanal.py::test_dedup_store_isolates_same_id_between_channels`
- R6 → `services/orchestrator/tests/test_multicanal_dedup.py::test_same_external_id_in_two_channels_is_not_duplicate`, `::test_messages_processes_same_id_once_per_channel`, `::test_postgres_dedup_uses_composite_parameters`; `services/telegram_gateway/tests/test_multicanal.py::test_redis_dedup_key_includes_channel`
- R7 → `services/telegram_gateway/tests/test_multicanal.py::test_core_checks_capabilities_before_send`, `::test_canonical_send_without_adapter_returns_502`
- R8 → `services/telegram_gateway/tests/test_multicanal.py::test_fake_whatsapp_capabilities_follow_window`, `::test_closed_window_rejects_free_text`, `::test_canonical_send_fails_closed_outside_window`
- R9 → `services/telegram_gateway/tests/test_multicanal.py::test_closed_window_allows_approved_template_only`, `::test_canonical_send_allows_approved_template`
- R10 → `services/telegram_gateway/tests/test_multicanal.py::test_both_adapters_preserve_the_same_abstract_response`
- R11 → `services/telegram_gateway/tests/test_multicanal.py::test_no_network_is_used`
- R12 → `services/telegram_gateway/tests/test_multicanal.py::test_send_failure_is_simulable_and_status_is_common_vocabulary`, `::test_no_network_is_used`

## Correcciones tras la revisión de código

### Regresión de texto Telegram largo (P1.3)

- Fallo previo: `services/telegram_gateway/tests/test_grouping.py::test_single_message_longer_than_contract_limit_is_not_buffered`.
  El webhook validaba el update de 4097 caracteres como `NormalizedMessage`
  (límite 4096) antes de que el flujo legacy pudiera tratarlo como no procesable,
  y la `ValidationError` acababa en `500 internal_error`.
- Corrección en `services/telegram_gateway/telegram_gateway/main.py`: si la
  normalización de un update lanza `ValidationError`, el webhook conserva la
  clave de idempotencia de Telegram (`telegram`, `str(update_id)`) y deja que la
  rama legacy lo registre y lo descarte sin reenviarlo. Los updates válidos se
  siguen normalizando igual (R1, R3).

### Deduplicación histórica (P1.1)

- `RedisDedupStore` consulta `gw:update:<id>` antes de marcar Telegram y migra la
  marca a `gw:message:telegram:<id>`; las claves nuevas siguen escribiendo también
  la clave histórica para no romper despliegues mixtos. `FakeDedupStore` hace la
  misma comprobación con su estado legacy.
- `PostgresRepository` crea `processed_updates` si no existe y, en la propia
  sentencia de deduplicación de Telegram, descarta los ids presentes en esa
  tabla histórica. No borra ni modifica `processed_updates` ni copia filas al
  inicializar la conexión.
- Tests nuevos: `test_redis_dedup_preserves_legacy_update_key`,
  `test_fake_dedup_preserves_legacy_update_key` y
  `test_postgres_honors_legacy_processed_updates`.

### Mensajes canónicos de WhatsApp (P1.2)

- `POST /messages` ya no acepta y descarta WhatsApp: traduce el
  `NormalizedMessage` de texto al flujo interno existente y procesa el mensaje
  (contacto, historial, RAG, LLM y respuesta). El destino interno entero de los
  resultados RAG se deriva de forma estable de `(canal, mensaje_externo_id)`.
- La respuesta se envía al canal de origen mediante `ChannelBoundGateway` y la
  variante canónica `ChannelSendRequest` de `POST /send`. Telegram conserva su
  envío legacy. No se añade proveedor real ni identidad/login de #38.
- Si el destino externo no se puede representar en el flujo legacy de Telegram,
  la ruta lo procesa con identidad de canal y bloques abstractos en lugar de
  rechazarlo o perderlo.
- Tests nuevos: `test_canonical_whatsapp_message_is_processed_and_answered`,
  `test_same_canonical_message_produces_the_same_answer_in_both_channels`,
  `test_canonical_telegram_with_opaque_ids_is_accepted_as_text` y
  `test_http_gateway_send_channel_uses_canonical_contract`.

## Trazabilidad adicional

- R1, R10 → `services/orchestrator/tests/test_multicanal_flow.py::test_canonical_whatsapp_message_is_processed_and_answered`, `::test_same_canonical_message_produces_the_same_answer_in_both_channels`
- R5, R6 → `services/telegram_gateway/tests/test_multicanal.py::test_redis_dedup_preserves_legacy_update_key`, `::test_fake_dedup_preserves_legacy_update_key`; `services/orchestrator/tests/test_multicanal_dedup.py::test_postgres_honors_legacy_processed_updates`
- R7, R10 → `services/orchestrator/tests/test_adapters.py::test_http_gateway_send_channel_uses_canonical_contract`

## Corrección de la regresión Postgres (P1.1)

- La migración `INSERT ... SELECT` que se ejecutaba al abrir la conexión se
  eliminó: añadía una sentencia no relacionada a las operaciones Postgres y
  rompía cuatro tests que exigen una sola consulta o solo lecturas.
- En su lugar, `mark_message_if_new` resuelve la compatibilidad histórica en
  una única sentencia: para Telegram inserta en `processed_messages` con
  `SELECT ... WHERE NOT EXISTS (SELECT 1 FROM processed_updates ...)`, y para
  el resto de canales mantiene el `INSERT ... VALUES` actual.
- No se escriben ni borran filas de `processed_updates`; siguen descartando
  repetidos históricos y no se ejecutan consultas adicionales por operación.
- El test de la migración se reemplazó por
  `test_postgres_honors_legacy_processed_updates`, que verifica el mismo
  comportamiento (R5) sin depender de una sentencia de inicialización.

## Verificación

- Línea base antes de implementar: `2143 passed, 1 skipped, 1 warning`.
- Primera verificación tras cambios: `1 failed, 2215 passed, 1 skipped`.
- Tras corregir el caso Telegram de 4097 caracteres: `2216 passed, 1 skipped,
  1 warning` (2026-11-03). La suite quedó verde en ese checkpoint.
- Corrida tras los cambios de la revisión: `4 failed, 2219 passed, 1 skipped`.
- Tras eliminar la migración Postgres y consultar los históricos en la propia
  sentencia de deduplicación: `2223 passed, 1 skipped, 1 warning`
  (`./init.sh`, 2026-11-03). Todos los tests pasan; T8 está `[x]`.
- Los hallazgos de revisión sobre deduplicación legacy, mensajes canónicos y
  texto Telegram largo tienen cambios y tests asociados. La revisión adicional
  detectó que `_legacy_from_normalized` mapeaba `external_user_id` de WhatsApp a
  `telegram_user_id`, con riesgo de compartir contacto/consentimiento.

## Continuación aprobada

- El usuario aprobó identidad y consentimiento por `(channel, external_user_id)`
  en #36. Continuar desde T9–T14 del spec actualizado, preservar T1–T8 y las
  modificaciones previas de #35.
- El último init del alcance previo pasó: `2223 passed, 1 skipped, 1 warning`.
  Esta evidencia no cubre T9–T14; ejecutar la suite al completar esta fase.

## Corrección requerida antes de verificar T9–T14

- Revisión del leader contra R21/T10: `POST /messages` todavía llama
  `mark_message_if_new` antes de la compuerta. Para un remitente WhatsApp sin
  consentimiento, eso persiste `(channel, external_message_id)` en
  `processed_messages`, aunque el test actual solo comprueba contactos,
  mensajes, eventos y consentimiento.
- Ajuste solicitado: no escribir `processed_messages` para WhatsApp antes del
  consentimiento; usar el dedup temporal/TTL del gateway. Tras consentimiento,
  conservar la idempotencia persistente por clave compuesta. Para Telegram
  legacy, mantener la excepción previamente aprobada de `processed_updates`
  con solo `update_id`. Añadir aserciones que prueben que el gate preconsentimiento
  no persiste identidad ni IDs de mensaje fuera de `privacy_consents`.

## T9–T13: identidad y consentimiento por canal

### Contactos

- `Contact` añade `channel`, `external_user_id` y `external_chat_id`; los campos
  `telegram_user_id` y `chat_id` pasan a opcionales y solo se rellenan en
  Telegram. `client_id` sigue ausente (R19).
- `FakeRepository` indexa Telegram por su entero histórico (para no romper a los
  consumidores y tests de #35) y el resto de canales por
  `(channel, external_user_id)`. Un mismo `10` en Telegram y WhatsApp crea dos
  contactos con ids internos distintos (R14).
- `PostgresRepository` incorpora `get_or_create_channel_contact`, que guarda
  `channel` e ids externos como texto y deja `telegram_user_id`/`chat_id` en
  NULL para WhatsApp (R16). Los wrappers legacy `get_or_create_contact`,
  `has_privacy_consent` y `add_privacy_consent` delegan en la pareja
  `("telegram", str(id))`, así que el flujo histórico también usa la identidad
  de canal (R13, R15).
- El mensaje canónico de WhatsApp ya no se traduce a `MessageRequest` ni a
  `telegram_user_id`: `process_channel_message` usa la pareja, la compuerta
  preconsentimiento y el gateway multicanal. Telegram canónico conserva el flujo
  legacy (R3, R13, R16).
- Antes del consentimiento la compuerta resuelve la pareja en memoria, envía el
  aviso por su canal y solo permite escribir la evidencia en `privacy_consents`
  (R21).

### Esquema y migración

- `_SCHEMA` declara `contacts(channel, external_user_id, external_chat_id)` con
  `telegram_user_id`/`chat_id` nullable y `privacy_consents(channel,
  external_user_id)` con `telegram_user_id` nullable.
- `_MIGRATIONS` aplica DDL aditivo e idempotente: añade columnas, elimina los
  `NOT NULL` legacy, rellena `channel = 'telegram'`,
  `external_user_id = CAST(telegram_user_id AS TEXT)` y
  `external_chat_id = CAST(chat_id AS TEXT)`, y crea los índices compuestos.
  Nunca cambia ids, mensajes, casos, versión, hash ni fecha de aceptación
  (R17, R18).
- En producción (`connect` real) la migración se ejecuta al abrir la conexión.
  Las conexiones falsas de los tests la activan explícitamente con
  `run_migrations=True` para verificar el DDL sin Postgres.

## Trazabilidad adicional (T9–T14)

- R13 → `services/orchestrator/tests/test_multichannel_identity.py::test_contact_lookup_uses_channel_and_external_user_id`, `::test_legacy_telegram_contact_gets_channel_and_external_ids`
- R14 → `services/orchestrator/tests/test_multichannel_identity.py::test_same_numeric_id_in_telegram_and_whatsapp_stays_separate`; `services/orchestrator/tests/test_multicanal_flow.py::test_same_canonical_message_produces_the_same_answer_in_both_channels`
- R15 → `services/orchestrator/tests/test_multichannel_identity.py::test_consent_is_independent_by_channel`; `services/orchestrator/tests/test_multicanal_flow.py::test_canonical_whatsapp_message_is_processed_and_answered`
- R16 → `services/orchestrator/tests/test_multichannel_identity.py::test_whatsapp_identity_never_uses_the_telegram_column`; `services/orchestrator/tests/test_repository_schema.py::test_whatsapp_postgres_identity_keeps_telegram_columns_null`; `services/orchestrator/tests/test_multicanal_flow.py::test_whatsapp_opaque_external_id_is_kept_as_text`
- R17 → `services/orchestrator/tests/test_repository_schema.py::test_legacy_contacts_are_backfilled_preserving_ids_and_relations`, `::test_migration_is_idempotent_when_run_more_than_once`; `services/orchestrator/tests/test_multichannel_identity.py::test_legacy_telegram_contact_gets_channel_and_external_ids`
- R18 → `services/orchestrator/tests/test_repository_schema.py::test_legacy_consents_are_backfilled_without_losing_version_hash_or_date`, `::test_migration_is_idempotent_when_run_more_than_once`
- R19 → `services/orchestrator/tests/test_multichannel_identity.py::test_contacts_have_no_client_id_and_channels_are_not_linked`
- R20 → tests de R13–R18 anteriores y `services/orchestrator/tests/test_repository_schema.py::test_whatsapp_postgres_identity_keeps_telegram_columns_null`
- R21 → `services/orchestrator/tests/test_multichannel_identity.py::test_before_consent_no_contact_or_personal_data_is_persisted`, `::test_acceptance_before_contact_only_writes_privacy_consent`, `::test_canonical_telegram_before_consent_does_not_persist_message_id`, `::test_persistent_dedup_starts_after_channel_consent`

## Corrección del gate preconsentimiento (R21)

- `POST /messages` ya no llama `mark_message_if_new` para un mensaje canónico
  sin consentimiento vigente. La compuerta sigue resolviendo la pareja en
  memoria, envía el aviso o escribe solo la evidencia en `privacy_consents`, y
  no persiste `processed_messages` ni crea contacto.
- Tras el consentimiento, la clave compuesta `(channel, external_message_id)`
  vuelve a ser la barrera persistente; así se conserva R5/R6 sin datos previos
  al consentimiento.
- El payload legacy de Telegram conserva la excepción aprobada de #35:
  `mark_message_if_new` sigue registrando el `update_id` histórico, y los tests
  de `test_consent_before_data.py` que lo exigen no cambian.
- Tests nuevos/actualizados: los de deduplicación canónica ahora consienten
  antes de comprobar duplicados; se añadieron aserciones de que el gate no deja
  ids de mensaje ni contactos antes de consentir y de que la deduplicación
  persistente empieza después.

## Corrección de los tres fallos de la última verificación

### Esquema Postgres parametrizado (P1.1)

- `_SCHEMA` ya no usa el literal `DEFAULT 'telegram'` en `contacts.channel` ni
  `privacy_consents.channel`: las filas nuevas siempre reciben el canal por
  parámetro y las instalaciones existentes lo rellenan con la migración
  idempotente. Esto restaura `test_postgres_repository_uses_parameters_only`
  sin cambiar el SQL de lectura/escritura (R13, R16, R17, R18).

### Telegram canónico con id de mensaje opaco (P1.2)

- `POST /messages` valida que un Telegram canónico de texto tenga
  `external_user_id` y `external_chat_id` numéricos (si no, `422`), pero ya no
  exige que `external_message_id` sea convertible a entero. Si es opaco, el
  mensaje se procesa con identidad `(channel, external_user_id)` y clave de
  deduplicación compuesta, sin inventar un `update_id` (R1, R3, R13, R21).
- `_notify_channel` usa el envío legacy de Telegram cuando el destino es un
  chat numérico, de modo que el aviso preconsentimiento de un Telegram
  canónico llega por el mismo camino existente (R3, R21).

### Fallo síncrono al guardar consentimiento (P1.3)

- Las aceptaciones que se procesan en la petición HTTP llaman directamente a
  `process_message`/`process_channel_message`, sin el wrapper que absorbe
  errores de los `BackgroundTasks`. Si falla la escritura de la evidencia, la
  ruta responde `500 internal_error` y no envía confirmación (R21 y R17/R18 de
  #35).

## Trazabilidad de las correcciones

- R3, R13, R21 → `services/orchestrator/tests/test_multichannel_identity.py::test_canonical_telegram_before_consent_does_not_persist_message_id`
- R13, R16, R17, R18 → `services/orchestrator/tests/test_adapters.py::test_postgres_repository_uses_parameters_only`
- R21 → `services/orchestrator/tests/test_privacy.py::test_consent_store_failure_returns_500_without_confirmation`
- R3, R13 → `services/orchestrator/tests/test_multicanal_flow.py::test_canonical_telegram_with_opaque_ids_is_accepted_as_text`

## Verificación pendiente

- `./init.sh` finalizó correctamente: 2239 passed, 1 skipped, 1 warning. La
  suite completa verifica los mapeos R13–R21 detallados arriba, además de los
  requisitos R1–R12; se conservan los tests legacy de #35. El warning es la
  deprecación de `httpx` en `starlette.testclient`.
- No se cambió el spec ni las decisiones de R21, y no se eliminó ninguna
  aserción existente. Implementación lista para revisión dirigida; feature
  permanece `in_progress` hasta el reviewer.

## Corrección de la revisión P1 (identidad y consentimiento por canal)

- `POST /messages` ya no rechaza ids canónicos no numéricos: `NormalizedMessage`
  define `external_user_id`, `external_chat_id` y `external_message_id` como
  texto. Solo el payload legacy Telegram se traduce a `MessageRequest`; si esa
  traducción no es posible, el mensaje se procesa con la pareja
  `(channel, external_user_id)` y su clave de deduplicación compuesta (R1, R13,
  R16).
- WhatsApp nunca se convierte a `telegram_user_id`: `_legacy_from_normalized`
  devuelve `None` para canales distintos de Telegram,
  `get_or_create_channel_contact` y `add_channel_privacy_consent` dejan
  `telegram_user_id`/`chat_id` en NULL, y la compuerta consulta
  `has_channel_privacy_consent(channel, external_user_id, version)` (R13-R16,
  R21).
- El consentimiento de un canal no habilita al otro, ni siquiera cuando ambos
  usan el mismo valor numérico como id externo; los contactos y el historial
  también permanecen separados (R14, R15).
- Backfill repetido: los tests de esquema conservan además `messages` y
  `case_links` antes y después de dos ejecuciones, de modo que la migración no
  altera las relaciones de los contactos históricos (R17, R20).

### Trazabilidad de la corrección P1

- R1, R3, R13 → `services/orchestrator/tests/test_multicanal_flow.py::test_canonical_telegram_with_opaque_ids_is_accepted_as_text`
- R14, R15 → `services/orchestrator/tests/test_multichannel_identity.py::test_same_numeric_id_in_telegram_and_whatsapp_stays_separate`, `::test_consent_is_independent_by_channel`
- R16 → `services/orchestrator/tests/test_multicanal_flow.py::test_whatsapp_opaque_external_id_is_kept_as_text`; `services/orchestrator/tests/test_multichannel_identity.py::test_whatsapp_identity_never_uses_the_telegram_column`
- R17, R20 → `services/orchestrator/tests/test_repository_schema.py::test_legacy_contacts_are_backfilled_preserving_ids_and_relations`, `::test_migration_is_idempotent_when_run_more_than_once`
- R21 → `services/orchestrator/tests/test_multichannel_identity.py::test_before_consent_no_contact_or_personal_data_is_persisted`, `::test_acceptance_before_contact_only_writes_privacy_consent`, `::test_canonical_telegram_before_consent_does_not_persist_message_id`

## Corrección de la revisión final (R22/R23)

- `POST /messages` separa la deduplicación persistente por tipo de payload.
  Solo un request canónico (`NormalizedMessage`) usa
  `mark_message_if_new(channel, external_message_id)` y únicamente cuando el
  aviso de privacidad está configurado y existe consentimiento vigente para
  `(channel, external_user_id)`. Sin aviso o sin consentimiento no escribe
  `processed_messages` (R23), tampoco cuando el canónico Telegram es numérico y
  se procesa con el flujo histórico.
- El payload legacy de Telegram usa exclusivamente
  `mark_update_if_new(update_id)`, que guarda solo `update_id` en
  `processed_updates`, sin identidad, texto ni payload (R22).
- `FakeRepository.mark_update_if_new` y
  `PostgresRepository.mark_update_if_new` escriben solo `processed_updates`; el
  repositorio Postgres consulta además `processed_messages` para no repetir un
  mensaje ya marcado por el flujo canónico. `mark_message_if_new` deja de
  alimentar el registro legacy.
- P2: el test idempotente del esquema conserva y compara `messages` y
  `case_links` antes/después de dos ejecuciones del backfill.

### Trazabilidad de la corrección final

- R22 → `services/orchestrator/tests/test_multichannel_identity.py::test_legacy_telegram_before_consent_only_persists_update_id`,
  `::test_request_without_privacy_config_does_not_persist_message_id`;
  `services/orchestrator/tests/test_multicanal_dedup.py::test_postgres_legacy_update_writes_only_processed_updates`
- R23 → `services/orchestrator/tests/test_multichannel_identity.py::test_canonical_telegram_numeric_before_consent_does_not_persist_message_id`,
  `::test_request_without_privacy_config_does_not_persist_message_id`,
  `::test_before_consent_no_contact_or_personal_data_is_persisted`,
  `::test_persistent_dedup_starts_after_channel_consent`
- R17, R18 → `services/orchestrator/tests/test_repository_schema.py::test_legacy_contacts_are_backfilled_preserving_ids_and_relations`,
  `::test_migration_is_idempotent_when_run_more_than_once`

## Verificación pendiente de esta corrección

- `./init.sh` tras la corrección final falló: 1 failed, 2242 passed, 1 skipped,
  1 warning. Falló `test_consent_is_independent_by_channel`: el test aceptó
  consentimiento Telegram para el ID `10`, y luego afirmó contradictoriamente
  que el wrapper legacy `has_privacy_consent(10, ...)` no lo encuentra. Se
  corrigió la cobertura con identidad separada, sin cambiar la lógica.

## Corrección de la cobertura de consentimiento independiente (R15)

- `test_consent_is_independent_by_channel` dejó de reutilizar la identidad `10`
  para la dirección inversa. La primera mitad conserva el caso Telegram `10`
  consentido → WhatsApp `10` sin consentimiento. La segunda mitad usa
  WhatsApp `20` consentido → Telegram `20` sin consentimiento, de modo que la
  aserción `has_privacy_consent(20, ...)` es coherente con lo aceptado.
- No se cambió lógica de producción ni ninguna aserción de comportamiento; solo
  se corrigió la identidad del fixture para probar realmente que el
  consentimiento WhatsApp no habilita la identidad Telegram (R15).
- Trazabilidad: R15 → `services/orchestrator/tests/test_multichannel_identity.py::test_consent_is_independent_by_channel`.
- `./init.sh` posterior a la corrección pasó: 2243 passed, 1 skipped, 1 warning.
  El warning es la deprecación de `httpx` en `starlette.testclient`. La suite
  completa está verde; R22/R23 y P2 tienen trazabilidad arriba. #36 permanece
  `in_progress` hasta revisión dirigida.

## Revisión final

- Reviewer de código: **APPROVED**. Confirmó compuerta preconsentimiento,
  excepción limitada `processed_updates(update_id)` para Telegram legacy,
  ausencia de `processed_messages` antes de consentir, backfill idempotente que
  conserva mensajes/casos, identidad y consentimiento aislados por canal, y
  preservación de los cambios de #35.
