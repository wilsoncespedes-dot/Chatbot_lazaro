# Tasks — proveedor_whatsapp_real (feature #43)

Todas las tareas de código son del servicio `telegram_gateway` salvo las
indicadas. Ninguna prueba abre red: el adaptador recibe un `httpx.Client` con
`httpx.MockTransport`; Redis se sustituye por `FakeDedupStore` y
`FakeWhatsAppWindowStore`.

## Configuración

- [x] T1 — Añadir a `telegram_gateway/config.py` las variables `WHATSAPP_*` de
  `design.md` §Configuración (secretos como `SecretStr`), validación de
  formato de versión, idioma, cuerpo interactivo y `WHATSAPP_WINDOW_HOURS`
  (1–24), y el validador que con `WHATSAPP_ENABLED=true` falla nombrando solo
  las variables vacías. Cubre: R3, R5.
- [x] T2 — Añadir el bloque `# WhatsApp Cloud API (#43)` a `.env.example`
  (secretos vacíos, `WHATSAPP_ENABLED=false`, defaults del resto; reutilizar
  la línea existente de `WHATSAPP_WINDOW_HOURS`). Cubre: R7.
- [x] T3 — Pasar las variables `WHATSAPP_*` al servicio `telegram_gateway` en
  `docker-compose.yml` y `render.yaml` (secretos con `sync: false`, sin
  `value`); añadir los tres secretos a `SECRET_KEYS`/`THIRD_PARTY_SECRETS` en
  `scripts/tests/test_render_blueprint.py`. Cubre: R5, R7.

## Lógica pura (`telegram_gateway/whatsapp_cloud.py`)

- [x] T4 — `verify_signature` (HMAC-SHA256 sobre bytes crudos, prefijo
  `sha256=`, `hmac.compare_digest`, hex sin distinguir mayúsculas) y
  `verify_subscription`. Cubre: R8, R9, R12, R13.
- [x] T5 — `split_button_id` y `parse_webhook`: filtrado de cambios
  aplicables, normalización text/interactive/button/unsupported, exclusión de
  `reaction`, descarte de mensajes inválidos sin abortar el lote, orden
  preservado, `inbound_wa_ids` y `statuses`. Cubre: R14, R15, R16, R17, R18,
  R19, R20, R21, R22, R27, R47, R51, R52.
- [x] T6 — `build_send_payloads`: texto, plantilla con/sin `components`,
  botones interactivos con `id:proof`, fusión del `TextBlock` previo (≤1024)
  como cuerpo, `WHATSAPP_INTERACTIVE_BODY_TEXT` como alternativa, límite de
  256 en `reply.id`, y opciones sin ids/lista/enlace vía `render_blocks`.
  Cubre: R32, R34, R35, R36, R37, R38, R39, R54, R55.
- [x] T7 — `translate_error` (131047 → `ChannelWindowClosed`; códigos de
  plantilla → `TemplateNotApproved`; resto, no-JSON y errores de red →
  `ChannelSendFailed`) y `to_delivery_status`. Cubre: R43, R44, R45, R48.

## Adaptadores

- [x] T8 — `adapters/whatsapp_window.py`: protocolo
  `WhatsAppWindowStore`, `RedisWhatsAppWindowStore` (clave
  `gw:whatsapp:last_inbound:<wa_id>`, ISO-8601, `EX` = horas de ventana) y
  `FakeWhatsAppWindowStore` (con `fail`). Cubre: R27, R42.
- [x] T9 — `adapters/whatsapp_cloud.py`: `WhatsAppCloudConfig` (token con
  `repr=False`) y `WhatsAppCloudAdapter` con `capabilities`,
  `capabilities_for`, `normalize_incoming`, `send` (revalida ventana sin HTTP,
  POST secuenciales con `Authorization: Bearer`, parada sin reintento al
  primer fallo, log de estado/código/subcódigo/`fbtrace_id` sin token, wa_id ni
  texto) y `delivery_status`. Cubre: R5, R6, R28, R29, R30, R32, R33, R40,
  R41, R42, R43, R44, R45, R46, R48, R49, R56, R57, R58, R59, R62.

## Dominio y app

- [x] T10 — En `domain.py`: campo `Adapters.whatsapp_window`, excepción
  `WebhookForbidden` (403, `forbidden`) y uso de `capabilities_for` en
  `send_response` cuando exista. Cubre: R9, R31, R50, R60, R61.
- [x] T11 — En `main.py`: `build_default_adapters` crea
  `RedisWhatsAppWindowStore` + `WhatsAppCloudAdapter` (con `httpx.Client` y
  `HTTP_TIMEOUT_SECONDS`) solo si `WHATSAPP_ENABLED`; rutas `GET/POST
  /whatsapp/webhook` (404 si deshabilitado), exención de `X-Service-Token`,
  lectura de cuerpo crudo antes de parsear, 401 por firma, 200 ante JSON
  inválido u objeto ajeno, registro de ventana, dedup `("whatsapp", wamid)`
  con política ante fallo de Redis, reenvío en orden, log de estados y 200
  final; trabajo síncrono en `run_in_threadpool`. Cubre: R1, R2, R4, R8, R9,
  R10, R11, R12, R14, R23, R24, R25, R26, R27, R47, R53.

## Pruebas

- [x] T12 — `tests/test_whatsapp_config.py`: deshabilitado → `whatsapp is
  None` y `/send` 502 `upstream_error` (R1); webhook 404 GET/POST (R2); falta
  cada secreto → error que nombra la variable y no contiene valores (R3);
  habilitado → `WhatsAppCloudAdapter` (R4); `repr` de Settings y adaptador sin
  secretos (R5); `.env.example` declara las claves con secretos vacíos (R7).
  Cubre: R1, R2, R3, R4, R5, R7.
- [x] T13 — `tests/test_whatsapp_webhook.py` (GET): challenge correcto con
  `text/plain` (R8); modo distinto, token distinto, token ausente y sin
  challenge → 403 `forbidden` (R9); sin `X-Service-Token` en GET y POST (R10).
  Cubre: R8, R9, R10.
- [x] T14 — `tests/test_whatsapp_webhook.py` (firma): firma válida → 200 y
  reenvío (R11); sin encabezado, sin prefijo, HMAC incorrecto → 401 y fakes
  de dedup/ventana/orquestador intactos (R12); cuerpo re-serializado con
  bytes distintos → 401 (R13); firma válida con no-JSON, lista u `object`
  ajeno → 200 sin reenvío (R14); `phone_number_id` ajeno y `field` ajeno
  ignorados (R15) mientras otro cambio aplicable del mismo cuerpo se procesa
  (R51). Cubre: R11, R12, R13, R14, R15, R51.
- [x] T15 — `tests/test_whatsapp_webhook.py` (normalización): texto (R16);
  `button_reply` y `list_reply` con y sin prueba (R17); `button.payload`
  (R18); imagen, audio, sticker y tipo desconocido → `unsupported` (R19);
  `reaction` no se reenvía pero registra ventana (R20, R27); mensaje sin
  `from`, sin `id`, texto vacío y texto > 4096 descartados sin abortar el lote
  (R21) y el mensaje válido posterior sí se reenvía (R52); orden de varios
  mensajes (R22). Cubre: R16, R17, R18, R19, R20, R21, R22, R27, R52.
- [x] T16 — `tests/test_whatsapp_webhook.py` (idempotencia): webhook duplicado
  con el mismo wamid → un solo reenvío (R23) y ambos 200 (R53); wamid igual a un
  `update_id` Telegram ya marcado se reenvía (R24); `FakeDedupStore(fail=True)`
  → se reenvía (R25); orquestador que lanza `OrchestratorError` → 200 y log
  (R26). Cubre: R23, R24, R25, R26, R53.
- [x] T17 — `tests/test_whatsapp_cloud.py` (ventana): `capabilities_for` con
  entrante hace 1 h → abierta; a las 24 h exactas y sin entrante → cerrada
  (R28, R29); `capabilities()` → cerrada (R30); `send_response` usa
  `capabilities_for` (R31) y Telegram/Fake usan `capabilities()` (R61); almacén con
  `fail=True` → abierta con aviso en log (R42). Cubre: R28, R29, R30, R31,
  R42, R61.
- [x] T18 — `tests/test_whatsapp_cloud.py` (envío): texto dentro de ventana →
  una petición con URL, `Authorization` y cuerpo exactos (R32), retorno
  `"sent"` (R62); texto fuera de ventana → `ChannelWindowClosed` y cero peticiones
  (R33); plantilla fuera y dentro de ventana con variables en orden (R34) y sin
  `components` cuando no hay variables (R35); botones con `id:proof` y títulos
  (R36); fusión del texto previo como cuerpo (R37) sin envío aparte de ese texto
  (R54) y cuerpo por defecto cuando el texto previo supera 1024, no es texto o
  no existe (R55); `reply.id` > 256 → `ChannelSendFailed` sin
  petición (R38); opciones sin ids, lista y enlace como texto, `preview_url`
  solo en enlace (R39); varios bloques en orden (R40) con retorno `"sent"` (R56); fallo en el
  segundo de tres bloques → sin tercer envío (R41), el MockTransport cuenta una
  sola petición al segundo bloque (R57) y se propaga la excepción traducida
  (R58). Todas con
  `httpx.MockTransport` (R49). Cubre: R32, R33, R34, R35, R36, R37, R38, R39,
  R40, R41, R49, R54, R55, R56, R57, R58, R62.
- [x] T19 — `tests/test_whatsapp_cloud.py` (errores y estados): 131047 →
  `ChannelWindowClosed`; cada código de plantilla → `TemplateNotApproved`;
  401/190, 429/130429, 500, cuerpo no JSON, `httpx.ConnectError` y
  `httpx.ReadTimeout` → `ChannelSendFailed` (R43–R45); log con código,
  subcódigo y `fbtrace_id` (R46) y mensaje de excepción sin cuerpo de Meta
  (R59) ni token (R5); `caplog` sin wa_id ni texto en envío y webhook (R6);
  `delivery_status` para los cuatro valores, mayúsculas/espacios y
  desconocidos (R48); webhook con `statuses[]` (delivered y failed con
  `errors`) → log `whatsapp_status`, sin reenvío ni marca de dedup (R47).
  Cubre: R5, R6, R43, R44, R45, R46, R47, R48, R59.
- [x] T20 — `tests/test_whatsapp_webhook.py` (`POST /send` extremo a extremo
  con el adaptador real inyectado y `MockTransport`): ventana cerrada + texto →
  422 `validation_error`; plantilla → 200; Meta 132001 → 422; Meta 500 → 502
  `upstream_error`. Cubre: R31, R33, R34, R44, R45.

## Documentación y cierre

- [x] T21 — Actualizar `docs/architecture.md` §3.8 (excepción del webhook
  WhatsApp), `docs/proyecto.md` §12/§13 (Decisión del dueño 2026-11-03: Meta
  Cloud API; Twilio/360dialog fuera de alcance; coste de plantillas sigue
  abierto) y `docs/despliegue.md` (alta del webhook en Meta). Cubre: R7.
- [x] T22 — Verificar que las pruebas existentes de Telegram y
  `FakeWhatsAppAdapter` (`test_webhook.py`, `test_send.py`,
  `test_multicanal.py`, `test_grouping.py`) pasan sin modificaciones y que
  `./init.sh` queda verde; documentar la trazabilidad R→test en
  `progress/impl_proveedor_whatsapp_real.md`. Cubre: R50, R60.
