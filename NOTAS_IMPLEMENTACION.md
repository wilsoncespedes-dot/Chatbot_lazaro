# Notas de implementación — rama `feat/produccion-multicanal`

Decisiones tomadas sin consultar (decisión + motivo), por fase. Al final: resumen,
pendientes, variables nuevas y pasos de despliegue.

## Decisión general

- **Sin el arnés del proyecto.** Por instrucción expresa del dueño, estas fases no
  pasan por `feature_list.json`, specs ni el flujo leader/implementer; el código lo
  escribe Claude directamente. Motivo: prioridad de velocidad pedida por el dueño.

## Fase 1 — Migraciones y secretos

- **Runner en `migrations/runner.py` (`python -m migrations.runner`).** Las SQL y el
  runner viven juntos en `migrations/`, con su propia imagen (`migrations/Dockerfile`,
  solo `pg8000`). Motivo: el runner no debe depender de la imagen de ningún servicio.
- **Servicio `migrate` en docker compose** (`restart: "no"`); los servicios con base
  esperan `service_completed_successfully`. Motivo: corre una vez por `docker compose
  up` del despliegue y nunca desde los servicios (el deadlock de 5d1a398 desaparece:
  ya no hay DDL concurrente).
- **Lock de sesión `pg_advisory_lock(7301985)`** (clave distinta del antiguo turno
  7301984) y **una transacción por archivo** junto con su fila en
  `schema_migrations(version, nombre, sha256, aplicada_en)`.
- **Checksum estricto:** si un archivo ya aplicado cambia, el runner aborta. Motivo:
  las migraciones aplicadas son inmutables; se corrige con una nueva.
- **Archivos ejecutados con el protocolo simple de Postgres** (cursor sin parámetros
  en pg8000), así un `.sql` puede tener varias sentencias sin partirlo a mano.
- **`{{EMBEDDINGS_DIM}}`**: la dimensión de `chunks.embedding` dependía de la
  configuración del RAG; el runner la sustituye (por defecto 1536, validada como
  entero). Solo se aceptan variables de una lista blanca.
- **0001 se generó desde las constantes de DDL** (`_SCHEMA`, `_INDEXES`,
  `_MIGRATIONS` del orquestador, handover, canales, buzón, RAG y MCP) con el texto
  exacto, en secciones `-- ── <servicio>`. Las constantes se eliminaron; los tests
  de esquema leen ahora las secciones con `migrations.section(...)`.
- **MCP:** `schema.initialize` ya no crea tablas; solo siembra las ofertas de
  demostración si `MCP_DEMO_SEED=true` (es dato, no esquema).
- **`require_service_token` en `lazaro_contracts.production`** (reusa la lista de
  marcadores `PLACEHOLDERS`: `cambia-esto`, `changeme`, `test`, `xxx`…). Se llama en
  el `lifespan` de los 5 servicios y en los workers del orquestador. Motivo: validar
  en el arranque real y no al importar el módulo (varios `main.py` crean la app al
  importarse, y los tests los importan).
- **`POSTGRES_PASSWORD:?`** en compose: sin valor, compose se niega a arrancar.
- Tests de integración del runner contra Postgres real: `migrations/tests/
  test_runner_integracion.py`, se activan con `TEST_DATABASE_URL` (contenedor
  `pgvector/pgvector:pg16` local desechable). Los tests en memoria que simulaban el
  backfill de #36 se sustituyeron por estos.
- `render.yaml` (despliegue antiguo en Render) no ejecuta el runner; no se tocó
  porque el despliegue vigente es docker compose en EC2.
- Al cerrar la fase 2 aparecieron 7 tests del orquestador que aún esperaban DDL o
  un commit de esquema al conectar (no estaban en los "afectados" de la fase 1);
  se corrigieron en el commit de la fase 2.

## Fase 2 — Entrada unificada sin pérdidas

- **Las URLs públicas no cambian** (`/telegram/webhook`, `/whatsapp/webhook`), pero
  sus rutas propias se eliminaron: ahora llaman a `WebhookService.receive(...,
  own_route=True)`, el mismo caso de uso del webhook genérico. El canal se resuelve
  en el `ChannelRegistry` y el adaptador hace verificación + `NormalizedMessage`.
- **Contrato del adaptador con webhook propio** (`webhook_propio = True`):
  `verificar_webhook(headers, body)` y `eventos(body) -> list[NormalizedMessage] |
  None`. Telegram verifica `X-Telegram-Bot-Api-Secret-Token`, confirma el
  `callback_query` y normaliza; WhatsApp verifica `X-Hub-Signature-256`, registra
  la ventana de 24 h y los estados de entrega y devuelve los mensajes del lote.
  Motivo: el middleware y las rutas tenían esa lógica duplicada fuera del puerto.
- **`/webhooks/telegram` y `/webhooks/whatsapp` siguen en 404** (R7-R9 de #62): un
  canal con webhook propio solo entra por su URL histórica. Si la tabla `canales`
  no responde, esas URLs siguen funcionando con la semilla integrada (R15 de #66).
- **Cola de reintento en el gateway** (`gateway_entrantes_pendientes`, migración
  0002, `adapters/inbound_retry.py`, `inbound.py`). Si `post_message` falla de forma
  transitoria (red, 5xx, 401…) el mensaje se guarda y se responde `ok`; si tampoco
  se puede guardar → **503** y se borra la marca de Redis para que el reenvío del
  canal entre. Un worker (hilo en el `lifespan`) reenvía con espera
  `2 s · 2^intentos` (tope 300 s) y borra la fila al entregarla; a las 48 h se
  descarta con log `inbound_retry_discarded ... reason=expired`. Un 400/413/422 del
  orquestador no se reintenta (el contenido no cambiaría). Todo configurable
  (`INBOUND_RETRY_*`). La fila guarda el texto solo mientras espera.
- **Agrupación de Telegram (#30):** se conserva solo para Telegram (atributo
  `agrupa_mensajes` del adaptador). Un grupo que el orquestador no acepta pasa a la
  cola persistente en vez de descartarse tras `MESSAGE_GROUPING_MAX_ATTEMPTS`.
- **Inbox idempotente en el orquestador:** columna `inbox.external_message_id` +
  índice único `(channel, external_message_id)` (migración 0002). `INSERT ... ON
  CONFLICT DO NOTHING`: una copia repetida responde `duplicate` aunque Redis esté
  caído y aunque el remitente aún no haya consentido (R7 sigue sin escribir en
  `processed_messages`). Las filas antiguas tienen NULL y no chocan.
- **El consentimiento que se procesa en la petición** (botón/frase) reserva antes su
  fila del inbox (`begin_direct_inbound`, estado `processing`); si el proceso
  falla se borra (`abandon_inbound`) para que el reintento del gateway no sea
  "duplicado" (R18 de #35 sigue respondiendo 500).
- **Se eliminó `process_message` y `_legacy_consent_gate`.** El `MessageRequest`
  histórico se convierte con `normalize_legacy_message` (misma identidad y clave
  `telegram`/`str(update_id)`) y todo va por `process_channel_message`. Los comandos
  de personal de Telegram (`/start <token>`, `/consultar`) se atienden al inicio de
  ese flujo (`_handle_staff_command`) con la misma exención de consentimiento. El
  `update_id` numérico de Telegram se conserva para el enrutado interno. Las filas
  `legacy` que queden en el inbox al desplegar se convierten al procesarlas.
- **Cambio visible:** antes de consentir ya no se guarda `processed_updates(update_id)`
  para Telegram; la barrera es el id en la fila del inbox (sin carga tras procesarla).
- **Mensajes no-texto de Telegram** (fotos, audios, stickers, texto vacío) se envían
  al orquestador como `kind="unsupported"`, igual que WhatsApp, y el orquestador
  responde el texto configurable del panel. Se eliminó `NON_TEXT_REPLY` (quedaba
  sin uso); si sigue en el `.env` del servidor se ignora.
- **Adaptadores "viejos" que se conservan:** `adapters/telegram.py`,
  `adapters/whatsapp.py`, `adapters/whatsapp_cloud.py` y `whatsapp_window.py` son
  los clientes HTTP y el almacén de ventana que usan los adaptadores del registro
  (`adapters/channels/*`); la condición "cuando nada los use" no se cumple. Se
  eliminó lo que sí quedó sin uso (`build_message_request`, el modelo
  `TelegramUpdate`, la comprobación de secreto en el middleware).
- **Limitación conocida:** durante una caída del orquestador, un mensaje nuevo puede
  entregarse antes que uno anterior que espera en la cola de reintento.
- `migrations/testing.py`: helper `migrated_database()` para tests de integración
  con una base desechable migrada (requiere `TEST_DATABASE_URL`).

## Fase 3 — Memoria por contacto sin login

- **`MEMORY_ENABLED` por defecto `true`** y **`MEMORY_CONTEXT_MESSAGES` por defecto
  20** (era 6; el máximo ya era 20). En los tests, `conftest.make_env` fija
  `memory_enabled=False` (igual que con `identity_login_required`): las suites
  históricas prueban el flujo sin memoria y los tests de memoria la activan.
- **Migración 0003**: `contact_facts (contact_id, clave, valor, fuente_mensaje_id,
  actualizado)`, PK `(contact_id, clave)` y `CHECK` con las 5 claves (`nombre`,
  `empresa`, `producto_interes`, `pedido_caso`, `preferencia_contacto`); y
  `contact_memory (contact_id, resumen, mensajes_pendientes, actualizado)`. Ambas con
  `REFERENCES contacts(id) ON DELETE CASCADE`: rechazar el consentimiento (R29) y la
  retención por inactividad borran la memoria del contacto con él.
  `fuente_mensaje_id` es solo trazabilidad, sin FK, porque la retención borra
  mensajes por antigüedad y el hecho sigue siendo válido.
- **Dos niveles.** Contacto (canal + id externo): hechos + resumen + últimos 20
  mensajes, siempre que llegue al LLM. Cliente con login: `client_memory` y el
  historial de la sesión (#40, sin cambios). Con sesión, el prompt lleva ambos.
- **Extracción** (`_update_contact_memory`, tras responder): el LLM recibe los
  hechos actuales, el resumen y los últimos `MEMORY_FACTS_INPUT_MESSAGES` mensajes
  y devuelve `{"hechos": {...}, "resumen": "..."}`. Corre cada
  `MEMORY_FACTS_EVERY_MESSAGES` (5) mensajes o antes si el texto trae una frase de
  `MEMORY_FACT_TRIGGER_PHRASES` ("me llamo", "trabajo en", "me interesa"…). Un
  fallo nunca rompe la respuesta (evento `memory_failed`). Motivo: no gastar una
  llamada al LLM por mensaje.
- **Filtro sensible reutilizado** (`is_sensitive`/`clean_summary` de `memory.py`):
  los mensajes con datos sensibles no entran al extractor, y cada valor y frase del
  resumen se filtra otra vez antes de guardarse. **Limitación**: un número de
  pedido de 6+ dígitos no se guarda (umbral `MEMORY_SENSITIVE_MIN_DIGITS`), y un
  mensaje que mezcla nombre y número largo no aporta el nombre.
- **"¿Qué plan te dije?"** no puede contestarlo el RAG (exige citas de los
  manuales). Si el mensaje contiene una frase de `MEMORY_RECALL_PHRASES` y hay
  memoria, se responde con un prompt propio que solo ve la memoria del contacto
  (`{"answer": ...}`, sin cifras que no estén en esa memoria). Si el modelo falla
  o inventa, se responde con los hechos guardados ("Ana, esto es lo que tengo
  anotado: te llamas Ana; te interesa plan Pro."). Sin memoria, el mensaje sigue
  el flujo normal. Evento `memory_answer` con `llm` o `fallback`.
- **En el prompt RAG** los hechos van en `<datos_contacto>` y el resumen en
  `<resumen_contacto>`, marcados como datos no citables (`CONTACT_CONTEXT_NOTE`)
  para que el modelo pueda llamar al contacto por su nombre. Sin memoria el prompt
  es el mismo byte a byte (R26).
- **Login**: los hechos del contacto pasan a `client_memory` como "Nombre: Ana",
  "Producto de interés: plan Pro"… (reemplazan un ítem con la misma etiqueta) y la
  memoria del contacto se vacía. Durante una sesión no se extraen hechos al nivel
  del contacto, y el historial anónimo empieza después de la última sesión cerrada.
  Motivo: R49 — otro cliente que inicie sesión en el mismo chat no debe heredar
  datos del anterior.
- **Con `IDENTITY_LOGIN_REQUIRED=true`** (valor del `.env.example`) un contacto sin
  sesión recibe el enlace de acceso y no llega al LLM; la memoria por contacto
  sigue acumulando lo que diga antes del login y se fusiona al iniciar sesión. Con
  `false` el contacto conversa sin login y usa su memoria. No se cambió ese valor
  (fuera del alcance de la fase).
- **Supresión por cliente**: borra también la memoria de los contactos de sus
  sesiones; `removed_counts` gana la clave `contact_facts`.
