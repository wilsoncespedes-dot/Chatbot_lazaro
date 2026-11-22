# Bitácora histórica (append-only)

> Cada vez que se cierra una sesión, su resumen se añade aquí, al final.
> El detalle de las sesiones anteriores al 2026-11-15 (bitácora completa,
> specs e informes `impl_`/`review_`/`specreview_` de cada feature) está en el
> tag git `archivo-antes-limpieza-2026-11-15`. Para consultarlo:
> `git show archivo-antes-limpieza-2026-11-15:progress/history.md`.

---

## 2026-10-30 a 2026-11-14 — Resumen de las 57 features cerradas

Todas pasaron por spec, implementación, `./init.sh` verde y revisión de código.

| # | Feature | Qué entrega |
|---|---------|-------------|
| 1 | `contratos_servicios` | Contratos entre servicios |
| 2 | `esqueleto_servicios` | Esqueleto de servicios con Docker |
| 3 | `telegram_gateway` | Telegram gateway |
| 4 | `orquestador_basico` | Orquestador básico |
| 5 | `rag_ingesta_busqueda` | RAG: ingesta de manuales y búsqueda con umbral |
| 6 | `no_inventar` | No inventar: validación de citas y rechazo fijo |
| 9 | `contrato_asignar_caso` | Contrato: asignar un caso a un asesor |
| 7 | `traspaso_asesor` | Traspaso a asesor |
| 8 | `evaluacion` | Evaluación con preguntas de ejemplo |
| 10 | `validacion_config_asesores` | Validación de ADVISOR_CHAT_IDS al arrancar handover |
| 11 | `registro_solicitudes_traspaso` | Registro de cada solicitud de traspaso en handover |
| 12 | `vencimiento_automatico` | Ejecución periódica de POST /cases/check-timeouts |
| 13 | `contrato_autorizacion_asesores` | Contrato: autorización de asesores sobre un caso |
| 14 | `autorizacion_asesores` | Autorización de asesores para responder y cerrar casos |
| 15 | `contrato_conversacion_caso` | Contrato: mensajes del cliente hacia el asesor |
| 16 | `conversacion_cliente_asesor` | Conversación bidireccional cliente-asesor por Telegram |
| 17 | `contrato_cierre_casos_huerfanos` | Contrato: cierre de casos huérfanos (asesor retirado de ADVISOR_CHAT_IDS) |
| 18 | `candado_repositorio_orquestador` | Candado en la conexión compartida de PostgresRepository del orquestador |
| 19 | `edicion_fragmentos` | Edición del contenido de fragmentos RAG |
| 20 | `verificacion_cuentas` | Vincular perfiles verificados con cuentas de Telegram |
| 21 | `panel_administracion` | Panel administrativo mínimo |
| 22 | `panel_fragmentos` | Manuales y fragmentos en el panel administrativo |
| 23 | `bootstrap_administrador` | Crear el primer administrador de forma segura |
| 24 | `despliegue_produccion` | Configuración y verificaciones para despliegue de producción |
| 25 | `clasificador_consultas` | Clasificar consultas por categoría configurable |
| 26 | `consulta_bd_lenguaje_natural` | Consultas de datos autorizadas en lenguaje natural |
| 27 | `privacidad_y_retencion_datos` | Política de privacidad, retención y eliminación de datos |
| 28 | `despliegue_retencion` | Retención de datos en Render |
| 29 | `panel_asesores` | Panel de asesores para atender casos |
| 30 | `agrupacion_mensajes` | Agrupar mensajes consecutivos del cliente |
| 31 | `busqueda_hibrida_rag` | Búsqueda híbrida para manuales |
| 32 | `traspaso_automatico_fallos` | Derivar automáticamente tras fallos repetidos |
| 33 | `contrato_listar_casos_asesor` | Contrato para listar casos de un asesor |
| 34 | `robustez_estado_traspaso_automatico` | Retención y recuperación del estado de traspaso automático |
| 35 | `consentimiento_antes_de_datos` | No guardar datos personales antes del consentimiento |
| 36 | `nucleo_multicanal` | Núcleo multicanal Telegram y WhatsApp |
| 37 | `estados_y_consentimiento` | Estados de conversación y consentimiento versionado |
| 38 | `identidad_credenciales` | Identidad web, credenciales y sesiones |
| 39 | `harness_ia_por_estado` | Harness de IA con herramientas y datos por estado |
| 40 | `memoria_por_cliente` | Historial resumido y memoria permanente por cliente |
| 41 | `panel_asesores_multicanal` | Panel de asesores multicanal y solicitudes de supresión |
| 42 | `administracion_y_avisos` | Administración de clientes, textos y avisos |
| 43 | `proveedor_whatsapp_real` | Integración del proveedor real de WhatsApp |
| 44 | `confirmar_callback_telegram` | Confirmar callback_query de Telegram (answerCallbackQuery) |
| 45 | `corregir_foreign_session_windows` | Corregir tipo de parámetro en PostgresRepository.foreign_session_windows |
| 46 | `consentimiento_texto_telegram` | Consentimiento por frase de texto en Telegram (sin botones inline) |
| 47 | `healthcheck_dependencias` | Health checks reales de dependencias |
| 48 | `retirar_asesores_telegram` | Retirar la atención de asesores por Telegram |
| 49 | `roles_supervisor_responsable_datos` | Roles de supervisor y responsable de datos en el panel |
| 50 | `notas_internas_y_etiquetas` | Notas internas y etiquetas en los casos |
| 51 | `respuestas_guardadas` | Respuestas guardadas para asesores |
| 52 | `asignacion_automatica_carga` | Asignación automática de casos por carga |
| 53 | `panel_tiempo_real` | Panel de asesores en tiempo real |
| 54 | `segundo_factor_panel` | Segundo factor en el acceso del personal al panel |
| 55 | `evaluacion_ataques_y_preguntas_reales` | Evaluación con casos de ataque y preguntas reales |
| 56 | `rediseño_visual_paneles` | Rediseño visual moderno de los paneles |
| 57 | `retencion_evidencia_y_privacidad_inicial` | Aplicar la retención aprobada a la evidencia de consentimiento |

Último `./init.sh` antes de la limpieza (2026-11-14): 3579 passed, 1 skipped.
## 2026-11-15 — Limpieza del repositorio y guía de instalación
- **Motivo:** al equipo le costaba abrir el proyecto. Una clonación limpia de la rama de trabajo instala y pasa los tests; el problema era que GitHub entrega por defecto una rama 256 archivos por detrás, el README pedía pasos que no aplican a un clon (`cd ~/proyectos/…`, `git init`, `claude`) y no explicaba PowerShell ni Docker, había rutas con `ñ` y `.codex/hooks.json` apuntaba a una ruta de un solo PC.
- **Limpieza:** se archivaron en el tag `archivo-antes-limpieza-2026-11-15` y se borraron del árbol `specs/` (172 archivos), los informes de `progress/` (186), `.codex/` y `.agents/`. `feature_list.json` pasó de 95 KB a 9 KB (features `done` resumidas) y esta bitácora de 57 KB a 6 KB. `init.sh` y `CHECKPOINTS.md` exigen spec solo en `spec_ready`/`in_progress`.
- **Documentación:** README reescrito (clonar, instalar, tests, Docker, problemas frecuentes). Correcciones en `docs/especificacion.md` (restos de exportación, proveedor de WhatsApp ya elegido, consentimiento por texto en Telegram, hash real de contraseñas, enlace de la fuente de Meta), `docs/proyecto.md` (nota del arnés, secciones históricas, riesgo de consulta de datos) y `docs/architecture.md`.
- **Sin cambios** en `services/`, `contracts/`, `eval/`, `scripts/`, `docker-compose.yml` ni `.github/`. `contracts/` no se toca: es código en uso y `CONTRATOS.md` está verificado por tests.
## 2026-11-15 — Feature #58 correcciones_sonar (done)
- **Origen:** reporte de análisis estático de Sonar con 12 hallazgos; spec en `specs/correcciones_sonar/` (R1–R12, T1–T15), aprobado por el reviewer.
- **Correcciones:** detección de correo en tiempo lineal en `memory.py` y `admin.py` del orquestador, `database_url` de rag vacío por defecto (producción lo exige), helpers extraídos en `scripts/configurar_webhook.py` y aserción reforzada en `services/rag/tests/test_adapters.py`.
- **Sin cambio de código:** los falsos positivos quedaron marcados con `# NOSONAR` (verificados por `scripts/tests/test_sonar_markers.py`); el hallazgo de `test_advisor_commands.py` estaba obsoleto y el archivo no se tocó.
- **Resultado:** `./init.sh` verde, 3624 passed, 1 skipped (un ciclo de corrección por ids de `parametrize` en Windows); revisión de código `APPROVED`.
- **Pendiente fuera de alcance:** `eval/scoring.py` línea 30 conserva la misma regex de correo; no estaba en el reporte y queda a decisión del leader.
## 2026-11-16 — Retiro del segundo factor en paneles (solicitud del dueño)
- **Cambios:** acceso admin/asesor con usuario y contraseña; se quitaron campos, validación, pantallas/rutas de segundo factor, acción de restablecimiento y variables/dependencia asociadas. Se actualizó `docs/especificacion.md` y la guía de despliegue.
- **Sesiones y datos previos:** las sesiones antiguas restringidas ya pueden entrar al panel. Las tablas/filas 2FA existentes se conservan y no se eliminan automáticamente; el panel dejó de requerirlas.
- **Verificación:** `./init.sh` verde, 3572 passed, 1 skipped; revisión de código sin hallazgos.
## 2026-11-16 — Hotfix `</script>` y feature #59 chat_caso_asesor (done)
- **Hotfix previo (a mano, pedido del dueño):** faltaba `</script>` en las dos etiquetas de `panel_live.js` de `advisor_panel.py`; con `panel_live_enabled` la bandeja y el detalle del caso quedaban en blanco. El test de regresión entró en el acceptance de #59.
- **#59:** el detalle del caso (`/asesor/cases/{case_id}`) muestra la conversación como chat de burbujas (cliente a un lado; asesor y asistente al otro, con autor y hora UTC localizada por JS) y el compositor queda debajo del chat; con ventana de WhatsApp cerrada ofrece plantilla y las respuestas guardadas siguen cargándose. `POST /asesor/reply` con `origen=caso` vuelve al caso. Actualización en vivo con autoscroll, sin `innerHTML` ni tocar el compositor. CSS `.chat*` en `ADMIN_CSS` con contraste WCAG y foco visible. Spec en `specs/chat_caso_asesor/` (R1–R39, T1–T14).
- **Tests:** nuevo `services/orchestrator/tests/test_chat_caso_asesor.py` y `test_every_script_tag_is_closed` en `test_panel_visual.py` (R30, regresión del hotfix). Ningún test existente editado.
- **Resultado:** writer OpenCode/DeepSeek en un solo intento, sin ciclos de corrección; `./init.sh` verde, 3613 passed, 1 skipped. Revisiones de spec y de código `APPROVED`.
## 2026-11-16 — Pruebas manuales con Telegram (fuera del flujo SDD, pedido del dueño)
- **Hotfix:** `HttpLLMClient` acepta un encabezado de sesión opcional (`LLM_SESSION_HEADER`, p. ej. `x-opencode-session` para OpenCode Go). La IA tiene su propio tiempo de espera (`LLM_TIMEOUT_SECONDS`, 60 s por defecto). Archivos: `adapters/llm.py`, `config.py`, `main.py`, `tests/test_adapters.py`, `.env.example`.
- **Corregido (directo):** `/admin/profiles` ya no crea perfiles `cliente` (remite a `/admin/clientes`). Orchestrator, handover y rag reconectan a Postgres tras un reinicio de la base: `SELECT 1` tras 10 s sin uso y descarte ante errores de red (`handover/tests/test_db_reconnect.py`).
- **Configuración local (no código):** `RAG_SIMILARITY_THRESHOLD=0.75` es demasiado alto para `text-embedding-3-small` (~0.69 en preguntas del manual, ~0.40 en preguntas ajenas); en las pruebas se usó 0.5. Faltaban `IDENTITY_PUBLIC_BASE_URL` e `IDENTITY_LINK_SIGNING_KEY`.
- **Resultado:** `./init.sh` 3622 passed, 1 skipped. **Pendiente de decidir:** umbral RAG definitivo y si el encabezado de sesión se formaliza como feature.
## 2026-11-21 — Fase 0 de la ampliación multicanal genérica (solo docs)
- **Origen:** revisión del profesor (plataforma multicanal y multiagente de verdad). El dueño aprobó el plan por fases con cambios: login obligatorio, etiqueta de origen en todo el panel (prioridad alta), outbox en Postgres; la importación de clientes y la API de Lázaro quedan como «a futuro».
- **Rama:** `feat/multicanal-generico`. No se despliega sola; los push a `feat/lazaro-backlog-complete` sí se despliegan en AWS.
- **Registrado:** features #60–#78 en `feature_list.json` (#78 README con `sdd: false`) y `esqueleto_instagram` en `later`. Docs: `docs/especificacion.md`, `docs/architecture.md` y `docs/proyecto.md` (§1 y §13.6).
- **Decisiones pendientes del dueño:** protección de secretos de `canales` (antes de #61) y Excel en la importación (antes de #77).
## 2026-11-21 — Feature #60 contrato_canal_abierto (done)
- **Contrato:** `Channel` pasa a ser un slug (2–32, `^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$`). `MessageKind` admite `image`/`file`/`audio`. `NormalizedMessage` gana `attachments` (`Attachment`, solo metadatos, máx. 10), `metadata` (`pydantic.JsonValue`, ≤ 4096 bytes, profundidad 5, sin `NaN`/`Infinity`) y `direction` (`inbound`/`outbound`). Los campos nuevos se omiten al serializar con su valor por defecto (`exclude_if`). También: capacidades `supports_buttons/images/files/audio`, bloque `ImageBlock` y constantes de firma (`X-Lazaro-Timestamp`, `X-Lazaro-Signature`, ventana 300 s). Spec en `specs/contrato_canal_abierto/` (R1–R48, T1–T17).
- **`CONTRATOS.md`:** tablas de `NormalizedMessage`, `Attachment` y `ChannelCapabilities`, y la sección «Canal genérico (webhook firmado)»: `POST /webhooks/{canal_id}`, firma, callback y equivalencia con los nombres del encargo. Los ejemplos están firmados y los verifican los tests. También las filas 422 y el supuesto S17.
- **Guardas temporales:** el gateway responde `422` a un canal distinto de `telegram`/`whatsapp` y a un bloque `image` sin `supports_images` (#61 lo sustituye por degradación). El orquestador responde `422` a un canal no atendido o a `direction=outbound` (`ATTENDED_CHANNELS`, la retira #65). Los tipos multimedia reciben `unsupported_reply` sin persistir.
- **Tests:** nuevos `contracts/tests/test_canal_abierto.py`, `contracts/tests/test_canal_abierto_doc.py`, `services/telegram_gateway/tests/test_canal_abierto.py` y `services/orchestrator/tests/test_canal_abierto.py`. Ningún test ni ejemplo existente se editó (R47).
- **Resultado:** writer OpenCode/DeepSeek. Un ciclo de corrección por revisión de código: `JsonValue` de pydantic con `allow_nan=False` y tests de tuplas, clave no texto y 100 000 niveles (R17), y consentimiento previo en los tests de R43/R44. `./init.sh` verde: 3729 passed, 1 skipped. Revisiones de spec y de código `APPROVED`.
- **Nota del arnés:** `scripts/run_opencode_writer.sh` no acepta `progress/review_code_<feature>.md` como `--context`. Los hallazgos se copiaron a `progress/impl_<feature>.md`.
## 2026-11-21 — Feature #61 registro_canales_gateway (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Gateway:** puerto `Canal` (`ports/canal.py`) y `ChannelRegistry` con registro por decorador (tipo desconocido o duplicado falla cerrado). Telegram y WhatsApp Cloud API migrados a `adapters/channels/`; los webhooks heredados responden igual y `POST /send` resuelve el adaptador con el registry.
- **Tabla `canales`:** repositorio pg8000 perezoso con schema idempotente, siembra diferida de `telegram` y `whatsapp` desde las variables actuales, y secretos de `config` cifrados con Fernet (`cryptography`, clave `CHANNEL_SECRETS_KEY` opcional); listados sin secretos y logs sin valores.
- **Degradación pura:** botones a lista numerada, imagen a enlace y lista a texto numerado según capacidades; sustituye la guarda temporal de #60.
- **Rutas internas:** `/channels`, alta, edición, activación y revelar/regenerar secreto con `X-Service-Token`, documentadas en `CONTRATOS.md`. Health consulta Redis y PostgreSQL; Compose y `render.yaml` ajustados.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 3879 passed, 1 skipped. Revisiones de spec y de código `APPROVED`. Informe R→test en `progress/impl_registro_canales_gateway.md`.

## 2026-11-21 — Feature #62 webhook_generico_firmado (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Gateway:** adaptador `webhook_generico` y ruta pública `POST /webhooks/{canal_id}` con HMAC-SHA256 de `<timestamp>.<cuerpo>`, ventana anti-repetición configurable, 404 sin distinguir inexistente/inactivo, 413/401/422 con precedencia definida, e idempotencia por `(canal_id, external_message_id)`.
- **Callback saliente:** `POST` firmado a `config.callback_url` con bloqueo anti-SSRF (https, sin direcciones privadas/loopback/link-local/metadatos). Ejemplos firmados de `CONTRATOS.md` verificados por tests.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 3979 passed. Revisiones de spec y de código `APPROVED`. Informe R→test en `progress/impl_webhook_generico_firmado.md`.

## 2026-11-21 — Feature #63 canal_simulado (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Adaptador SIMULADO:** tipo `simulado` configurable desde `config` (nombre, ícono, color, capacidades), sin llamadas de red; respuestas salientes en un buzón propio con retención corta configurable. La marca SIMULADO aparece en clase, docstring, etiqueta del panel y herramienta de prueba.
- **Panel y herramienta:** página de prueba tipo chat (solo admin y supervisor) y `scripts/simular_canal.py`, que envía mensajes firmados al webhook genérico. Hasta #65 el orquestador rechaza con 422 los canales no atendidos y el buzón lo muestra como tal.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4103 passed, 1 skipped. Revisiones de spec y de código `APPROVED`. Informe R→test en `progress/impl_canal_simulado.md`.

## 2026-11-21 — Feature #64 cola_entrada_outbox (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Cola y outbox en Postgres:** `POST /messages` guarda el mensaje en la tabla de entrada junto a la deduplicación y responde 202; worker `procesar_entrantes` (`FOR UPDATE SKIP LOCKED`, orden por conversación, reintentos con máximo y motivo de fallo). Toda respuesta saliente se escribe en `outbox` en la misma transacción; worker `enviar_salientes` con backoff exponencial con jitter, sin reintento de 422, orden por destino y entrega al menos una vez.
- **Panel y operación:** envíos fallidos visibles y reintentables por supervisor/admin con auditoría; workers añadidos a `docker-compose.yml`; purga por retención y supresión.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4161 passed, 1 skipped (3 rondas de corrección: 44 -> 20 -> 0 fallos). Revisión de código `APPROVED`. Informe R→test en `progress/impl_cola_entrada_outbox.md`.

## 2026-11-21 — Feature #65 nucleo_sin_nombres_canal (done)
- **Modo:** supervisado; spec aprobado por el reviewer. El código lo escribió Claude directamente (OpenCode Go sin cuota), por decisión del dueño, sin revisión de código del reviewer.
- **Núcleo sin nombres de canal:** el orquestador decide ventana y plantillas por `ChannelInfo.capabilities` y el consentimiento por `config.consent_mode` (`texto`/`boton`), leídos de `GET /channels` del gateway con caché (`CHANNEL_DIRECTORY_TTL_SECONDS`) y copia obsoleta. Se retiran `ATTENDED_CHANNELS`, `INBOX_CHANNELS` y `TEXT_CONSENT_CHANNELS`; los literales `telegram`/`whatsapp` quedan solo en `orchestrator/legacy.py`.
- **Gateway:** `default_capabilities` en cada adaptador y siembra idempotente de `consent_mode`. **Datos:** columna `canal_id` en contactos y mensajes con migración idempotente.
- **Resultado:** `./init.sh` verde: 4224 passed, 1 skipped. Informe R→test en `progress/impl_nucleo_sin_nombres_canal.md`.

## 2026-11-21 — Feature #66 panel_administracion_canales (done)
- **Modo:** supervisado. Claude escribió el spec y el código directamente (OpenCode Go sin cuota), por decisión del dueño, sin revisión del reviewer.
- **Panel `/admin/canales` (solo admin):** listar, crear y editar canales (nombre, ícono de lista cerrada, color `#RRGGBB` con contraste ≥ 4.5 frente a blanco, tipo de adaptador registrado, consentimiento, credenciales, URL de callback); activar y desactivar. URL del webhook (`GATEWAY_PUBLIC_BASE_URL/webhooks/{id}`) y secreto, solo tras acción explícita, con botón copiar (`/admin/static/canales.js`, sin cambiar la CSP). Ver y regenerar el secreto quedan en auditoría, sin el valor.
- **Credenciales:** el gateway guarda solo pistas (`…` + últimos 4) en `pistas_credenciales`. Cada cambio invalida el directorio de canales del orquestador.
- **Resultado:** `./init.sh` verde: 4302 passed, 1 skipped. Informe R→test en `progress/impl_panel_administracion_canales.md`.
