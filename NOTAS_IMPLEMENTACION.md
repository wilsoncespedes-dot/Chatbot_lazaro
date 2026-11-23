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

## Fase 4 — Consultas de solo lectura listas para producción

- **Migración `0004_consultas_lectura.sql`** con tres roles, todos
  `NOSUPERUSER NOBYPASSRLS NOINHERIT`:
  - `bot_vistas` (NOLOGIN): dueño de las vistas, con SELECT sobre las tablas
    base que estas leen.
  - `bot_lectura` (LOGIN si `BOT_LECTURA_PASSWORD` está definida): usa
    `CLIENT_DATA` y solo puede leer `mis_datos.*`.
  - `bot_consultas` (LOGIN si `BOT_CONSULTAS_PASSWORD` está definida): usa
    `DB_QUERY` (asesores/admin) y solo puede leer `consultas.*`.

  Son tres y no uno porque la configuración ya exigía DSN distintos, y las vistas
  del personal no se filtran por cliente mientras las del cliente sí. Los dos
  roles de login quedan con `default_transaction_read_only = on` y
  `statement_timeout = '5s'` a nivel de rol. Por eso la base corta una consulta
  lenta y rechaza escribir aunque el código fallara.
- **RLS por `lazaro.cliente_id`**, con `ENABLE` + `FORCE ROW LEVEL SECURITY`,
  en las tablas con datos de un cliente:
  - `profiles` (id)
  - `client_credentials` (profile_id)
  - `client_sessions` (profile_id)
  - `case_links` (profile_id)
  - `identidades_cliente` (cliente_id)

  Cada tabla tiene dos políticas:
  - `bot_solo_su_cliente` (SELECT `TO bot_vistas`): solo la fila cuyo id coincide
    con `current_setting('lazaro.cliente_id', true)`. Sin ese valor no ve ninguna
    fila.
  - `app_acceso_total` (`TO CURRENT_USER`, el usuario de la aplicación que corre
    las migraciones): sin cambios para la app. Hace falta porque `FORCE` también
    aplicaría la RLS al dueño de la tabla.

  Probado: las vistas las posee `bot_vistas`, así que la RLS se evalúa con ese
  rol aunque consulte `bot_lectura`. Un `SELECT` sin `WHERE` solo devuelve el
  cliente fijado por `PostgresClientDataQuery`.
- **Vistas creadas** (sin columnas de id interno de cliente):
  - `mis_datos.v_mi_cuenta` (id_cliente, usuario, correo, telefono, acceso_desde,
    acceso_hasta)
  - `mis_datos.v_mis_casos` (caso, estado, motivo, creado, cerrado)
  - `mis_datos.v_mis_sesiones` (canal, inicio, fin)
  - `consultas.v_casos` (caso, estado, motivo, canal, creado, asignado, cerrado)
  - `consultas.v_mensajes_diarios` (dia, canal, rol, mensajes): conteos, sin
    texto de mensajes.
  - `consultas.v_ofertas` (id, destino, titulo, precio_cop, valido_desde,
    valido_hasta, etiqueta), desde `demo_ofertas`.

  `demo_ofertas` solo se expone a `consultas`: una vista pública en `mis_datos`
  haría fallar la sonda de aislamiento del cliente al arrancar.
- **Las vistas del personal** leen tablas sin RLS (`handover_cases`, `contacts`,
  `messages`, `demo_ofertas`). Lo que limita al rol es el allowlist y los
  permisos, no un filtro por cliente.
- **Arranque**: si `DB_QUERY_DATABASE_URL` o `CLIENT_DATA_DATABASE_URL` usan el
  mismo usuario que `DATABASE_URL`, la configuración falla y el servicio no
  arranca. También falla si las dos usan el mismo rol entre sí. Además, al
  primer uso el adaptador verifica `rolsuper`/`rolbypassrls` del rol conectado;
  si alguno es cierto, queda "no disponible".
- **LIMIT obligatorio**: `validate_sql(..., max_rows=N)` añade `LIMIT N+1` si el
  SQL no trae uno al nivel superior; el +1 sirve para detectar `truncated`.
  - Un `LIMIT` del modelo solo se acepta si es el último y es un entero literal
    (`LIMIT 5`); `LIMIT ALL`, `LIMIT (…)` u `OFFSET` tras `LIMIT` se rechazan
    (`invalid_limit`).
  - Se mantiene el envoltorio `SELECT * FROM (…) LIMIT` del adaptador.
  - La auditoría guarda el hash del SQL realmente ejecutado, con el LIMIT.
- **statement_timeout** confirmado en tres capas:
  - `SET LOCAL` en cada consulta (`DB_QUERY_TIMEOUT_MS`/`CLIENT_DATA_TIMEOUT_MS`);
  - el valor por rol (5 s);
  - y ahora también en `PostgresDemoOffers.buscar` del MCP (5000 ms), que antes
    no tenía.
- **Resultado estructurado**: `query_client_data` y `query_staff_data` devuelven
  `QueryOutcome(status, result, validated)`. `QueryResult.as_dict()` da
  `{"columns", "rows", "truncated"}` serializable a JSON (Decimal→float,
  fechas→ISO). Las respuestas del bot no cambiaron.
- **Activación**:
  - `DB_QUERY_ENABLED`, `CLIENT_DATA_ENABLED` y `MCP_ENABLED` siguen en `false`
    por defecto.
  - El `.env.example` ya trae los allowlists de las vistas nuevas y explica qué
    DSN usar (`bot_consultas`/`bot_lectura`).
  - Las contraseñas `BOT_*_PASSWORD` las aplica el runner de migraciones (rol con
    LOGIN).
- **Copias de seguridad**: con `FORCE RLS`, un `pg_dump` hecho por un rol que no
  sea superusuario ni dueño con la política `app_acceso_total` vería filas
  filtradas. Hay que hacer el backup con el usuario principal o el superusuario.
- No se revoca `CONNECT` a `PUBLIC`: puede romper otros clientes del servidor y
  está fuera del alcance.

## Fase 5 — Herramienta `graficar`

- **`graficar` entra en `TOOL_MATRIX` solo en el estado `active`.** Grafica los
  datos propios del cliente con sesión: reutiliza `query_client_data` de la fase 4,
  con sus vistas `mis_datos`, la RLS y el LIMIT. No hay un camino nuevo a la base.
  - El LLM genera el SQL con una instrucción fija extra (`CHART_SQL_HINT`: dos
    columnas, etiqueta/fecha + valor agregado). Va en el *system prompt*, nunca
    mezclada con el texto del usuario.
  - Motivo de limitarlo a los datos del cliente: es la única fuente que ya tiene
    aislamiento por cliente en el chat. Graficar las vistas `consultas` del
    personal queda para un comando de asesor si se pide.
- **Se elige por palabra clave** (`CHART_TRIGGER_PHRASES`: grafica, grafico,
  graficar, graficame, diagrama) **y también por router.** El router
  (`HARNESS_ROUTER_ENABLED`) viene apagado por defecto, y sin palabra clave la
  herramienta sería inalcanzable. La autorización por estado sigue en
  `execute_tool` y la llamada queda auditada en `tool_calls` con origen `keyword`
  o `router`. El router solo acepta `args` vacío o `{"tipo": barras|lineas|torta}`.
- **Tipo de gráfico:**
  - Fechas en la etiqueta → líneas, ordenadas por fecha.
  - Lo demás → barras horizontales. Con más de 12 categorías, las de menor valor
    se agrupan en «Otros».
  - Torta solo si se pide ("torta", "pastel", "circular" o `tipo=torta`), hay 6
    categorías o menos y todos los valores son positivos. Si no, barras.
  - "Líneas"/"evolución" fuerzan líneas cuando hay al menos 2 puntos.
- **Nunca se envía un gráfico vacío:**
  - Sin filas o con todo en cero → `CHART_NO_DATA_REPLY` en texto.
  - Con datos pero sin forma de gráfico (una sola cifra, sin columna numérica) →
    las filas en texto, como `consultar_mis_datos`.
- **PNG en Python puro** (`orchestrator/charts.py`): lienzo RGB, fuente de mapa de
  bits 5x7 a escala 2 y PNG con `zlib`/`struct`. Copia el diseño de
  `render_bar_chart` del dashboard (etiqueta a la izquierda, barra, valor a la
  derecha, mismos colores de contraste).
  - La fuente dibuja mayúsculas sin tildes: ñ→N, á→A. Es legible y evita
    dependencias.
  - Ancho fijo de 720 px; un PNG pesa unos pocos KB.
- **Frase con la cifra clave**, determinista y sin LLM:
  - Barras/torta: "Casos por estado: «abierto» es el mayor con 5 de 8 en total
    (62 %)."
  - Líneas: último valor frente al primero y máximo.
- **Entrega por el outbox** (`_send_blocks`): el historial guarda la frase.
  - Canal con `supports_images` → `ImageBlock` (URL firmada) + `TextBlock` con la
    frase.
  - Canal sin imágenes → `TextBlock` + `LinkBlock` "Ver gráfico" con la misma URL
    firmada.
  - Sin tocar el gateway: los adaptadores ya declaran `supports_images` en
    `ChannelCapabilities` y la política del canal lo lee del directorio.
- **Enlace temporal firmado:**
  - URL: `IDENTITY_PUBLIC_BASE_URL/media/graficos/<id>.png?exp=<unix>&sig=<hmac>`.
  - Firma HMAC-SHA256 de `grafico:<id>:<exp>` con `CHART_LINK_SIGNING_KEY`.
  - Vence a los `CHART_LINK_TTL_SECONDS` (3600 por defecto).
  - Firma mala, vencida, id inexistente o gráficos apagados → 404 sin distinguir
    el caso.
  - Se sirve con `nosniff`, `no-referrer` y caché privada de 5 minutos.
  - La clave es nueva y debe ser distinta de `IDENTITY_LINK_SIGNING_KEY`: si una
    se filtra, no compromete la otra.
- **Almacenamiento**: tabla `chart_images` en la migración
  `0005_graficos.sql`, con FK a `contacts` ON DELETE CASCADE.
  - Cada gráfico nuevo borra los vencidos: no hace falta un cron.
  - El borrado de contenido de un contacto (rechazo de aviso o supresión) también
    borra sus gráficos.
- **Configuración**: `CHARTS_ENABLED=false` por defecto. Con `true`, la
  configuración exige:
  - `CLIENT_DATA_ENABLED=true`;
  - `IDENTITY_PUBLIC_BASE_URL` https;
  - una clave de 32 caracteres o más.

  Si falta algo, el servicio no arranca, para no descubrirlo con un cliente.
- **Despliegue**: el túnel ya publica `/media/respuestas/*` del orquestador
  (respuestas rápidas con imagen). `/media/graficos/*` necesita la misma regla.
  PENDIENTE: confirmar en la configuración del túnel de Cloudflare del servidor
  (fuera del repo) que la regla cubre `/media/*` y no solo `/media/respuestas/*`.
- Tests: `test_graficos.py` (31: dibujo, resumen, firma, matriz, router,
  configuración, flujo con imagen/enlace, sin datos, ruta, palabra clave y
  Postgres real). Se actualizaron:
  - el conteo de herramientas (7→8) en `test_harness_matrix` y
    `test_answer_quality`;
  - la lista de rutas expuestas en `test_config`;
  - el SQL auditado en `test_db_query`.

## Fase 6 — Canal TikTok Business Messaging

Origen: OpenCode escribió la primera versión mientras esta sesión estaba en pausa
por el límite de uso. Aquí se revisó contra el encargo y se completó lo que faltaba:
el secreto propio del webhook, los PENDIENTE, los tests de aceptación y el simulador.

- **Ruta y firma**
  - La ruta es `POST /webhooks/tiktok`. Es pública, sin `X-Service-Token`, y se
    registra antes de la genérica `/webhooks/{canal_id}`.
  - La firma va en `TikTok-Signature: t=<unix>,s=<hex>`: es el HMAC-SHA256 de
    `<t>.<cuerpo crudo>`, con una ventana anti-repetición de
    `TIKTOK_SIGNATURE_TOLERANCE_SECONDS`.
  - **Decisión:** se verifica con `TIKTOK_WEBHOOK_SECRET`, que es la variable propia
    que pide el encargo, y no con `TIKTOK_CLIENT_SECRET`. Si está vacío, todo
    webhook recibe 401 aunque `TIKTOK_ENABLED=true`. **Motivo:** falla cerrado y
    permite rotar el secreto del webhook sin tocar el OAuth.
  - PENDIENTE: confirmar con la doc oficial la cabecera, el formato y qué secreto
    firma. Según la documentación que consultó OpenCode es el `client_secret` de la
    app; en ese caso basta con poner el mismo valor en ambas variables.
- **Normalización**
  - Solo se procesa `im_receive_msg` de la cuenta `TIKTOK_BUSINESS_ID` y del
    `client_key` propio.
  - Los ecos y los mensajes de la propia cuenta se ignoran.
  - La multimedia y el texto demasiado largo llegan como `unsupported`, sin truncar.
- **OAuth**
  - Los tokens se guardan cifrados con Fernet (`CHANNEL_SECRETS_KEY`) en
    `canales.config_secreta`.
  - Se refrescan antes de enviar si vencen dentro de
    `TIKTOK_TOKEN_REFRESH_MARGIN_SECONDS`.
  - Si TikTok rechaza un token que todavía estaba vigente (códigos de
    autenticación), se refresca una sola vez y se reintenta. Un segundo rechazo
    deja el envío en `failed`, sin bucles.
  - Un candado por proceso evita dos refrescos simultáneos, porque TikTok rota el
    refresh token.
  - `TIKTOK_REFRESH_TOKEN` solo se usa en el primer arranque.
- **Salida**
  - `supports_images=False`: los gráficos de la fase 5 llegan como enlace firmado,
    con la forma «Título: URL».
  - El texto se divide en trozos de 6000 caracteres.
  - Hay un tope de 10 mensajes por conversación cada 48 h, llevado en Redis. Al
    superarlo, el gateway responde 422 de ventana y la fila del outbox queda en
    `fuera_de_ventana` (fase 7).
- **Panel**: el canal se siembra como `tiktok` (adaptador `tiktok`, gestionado por
  el entorno) y solo se activa con `TIKTOK_ENABLED=true`.
- **Simulador**: se lanza con
  `python scripts/simular_canal.py --canal tiktok --usuario u --texto "Hola"`.
  Necesita `TIKTOK_WEBHOOK_SECRET`, `TIKTOK_BUSINESS_ID` y `TIKTOK_CLIENT_KEY` en el
  entorno.
- **Tests**
  - `services/telegram_gateway/tests/test_tiktok.py`:
    - una firma válida llega al orquestador;
    - una firma inválida, o la ausencia de secreto, da 401;
    - un token vencido se refresca antes de enviar;
    - un token rechazado se refresca y se reintenta una sola vez;
    - un gráfico se entrega como enlace.
  - `services/orchestrator/tests/test_canales_externos.py`: un mensaje de `tiktok`
    deja la respuesta en el outbox de ese canal.
  - `scripts/tests/test_simular_canal.py`: el modo TikTok.
- PENDIENTE: confirmar con la doc oficial lo siguiente. No se hizo ninguna llamada
  real a TikTok.
  - Las URLs `TIKTOK_TOKEN_URL` y `TIKTOK_SEND_URL`.
  - Los códigos de token vencido (`AUTH_ERROR_CODES`).
  - El límite de 10 mensajes cada 48 h.
  - Que la API de Business Messaging (beta regional, con aprobación previa) esté
    disponible para la cuenta de Lázaro.
- Fuentes que citó OpenCode:
  - [webhooks](https://business-api.tiktok.com/portal/docs/subscribe-to-business-messaging-webhook-events-via-webhooks-api/v1.3)
  - [OAuth](https://business-api.tiktok.com/portal/docs/business-messaging-api-authentication/v1.3)
  - [envío](https://business-api.tiktok.com/portal/docs/send-a-message-to-a-conversation/v1.3)
  - [firma](https://developers.tiktok.com/docs/en/webhooks-verification)
- **Verificación**: se pasaron los tests del gateway, de scripts y de contracts
  sobre el árbol exacto de este commit. El pytest completo de esta fase se ejecutó
  junto con el del cierre, porque OpenCode dejó las fases 6 y 7 entrelazadas en el
  árbol de trabajo.
