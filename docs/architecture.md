# Arquitectura — Qué significa "hacer un buen trabajo"

> Este documento define el estándar de calidad. El `reviewer` evalúa el
> código contra este archivo. Si no está aquí (o en `docs/conventions.md`),
> no es un requisito. El contexto de negocio está en `docs/proyecto.md`.

## 1. Mapa del monorepo

```
contracts/                 # Contratos entre servicios (feature 1)
├── CONTRATOS.md           # Documento legible: rutas, campos, errores
├── lazaro_contracts/      # Modelos Pydantic compartidos (request/response)
└── tests/
services/
├── telegram_gateway/      # Gateway de canales: Telegram, WhatsApp (Meta Cloud API) y, desde
│                          # #61-#63, cualquier canal registrado (puerto, registry, webhook genérico)
├── orchestrator/          # Cerebro: contacto, conversación, decide qué hacer;
│                          # incluye el módulo de identidad de clientes (#38)
├── rag/                   # Manuales: ingesta, fragmentos, búsqueda pgvector
├── mcp_lectura/           # Servidor MCP de solo lectura (#74): herramientas, auditoría
└── handover/              # Traspaso a asesor: casos, avisos, tiempo de espera
eval/                      # Evaluación con preguntas de ejemplo y casos de ataque
scripts/                   # Utilidades y workers (cargar_manual, configurar_webhook, vencer_casos, purgar_datos…)
docker-compose.yml         # Postgres (pgvector), Redis y los servicios
```

Cada servicio tiene la misma forma:

```
services/<servicio>/
├── <servicio>/            # Paquete Python (mismo nombre que la carpeta)
│   ├── main.py            # App FastAPI: rutas HTTP, sin lógica de negocio
│   ├── config.py          # Settings leídas de variables de entorno
│   ├── domain.py          # Lógica pura (sin red, sin base de datos)
│   └── adapters/          # Clientes externos: DB, Redis, Telegram, LLM, otros servicios
├── tests/
├── requirements.txt       # Dependencias de ejecución del servicio
└── Dockerfile
```

**No se añaden servicios, carpetas de primer nivel ni capas nuevas** sin que
una feature de `feature_list.json` lo pida y su `design.md` lo justifique.

### Multicanal genérico (#60–#67, en curso desde 2026-11-21)

Diseño aprobado por el dueño; cada pieza se vuelve regla vigente cuando su
feature queda `done`. Detalle de producto en `docs/especificacion.md`,
«Ampliación multicanal genérica y multiagente».

- **Hexagonal en el gateway de canales.** Dentro de
  `services/telegram_gateway/telegram_gateway/` se añaden `ports/` (puerto
  `Canal`: `recibir_mensaje`, `enviar_mensaje`, `identificar_usuario`,
  `capacidades`), `registry.py` (`ChannelRegistry`: `tipo_adaptador` →
  adaptador, sin `if/else` por canal) y `adapters/channels/` (un módulo por
  canal: telegram, whatsapp_cloud, generico_webhook, simulado). El servicio
  conserva su nombre para no romper el despliegue ni el webhook de Telegram.
- **Tabla `canales`** propiedad del gateway; el orquestador obtiene los
  metadatos públicos (nombre, ícono, color, activo) por HTTP con
  `X-Service-Token` y nunca recibe secretos.
- **El núcleo (orquestador) no conoce canales concretos:** decide con las
  capacidades que informa el canal (ventana, plantillas, botones, imágenes) y
  con ajustes por canal en `canales.config`; guarda `canal_id` en contactos y
  mensajes.
- **Cola en Postgres (#64):** `POST /messages` guarda y responde 202; los
  workers `procesar_entrantes` y `enviar_salientes` (misma imagen del
  orquestador, como `timeouts_worker`) usan `FOR UPDATE SKIP LOCKED`. Toda
  salida pasa por la tabla `outbox`, escrita en la misma transacción que el
  mensaje, con reintentos con backoff.
- **Etiqueta de origen (#67):** un único componente de panel (ícono + nombre +
  color de `canales`) que reutilizan bandeja, encabezado del chat, cada
  mensaje, ficha del cliente y dashboard.
- **Gmail (#90):** `gmail_api` vive en el `telegram_gateway` como adaptador
  `Canal`, con Gmail API REST/OAuth, credenciales en el almacén cifrado de
  `canales` y cursor incremental PostgreSQL. Un scheduler llama las rutas
  internas protegidas para recibir mensajes de `INBOX`; la salida conserva el
  hilo y usa MIME de texto plano. No se descargan ni envían adjuntos.

### Servidor MCP de solo lectura (#74)

`services/mcp_lectura/` es un servicio interno (SDK oficial `mcp`, licencia MIT)
que expone exactamente `buscar_manuales` y `ofertas_demo`, ambas con
`readOnlyHint=true`. `buscar_manuales` solo llama a `POST /search` del RAG y
`ofertas_demo` solo hace `SELECT` parametrizados en una transacción `READ ONLY`.
No publica puertos en compose, exige `X-Service-Token` en todas las rutas salvo
`GET /health` y audita cada llamada en `mcp_auditoria` (herramienta, `sha256`
de argumentos, filas, estado y fecha; nunca valores ni contenido). El
orquestador se conecta como cliente MCP por streamable HTTP solo en estado
`active` y con `MCP_ENABLED=true`; el `cliente_id` sale de la sesión y viaja en
`X-Cliente-Id`, nunca como argumento del modelo. Las ofertas de demostración se
marcan `es_demo=true` y `DEMOSTRACIÓN`. Detalle en `docs/mcp.md`.

### Panel de asesores multicanal (#41)

La bandeja, la vista de conversación, las plantillas WhatsApp, la presencia y la
cola de supresión del panel de asesores viven en el orchestrator
(`advisor_routes.py`, `advisor_panel.py`, funciones puras en `panel.py`), con
HTML renderizado en el servidor y JavaScript propio de mismo origen (#53), sin
CDN. Handover expone la transferencia de un caso entre asesores
y la reasignación decidida por un supervisor. Roles del panel: `admin`,
`supervisor`, `asesor`, `responsable_datos` y `cliente`; el rol se lee del
perfil de la sesión en el servidor. Las notas internas y las etiquetas de caso
viven en tablas propias del orchestrator (`case_notes`, `case_tags` y
`case_tag_assignments`), nunca en `messages` ni en las fuentes del prompt, la
memoria o los resúmenes.

La bandeja y la vista de conversación se actualizan en vivo (#53) con
JavaScript propio servido desde el mismo origen (`GET /asesor/static/panel_live.js`),
sin CDN ni scripts inline y bajo una CSP estricta. Un websocket de solo lectura
(`GET /asesor/ws`) envía avisos `{type, id, case_id}`; el navegador vuelve a
pedir el fragmento HTTP autorizado (`/asesor/live/inbox`, `/asesor/live/cases/{id}`)
y reemplaza la región en vivo sin duplicar filas. El transporte entre
instancias es la tabla Postgres `panel_events`, sondeada por cada conexión;
los eventos se publican en la misma transacción que el mensaje o el enlace del
caso y se purgan por retención y por supresión. Sin JavaScript se conserva la
recarga periódica con `<noscript>`.

### Administración y avisos (#42)

La administración de clientes, textos versionados, plantillas, ajustes
operativos y métricas vive en el orchestrator (`admin_routes.py`,
`administration.py`), sin JavaScript ni CDN. Un worker externo
(`scripts/avisar_vencimientos.py`) ejecuta la pasada de avisos de vencimiento
contra `POST /credentials/expiry-notices`.

**Importación de clientes desde CSV (#77).** El admin sube un archivo UTF-8
(con o sin BOM) con separador coma o punto y coma y encabezados `id`
(opcional), `usuario` (obligatorio), `correo` y `telefono` (opcionales); no se
admiten otras columnas ni contraseñas. Después de una vista previa en memoria
(errores por fila y campo, duplicados de base y de archivo), la confirmación
crea o actualiza solo correo y teléfono a través de `FuenteDeClientes`. Los
clientes importados nacen sin credencial activa; el archivo nunca se guarda y
las filas con errores o conflictos se informan en un resumen sin correo ni
teléfono. Límites y TTL son configurables (`CLIENT_IMPORT_MAX_BYTES`,
`CLIENT_IMPORT_MAX_ROWS`, `CLIENT_IMPORT_PREVIEW_TTL_SECONDS`; por defecto
1 MiB, 1000 filas y 900 s). Supuestos S1-S7 de `specs/importacion_clientes/`
(«nombre» es `usuario`, política única con «Saltar» por defecto, actualizar
solo contacto, staging en un proceso, sin flujo nuevo de habilitación de
contraseña, retención con `PRIVACY_RETENTION_DAYS`).

### Fuente de clientes y adaptador LazaroClientSource (solo a futuro)

El orquestador define el puerto `FuenteDeClientes` (`buscar_por_id`, `listar`,
`crear`, `actualizar` y `obtener_credencial`) y su implementación local
`FuenteClientesLocal` sobre el repositorio actual. La creación y administración
de clientes y las rutas internas `/clients` pasan por ese puerto.

**Posibilidad a futuro, no implementada.** No hay acceso a la API de Lázaro y no
se simula; lo siguiente describe solo cómo podría hacerse y no es un
compromiso:

- `LazaroClientSource` implementaría `FuenteDeClientes`: `buscar_por_id`
  consultaría a la API de Lázaro por el ID de cliente; `listar` paginaría
  clientes; una sincronización copiaría altas y bajas hacia la base local.
- **Duplicados:** la clave de cruce sería el ID de cliente de Lázaro. Si el
  cliente ya existe localmente se actualizaría; nunca se crearía otro. Un
  conflicto de usuario se reportaría para resolverlo a mano.
- **Borrados:** un cliente que desaparece en Lázaro se marcaría como revocado,
  sin borrar el historial; uno borrado solo en local se reportaría y no se
  eliminaría en Lázaro.

### Hoja de estilos compartida (#56)

Los paneles de administración y de asesores comparten la hoja
`GET /admin/static/admin.css` (`admin.ADMIN_CSS`): variables de diseño,
cabecera y navegación `site-header`/`site-nav`, tarjetas, insignias de estado y
tablas dentro de `.table-wrap`. No hay CDN, fuentes remotas, `style=` ni
archivos estáticos nuevos; la CSP se mantiene sin cambios.

### Identidad de clientes (#38)

La identidad web vive **dentro del orchestrator** (`identity.py`,
`identity_routes.py`, `identity_page.py`), no en un servicio nuevo. `GET/POST
/acceso` es la única ruta pública para personas: no exige `X-Service-Token`
(igual que `/health`), sirve HTML propio sin CDN y usa un enlace firmado de un
solo uso. Las rutas internas `/clients…` sí exigen `X-Service-Token` y son el
punto de entrada para la administración de credenciales (#42). El token del
enlace nunca se registra en logs: un filtro sobre `uvicorn.access` redacta el
valor de `t=`.

## 2. Tecnología fijada

| Pieza              | Elección                                             |
|--------------------|------------------------------------------------------|
| Lenguaje           | Python 3.12 (mínimo 3.11)                            |
| Web                | FastAPI + Uvicorn                                    |
| Modelos de datos   | Pydantic v2                                          |
| Cliente HTTP       | httpx                                                |
| Base de datos      | PostgreSQL 16 con extensión pgvector                 |
| Caché / colas      | Redis                                                |
| Tests              | pytest (+ `fastapi.testclient`)                      |
| Contenedores       | Docker + Docker Compose                              |
| CI / despliegue    | GitHub Actions → Render (pruebas)                    |

Cualquier dependencia nueva (librería de PDF, de Word, driver de Postgres,
SDK del proveedor de IA…) se declara en el `design.md` de la feature que la
necesita, con versión acotada y licencia compatible (MIT, BSD, Apache 2.0,
PSF). El agente solo instala lo que está en `requirements.txt` y en el
`design.md` aprobado, siempre dentro del `.venv` del proyecto. Licencias GPL/AGPL: prohibidas.

## 3. Principios

1. **Microservicios que se hablan solo por HTTP + JSON.** Un servicio nunca
   importa código de otro servicio ni lee su base de datos. Lo único
   compartido es `contracts/lazaro_contracts` (modelos Pydantic).
2. **Contratos primero.** Toda ruta entre servicios está en
   `contracts/CONTRATOS.md` y tiene su modelo en `lazaro_contracts`. Cambiar
   un contrato es una feature propia, no un efecto colateral.
3. **Capas dentro de cada servicio.** `main.py` (HTTP) → `domain.py`
   (decisiones) → `adapters/` (mundo exterior). `domain.py` no hace IO.
4. **Todo lo externo detrás de una interfaz inyectable.** Telegram, el
   proveedor de IA (LLM y embeddings), Postgres, Redis y los demás servicios
   se usan a través de un adaptador con una versión falsa (`Fake…`) para
   tests. Así los tests no necesitan red, claves ni Docker.
5. **Configuración.** Secretos, credenciales, URLs y configuración de
   infraestructura se leen de variables de entorno (`config.py` con Pydantic
   Settings o `os.environ`) y se declaran en `.env.example`. Excepción: textos
   legales y fijos, tiempos de producto, horarios y plazos de retención se
   administran desde el panel.
6. **Idempotencia multicanal.** El núcleo descarta duplicados usando la pareja
   `(canal, mensaje_externo_id)`; los identificadores solo son únicos dentro
   de un canal. Antes del login, contactos y consentimiento se aíslan por
   `(canal, external_user_id)`; nunca se convierte un ID de WhatsApp en
   `telegram_user_id`. La vinculación entre identidades de canales requiere
   login verificado. `canal` es cualquier canal registrado en `canales`
   (abierto desde #60), no una lista fija.
7. **Errores explícitos.** Respuestas de error siempre con forma
   `{"error": "<codigo>", "message": "<texto>"}` y el código HTTP adecuado.
   Nada de stack traces hacia el usuario ni hacia otros servicios.
8. **Autenticación entre servicios.** Toda ruta interna exige el encabezado
   `X-Service-Token` igual a `SERVICE_TOKEN`; sin él, `401`. Excepción:
   `GET /health`, la página pública `/acceso` (#38), el webhook de Telegram
   (que valida `TELEGRAM_WEBHOOK_SECRET`) y el webhook de WhatsApp
   `GET/POST /whatsapp/webhook` (que valida `hub.verify_token` y la firma
   `X-Hub-Signature-256` de Meta Cloud API). Desde #62 también el webhook
   genérico `POST /webhooks/{canal_id}`, que valida la firma HMAC-SHA256 del
   canal y la ventana anti-repetición.
9. **Registro de eventos.** Las decisiones importantes (respuesta con RAG,
   rechazo, traspaso, aviso a asesor) se guardan como eventos con fecha,
   contacto y motivo.

## 4. Seguridad (no negociable)

- **El bot no inventa.** Solo responde con fragmentos que superen el umbral
  de similitud y con citas validadas; si no, rechazo fijo y oferta de asesor.
- **El texto es dato, nunca instrucción.** Mensajes de usuarios y fragmentos
  de manuales se pasan al modelo delimitados como datos. El modelo **no
  tiene herramientas** que escriban directamente en la base de datos,
  ejecuten código o llamen a URLs arbitrarias. Las herramientas disponibles
  dependen del estado y se autorizan en el código: la matriz vive en
  `services/orchestrator/orchestrator/harness.py` (`TOOL_MATRIX`).
- Las consultas de datos usan exclusivamente vistas permitidas con RLS. La
  identidad cliente se obtiene de la sesión autenticada; las consultas no
  pueden seleccionar tablas directamente ni eludir políticas de filas.
- **Nadie ejecuta código a través del bot.** No se usa `eval`, `exec`,
  `subprocess`, `pickle` de datos externos ni SQL construido con texto del
  usuario (siempre parámetros).
- **El acceso a datos de cliente se limita a sus propias vistas con RLS.** La
  herramienta obtiene `cliente_id` de la sesión autenticada; el cliente nunca
  elige identidad, tabla ni política de filtrado. Las consultas SQL de personal
  siguen las restricciones y permisos definidos en su feature.
- **Secretos.** Solo en `.env` (ignorado por git). `.env.example` con nombres
  y valores vacíos o de ejemplo. Los agentes no leen `.env`.
- **Datos personales mínimos** (Ley 1581): guardar solo lo necesario para
  atender en ambos canales (ids externos, mensajes, casos y memoria autorizada).
  La memoria permanente pertenece al cliente y se elimina al tramitar una
  supresión (`orchestrator/memory.py` filtra datos sensibles y
  `domain.execute_suppression` es la única vía de borrado). Su retención requiere
  validación legal. La purga automática no elimina casos activos ni memoria
  permanente.

## 5. Licencias y código de terceros

- Se puede copiar código solo de repos con licencia **MIT o Apache 2.0**
  (principal: rag-support-bot, MIT). Cada copia se anota en
  `THIRD_PARTY_NOTICES.md` y el archivo conserva el aviso original arriba.
- Repos **sin archivo de licencia** (crm_bot, dbchatbot, NURA…): solo
  inspiración, cero copia.
- **AGPL** (Helpdock): ni copia ni adaptación cercana.

## 6. Qué NO hacer

- No usar `print()` para registrar: usar `logging`.
- No mezclar IO con decisiones en `domain.py`.
- No llamar a servicios reales (Telegram, proveedor de IA) desde los tests.
- No añadir funcionalidad nueva (servicios, paneles, herramientas del modelo)
  hasta que su feature exista en `feature_list.json`.
- No resolver una duda abierta de `docs/proyecto.md` §12 inventando: se
  convierte en un supuesto configurable documentado en `design.md`.
