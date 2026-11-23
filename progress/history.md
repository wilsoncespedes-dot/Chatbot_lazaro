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

## 2026-11-21 — Feature #67 etiqueta_origen_canal (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Etiqueta de origen:** componente único (`channel_label.py`) con ícono, nombre y color del canal, contraste AA y escape, usado en la bandeja, `/todos`, encabezado del chat, cada mensaje, historial, ficha del cliente y vistas en vivo. Canal inactivo conserva su etiqueta; canal desconocido o directorio caído muestra «Canal desconocido» neutro.
- **Filtro por canal:** cualquier canal registrado (incluye inactivos), combinable con asignación y etiqueta; valor inválido da 422.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4330 passed, 1 skipped. Revisión de código `APPROVED`. Informe R→test en `progress/impl_etiqueta_origen_canal.md`.

## 2026-11-21 — Feature #68 bandeja_unificada_tomar_control (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Bandeja unificada:** `/asesor/conversaciones` lista todas las conversaciones de todos los canales con estado derivado (`atendida_por_bot`, `atendida_por_asesor`, `pendiente`, `cerrada`), filtros por canal y estado, pendientes primero y límite configurable (`PANEL_CONVERSATIONS_LIMIT`). Visibilidad de las atendidas por el bot configurable (`PANEL_BOT_CONVERSATIONS_VISIBLE`).
- **Lectura en vivo:** vista de solo lectura de cualquier conversación, con auditoría `conversation_read`; el refresco no audita de nuevo.
- **Tomar conversación:** `POST /asesor/conversaciones/{id}/tomar` (CSRF, auditoría `conversation_take`) crea el caso si no existe y lo asigna en una operación atómica (`POST /cases/take` en handover, con bloqueo por contacto); 409 si otro asesor lo tomó. El bot calla desde ese momento. «Devolver al bot» reutiliza `/asesor/return`.
- **Contrato:** `CaseTakeRequest`, `CaseTakeResponse`, `scope=overview` y razón `advisor_take`.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4403 passed, 1 skipped. Revisión de código `APPROVED`. Informe R→test en `progress/impl_bandeja_unificada_tomar_control.md`.

## 2026-11-22 — Feature #69 estrategias_asignacion (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Estrategia intercambiable:** interfaz `EstrategiaAsignacion` en handover con `por_carga` (comportamiento de #52) y `round_robin` (puntero persistente con actualización atómica), registradas sin `if/else` en el flujo. Elegible en los ajustes operativos del panel sin redeploy; `manual` sigue disponible y el valor por defecto es el actual. Ambas respetan las reglas de #52.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4423 passed, 1 skipped. Revisión de código `APPROVED`. Informe R→test en `progress/impl_estrategias_asignacion.md`.

## 2026-11-22 — Feature #70 aviso_intencion_compra (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Detección:** frases de intención de compra configurables desde el panel (valores iniciales «me interesa», «quiero reservar», «quiero comprar») y motivo `purchase_intent` del router de IA (solo con `buscar_base_conocimiento`). Pedir un humano sigue escalando como antes.
- **Aviso:** el bot sigue respondiendo; la conversación se marca «Interés de compra» en la bandeja, sube de prioridad y se emite un evento en vivo. Crear caso automáticamente es un ajuste (apagado por defecto). Cada detección queda en eventos con su motivo (sin texto del cliente) y no se repite dentro de un intervalo configurable.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4485 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_aviso_intencion_compra.md`.

## 2026-11-22 — Feature #71 respuestas_rapidas_bot (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Respuestas rápidas:** tabla `respuestas_rapidas` administrable desde el panel (disparador normalizado, bloques de texto, opciones, enlace e imagen, activa y prioridad). Se evalúan antes del RAG solo donde el bot responde (nunca en consentimiento ni con asesor); si coincide, responde sin llamar al modelo y registra evento `quick_reply`. Imagen subida (tipo y tamaño validados, mismo origen) o url https; degrada a enlace en canales sin imágenes. No se siembra contenido de negocio. Compatible con el aviso de intención de compra (#70).
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4556 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_respuestas_rapidas_bot.md`.

## 2026-11-22 — Feature #72 consentimiento_unico_por_cliente (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Consentimiento por cliente:** al login verificado se registra la aceptación vigente por cliente (versión, fecha y canal) y se puebla `identidades_cliente`. Una identidad vinculada a un cliente que aceptó la versión vigente no vuelve a recibir el aviso en otro canal vinculado ni tras cerrar sesión; si cambia la versión se pide una sola vez y cubre todos sus canales. Identidades nunca vinculadas siguen recibiendo el aviso antes de guardar datos (#35). Login obligatorio sin cambios; la supresión borra la aceptación y las identidades.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4582 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_consentimiento_unico_por_cliente.md`.

## 2026-11-22 — Feature #73 id_cliente_y_bienvenida_canales (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **ID de cliente:** ID corto, único y estable (sin caracteres ambiguos, no secuencial), con reintento ante colisión y relleno de clientes existentes; se borra con la supresión. El cliente lo recibe en un mensaje propio tras el login y al pedirlo; el panel lo muestra con botón copiar y permite buscar por ID. Escribir un ID en el chat no identifica ni da acceso a datos.
- **Bienvenida con canales:** lista los canales activos públicos (nombre, ícono y enlace opcional); los simulados solo con el ajuste de demostración.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4618 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_id_cliente_y_bienvenida_canales.md`.

## 2026-11-22 — Feature #74 servidor_mcp_lectura (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Servidor MCP de solo lectura:** herramientas solo de lectura, orquestador como cliente MCP con autorización por estado (`TOOL_MATRIX`) y `cliente_id` tomado de la sesión, `X-Service-Token`, auditoría por llamada, modelo configurable por variables de entorno y degradación al comportamiento actual si el MCP cae. Ofertas de demostración marcadas como tales.
- **Limitación conocida:** el paquete `mcp` no estaba instalado en el `.venv`, por lo que el binding real con el SDK no está probado; las pruebas usan un MCP falso.
- **Resultado:** writer OpenCode/DeepSeek; revisión `APPROVED`. Informe R→test en `progress/impl_servidor_mcp_lectura.md` y revisión en `progress/review_servidor_mcp_lectura.md`.

## 2026-11-22 — Feature #75 dashboard_canales_svg (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Dashboard SVG:** mensajes por canal (con etiqueta de #67), conversaciones por estado y tiempo de respuesta (primera respuesta y de asesor: mediana y p90) en un rango de fechas, para supervisor y admin. Gráficos SVG generados en el servidor, sin JS de terceros ni cambios en la CSP, con título, texto alternativo y tabla de datos accesible. Canales simulados distinguidos y excluibles con filtro; reutiliza los cálculos de métricas existentes.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4710 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_dashboard_canales_svg.md`.

## 2026-11-22 — Feature #76 fuente_clientes_y_futuro_lazaro (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Puerto de clientes:** el orquestador define `FuenteDeClientes` (buscar por ID, listar, crear y actualizar) con la implementación `FuenteClientesLocal`; la creación manual en `/admin/clientes` pasa por el puerto. La sección Clientes muestra una tarjeta «a futuro» sobre una posible conexión con la API de Lazaro, y la documentación describe el adaptador `LazaroClientSource` solo como posibilidad. No se simula ninguna conexión.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4724 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_fuente_clientes_y_futuro_lazaro.md`.

## 2026-11-22 — Feature #77 importacion_clientes (done)
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Importación de clientes:** botón «Importar clientes» en `/admin/clientes` (solo admin) para CSV UTF-8 (coma o punto y coma) con vista previa y errores por fila y campo, detección de duplicados por ID, correo o teléfono (contra la base y dentro del archivo) con elección de actualizar o saltar, y resumen de creados, actualizados, saltados y fallidos con motivo. Escribe a través de `FuenteDeClientes` (#76); sin contraseñas (clientes sin credencial activa), límites configurables, archivo no guardado y protección contra inyección de fórmulas. Correo y teléfono sujetos a retención y supresión.
- **Resultado:** writer OpenCode/DeepSeek; `./init.sh` verde: 4760 passed, 1 skipped. Revisión `APPROVED`. Informe R→test en `progress/impl_importacion_clientes.md`.

## 2026-11-22 — Feature #78 readme_multicanal (done)
- **Modo:** nocturno (sin spec; README revisado y aprobado por reviewer, pendiente de revisión humana)
- **README:** documenta la plataforma multicanal: diagrama de arquitectura (núcleo, puertos, adaptadores, cola y workers), cómo agregar un canal con adaptador propio o con el webhook genérico, formato del webhook y del callback con firma, configuración de cola, servidor MCP y modelo de IA (incluido Ollama), sección «Posibilidades a futuro» (`LazaroClientSource`, datos de negocios por API, login configurable; nada presentado como implementado) y resumen honesto de lo real, lo simulado y lo propuesto. Sin cambios de código. Revisión en `progress/review_readme_multicanal.md`: `APPROVED`.


## 2026-11-17 — #60 rediseno_identidad_panel (done)
- Nueva identidad visual (turquesa, claro/oscuro) en `/admin`, `/asesor` y `/acceso`; marca "Lázaro Software". Shell común con menú lateral agrupado e iconos SVG en línea; menú de asesores por rol (Atención / Supervisión / Privacidad) vía `ContextVar`.
- Inicio con accesos rápidos, editor de "Textos del flujo" en dos columnas sin JS (`:target` + `:has()`), perfiles con avatar e insignias, métricas en tarjetas (`admin.metrics_body`), login nuevo con ojo para ver la contraseña (`/admin/static/login.js`, R26).
- Escrito por Claude a pedido del usuario (OpenCode no instalado en ese equipo). Spec `specs/rediseno_identidad_panel/` (R1–R26). PR #1 y #2 unidos por el dueño. `./init.sh`: 3650 passed, 1 skipped.

## 2026-11-17 — #61 fechas_y_formularios_panel (done)
- Fechas legibles ("17 nov 2026, 2:33 p. m.") en la zona del negocio con `admin.time_html`, también en el chat del caso y el JS en vivo (sustituye `dd/mm HH:MM UTC` de #59 R3). Formularios de alta en cuadrícula (`create-form`) y acciones de Clientes de igual ancho. R7: `/admin/supresiones` dentro del panel admin (PR #4). Spec `specs/fechas_y_formularios_panel/`. PR #3 unido.

## 2026-11-17 — #62 validacion_respuestas_flexible (done)
- La validación anti-alucinación dejaba de rechazar respuestas correctas: quita bloques ```json, ignora marcadores de pasos al inicio de línea y compara citas sin tildes ni puntuación (palabras completas). Cifras inventadas y paráfrasis se siguen rechazando. Spec `specs/validacion_respuestas_flexible/`. PR #5.

## 2026-11-17 — #63 fragmentos_por_seccion (done)
- `rag.domain.chunk_text` trocea por secciones (títulos Markdown y numerados) y frases, con la ruta de títulos al inicio de cada fragmento; la extracción DOCX conserva títulos y filas de tabla. Requiere volver a subir los manuales. Spec `specs/fragmentos_por_seccion/`. PR #6 (encima de #5).

## 2026-11-17 — #64 preguntas_seguimiento (done)
- Mensajes cortos con una pregunta anterior reciente buscan también con "pregunta anterior + mensaje" y combinan resultados; la IA recibe `<pregunta_anterior>` neutralizada. Configurable con `RAG_FOLLOWUP_*`. Spec `specs/preguntas_seguimiento/`. PR #7 (encima de #6).

## Notas del equipo traídas en el merge (rama feat/lazaro-backlog-complete; sus #60-#65 son aquí #79-#84)

## 2026-11-16 — pruebas manuales con Telegram (fuera del flujo SDD, pedido del dueño)

- Hotfix directo (opción A del dueño): `HttpLLMClient` acepta un encabezado de
  sesión opcional (`LLM_SESSION_HEADER`, p. ej. `x-opencode-session` para
  OpenCode Go) y la IA tiene su propio tiempo de espera (`LLM_TIMEOUT_SECONDS`,
  60 s por defecto; antes usaba los 10 s de los servicios internos). Archivos:
  `adapters/llm.py`, `config.py`, `main.py`, `tests/test_adapters.py`,
  `.env.example`. Tests de `services/orchestrator` en verde.
- Hallazgos de configuración local (no de código): la IA apuntaba a OpenAI con
  clave de OpenCode Go; faltaban `IDENTITY_PUBLIC_BASE_URL` e
  `IDENTITY_LINK_SIGNING_KEY`; `RAG_SIMILARITY_THRESHOLD=0.75` es demasiado alto
  para `text-embedding-3-small` (preguntas del manual Siigo puntúan ~0.69,
  preguntas ajenas ~0.40). Para las pruebas se usó 0.5 vía override de compose
  fuera del repo.
- Corregido (directo, a pedido del dueño): `/admin/profiles` ya no crea ni
  cambia perfiles a rol `cliente` (sin credencial nunca podían entrar:
  `login_denied credential_revocada`); remite a `/admin/clientes`. Tests en
  `test_admin.py`; `test_roles_matrix.py::test_admin_role_selector_lists_five_roles`
  ajustado a la regla nueva.
- Corregido (directo): orchestrator, handover y rag reconectan a Postgres si la
  base se reinicia (antes: `BrokenPipeError` y 500 hasta reiniciar el
  servicio). La conexión se comprueba con `SELECT 1` tras 10 s sin uso y se
  descarta ante errores de red. Tests en `handover/tests/test_db_reconnect.py`.
  Verificado reiniciando el contenedor de Postgres: 0 errores.
- `./init.sh`: 3622 passed, 1 skipped.
- Pendiente de decidir: umbral RAG definitivo y si el cambio del encabezado de
  sesión se formaliza como feature.

## 2026-11-17 — #65 asesores_sin_telegram (in_progress, rama `lazaro/asesores-sin-telegram`, encima de PR #7)

- Pedido del usuario: el panel de asesores ya no exige Telegram vinculado
  (el Inicio solo mostraba un aviso) y se quita la generación del enlace en
  Perfiles y roles (botón, `POST /admin/profiles/{id}/link-token`,
  `admin.render_link` y columnas de Telegram).
- Quitados los `except TelegramNotLinked` muertos y el mensaje
  `telegram_not_linked`.
- Se conserva la API interna `/profiles/{id}/link-token` y el `/start` de
  Telegram (feature #20) porque no son del panel; sin enlace nuevo, un asesor
  no podrá usar `/db_query` desde Telegram.

## Rama `juan` (Juan Pablo Parra), traída en el merge del 2026-11-22: sus #59 y #60 son aquí #86 y #87

## 2026-11-21 — Feature #59 `saludos_y_mensajes_sociales` (done)
- **Origen:** al escribir «hola», el bot respondía «No encontré información sobre eso en los manuales…». Causa: con `HARNESS_ROUTER_ENABLED=false`, todo mensaje `ACTIVE` caía en `buscar_base_conocimiento`; sin fragmentos se enviaba `no_answer_reply` y se contaba un fallo RAG que escalaba a asesor al tercer intento.
- **Decisión del dueño:** arreglarlo localmente, sin LLM extra, sin ingerir más PDFs (cuesta dinero) y sin salirse del rol; fuera del corpus, rechazo útil + asesor. Spec en `specs/saludos_y_mensajes_sociales/` (R1–R11, T1–T8), aprobado en revisión enfocada.
- **Cambio:** guardia determinista en `domain.py::_resolve_and_run` solo para `ACTIVE`, antes del router/RAG y después de las keywords; `is_social_message` puro en `harness.py` con igualdad de texto normalizado; `SOCIAL_MESSAGES`/`SOCIAL_REPLY` en `config.py` y `.env.example`. Sin herramientas nuevas (la matriz sigue con 6).
- **Tests:** 8 nuevos en `test_social_messages.py` con trazabilidad R1–R11 en `progress/impl_saludos_y_mensajes_sociales.md`. Se ajustó el payload de `test_multicanal_flow.py` («Hola» → pregunta real) porque «Hola» ya tiene comportamiento propio; la intención del test se conserva y el reviewer lo aprobó.
- **Resultado:** `./init.sh` verde (Git Bash), 3631 passed, 2 skipped; revisión `APROBADO`. Se instalaron `cryptography` y `pg8000`, ya declarados en `requirements.txt`, que faltaban en el entorno.
- **Siguiente:** #60 `calidad_respuestas_y_evaluacion` (specs de prompts, umbral/`top_k` y evaluación sobre el corpus existente), aún sin spec.
- **Ampliación posterior (2026-11-22):** `SOCIAL_MESSAGES` pasó de 11 a 25 frases (`buenas`, `qué tal`, `gracias por todo`, `vale`, `hasta luego`, …) como cambio de configuración sin spec, con tests parametrizados nuevos.

## 2026-11-22 — Feature #60 `calidad_respuestas_y_evaluacion` (done)
- **Origen:** el dueño pidió «hacer ambas cosas»: ampliar los saludos y mejorar la calidad de respuestas y su evaluación. Restricción firme: el corpus está congelado por coste, sin ingesta nueva, sin llamadas extra al LLM, matriz de 6 herramientas, router apagado y sin tipo `saluda` en `eval/scoring.py`.
- **Spec:** `specs/calidad_respuestas_y_evaluacion/` (R1–R13, T1–T10). Primera revisión `CAMBIOS REQUERIDOS` por dos puntos concretos: `HARNESS_ROUTER_PROMPT` está en `harness.py` (no en `domain.py`) y el acceptance exigía ejecutar la medición antes/después, no solo documentar el comando. Corregidos y re-revisado: `APROBADO`.
- **Cambio:** cortesía literal en `LLM_SYSTEM_PROMPT` y `HARNESS_ROUTER_PROMPT` sin nuevos datos ni herramientas; rechazo único «No tengo ese dato en los manuales disponibles. Puedo pasarte con un asesor si lo necesitas.» sincronizado en `config.py`, `.env.example` y `eval/run_eval.py`; dos casos de saludo+pregunta (`s01`, `s02`) en `eval/preguntas.json`; tests de configuración de `RAG_SIMILARITY_THRESHOLD` y `RAG_TOP_K` sin cambiar sus defaults.
- **Tests:** 11 nuevos, trazabilidad R1–R13 en `progress/impl_calidad_respuestas_y_evaluacion.md`. Se ajustaron las copias antiguas del rechazo en `test_decisions.py` y `test_no_inventar.py` (ahora `Settings().no_answer_reply`) y el conteo 19 → 21 en `test_run_eval_attacks.py`. Ningún test saltado ni borrado.
- **Medición real antes/después** con TestClient + `FakeEmbeddings`/`FakeChunkRepository` + manual de ejemplo: 19 preguntas → recuperación 2/13 (15%), rechazos 2/6 (33%), inventadas 4; 21 preguntas → 2/15 (13%), 2/6 (33%), 4. Declarado expresamente como no representativo del corpus de producción; no se recalibró el umbral a partir de esos valores.
- **Resultado:** `./init.sh` verde (Git Bash), 3647 passed, 2 skipped; revisión de código `APROBADO` tras reforzar R8 con la comprobación del camino real de `run_eval.main`.

## 2026-11-22 — Feature #79 `respuestas_rag_completas` (done)
- Se añadieron pruebas para el prompt de síntesis, los límites de fragmentación, el registro íntegro en outbox y el envío completo en varios mensajes por Telegram; se conservan las pruebas existentes de validación de citas.
- El reviewer aprobó la implementación tras revisión estática. `bash ./init.sh` se ejecutó, pero WSL no inició la sesión systemd y `find_python.sh` falló por CRLF antes de pytest. El usuario confirmó que verificó la feature; por instrucción suya se cerró con esta limitación documentada.

## 2026-11-22 — Feature #85 `asesores_sin_telegram` (done)
- Se retiró la condición que impedía a asesores sin Telegram tomar conversaciones y se actualizó la prueba para exigir una toma exitosa. La revisión estática aprobó la feature y confirmó que la API interna de vinculación se conserva mientras el panel deja de ofrecer el enlace.
- La suite no se ejecutó: `./init.sh` falló antes de pytest por CRLF en `find_python.sh`, y `python -m pytest` indicó que pytest no está instalado en el Python de Windows. Por instrucción del usuario, se cerró la feature al quedar solo pendiente esta ejecución.

## 2026-11-22 — Feature #88 `modo_conversacional_general` (done)
- Implementa el fallback conversacional en el orquestador cuando la búsqueda RAG termina sin fragmentos; reutiliza memoria de sesión existente, historial y outbox, con guardia de términos de negocio y prompt injection.
- Revisión estática aprobada y `python -m compileall` correcto. **Las pruebas no se ejecutaron**, por decisión del usuario; queda registrado que `./init.sh` no pudo completarse por configuración de Python/pytest y finales CRLF en el hook.
- Corrección posterior: las preguntas con signos de interrogación ya no se contestan con el saludo social fijo y continúan al fallback conversacional.
- Incidente 2026-11-22: el CI detectó que el default tenía 51 términos frente al límite de 50 del parser compartido, lo que impedía crear `Settings` al iniciar el orquestador. Se retiró `configuro`; las pruebas no se ejecutaron localmente.

## 2026-11-23 — Feature #89 `historial_conversacional_sin_login` (done)
- Se añadió historial reciente del mismo contacto al fallback conversacional cuando `MEMORY_ENABLED=true` e `IDENTITY_LOGIN_REQUIRED=false`; conserva sesión activa, consentimiento, límites, aislamiento y login obligatorio. No agrega tablas ni servicios.
- CI del commit `45f5f3c`: **4914 passed, 1 skipped**, builds Docker de orchestrator, Telegram Gateway, RAG y handover correctos. Revisión estática aprobada. `./init.sh` local se interrumpió porque WSL dejó de iniciar comandos.
- En la misma corrección se arreglaron los cinco fallos CI previos: neutralización del prompt, prueba de entrega por outbox, excepción de «¿Cómo estás?» sin alterar «¿Qué tal?», límite de frase en chunking y bloques Telegram dentro del contrato.
- El código está en la rama principal `codex/preparar-subida-github`. La documentación de despliegue aún apunta a `feat/lazaro-backlog-complete`; el servidor debe seguir la principal para recibir esta versión.

## 2026-11-23 — Feature #90 `canal_gmail` (done)
- Se añadió el adaptador Gmail API al gateway multicanal. El panel permite configurar una bandeja y credenciales OAuth cifradas; el scheduler sincroniza mensajes nuevos de INBOX por Gmail History y el bot/asesores responden como texto plano en el hilo original.
- La primera sincronización no hace backfill. Los adjuntos no se descargan ni se envían. El cursor se conserva ante fallos; los 404 de History vencido se distinguen de un mensaje borrado.
- Guía: `docs/gmail.md`. Requiere OAuth de Google Cloud y programar `scripts/sincronizar_gmail.py` cada 60 s; no se conectó una cuenta real durante esta sesión.
- Revisión de código aprobada en `progress/review_canal_gmail.md`; trazabilidad en `progress/impl_canal_gmail.md`.
- `./init.sh`: **4931 passed, 1 skipped**, exit code 0. `git diff --check` limpio.

## 2026-11-23 — Documentación de cierre Gmail en AWS
- La rama local se actualizó por fast-forward a `f269939`, que ya contenía los commits remotos recientes, Gmail y las fases multicanal.
- A solicitud del usuario, `docs/gmail.md` deja claro que producción usa AWS, pero falta confirmar EC2/ECS/u otro servicio para elegir y programar el scheduler cada 60 s. Incluye checklist de sincronización inicial y correo de prueba.
- Se subirán los archivos locales restantes solicitados por el usuario. No se leyó ni se agregó `.env`; credenciales OAuth no se copiaron al repositorio.
- Sincronización real pendiente; el usuario indicó haber guardado las credenciales del canal.

## 2026-11-23 — Gmail conectado en AWS (EC2)
- Producción confirmada: EC2 con Docker Compose. Canal `soporte-gmail` activo; sincronización inicial manual con `status=initialized` (credenciales OAuth válidas, cursor fijado).
- Nuevo servicio `gmail_sync_worker` (imagen del gateway) que ejecuta `sincronizar_gmail.py --intervalo` cada `GMAIL_SYNC_INTERVAL_SECONDS` (60 s); el script mantiene la pasada única sin `--intervalo`.
- Tests: `scripts/tests/test_sincronizar_gmail.py` (bucle, intervalo, errores) y `services/telegram_gateway/tests/test_gmail_sync_worker_compose.py`. scripts 123, contracts 963, gateway 610 (+2 skipped), handover 450, mcp_lectura 23 en verde; imagen del gateway construida.

## 2026-11-23 — Fases 6–7 de `feat/produccion-multicanal`

- **Fases previas:** fases 1–5 ya estaban implementadas en los commits de la rama
  (`4b2c21b`, `28f8418`, `81646d6`, `dc8e2db`, `6c024b1`).
- **TikTok Business Messaging:** se corrigieron OAuth, firma y el esquema real del
  webhook según la documentación oficial; tokens rotados cifrados, verificación de
  app/cuenta, cuota Redis atómica de 10 mensajes/48 h, y pruebas de mensajes,
  refresh, errores, firma y ruta pública.
- **Messenger e Instagram:** adaptadores Meta sobre webhook firmado compartido,
  separación de lotes mixtos, deduplicación, envío al PSID/IGSID, ventana de 24 h
  controlada en Redis, configuración y pruebas HTTP/webhook.
- **Documentación:** `.env.example`, README, arquitectura y `NOTAS_IMPLEMENTACION.md`
  describen credenciales, URLs públicas, permisos/revisión de proveedores y los
  límites de disponibilidad. Se retiró de `later` el esqueleto de Instagram ya
  cubierto por la integración real.
- **Verificación:** `./init.sh` ejecutó 5025 passed, 14 skipped; los cuatro Docker
  builds de CI y `docker compose build` (con contraseña temporal solo para
  interpolación de build) terminaron correctamente. No se llamaron APIs reales.

## 2026-11-23 — Panel admin: sin Simulador y Canales rediseñado

- **Simulador retirado del panel:** se quitaron el enlace del menú, las rutas
  `/admin/simulador` y `/asesor/simulador`, `simulator_page.py`,
  `simulator_routes.py`, el cliente `adapters/simulator.py` y sus tests. El
  adaptador `simulado` del gateway, su buzón y `scripts/simular_canal.py` se
  conservan (el profesor pidió un adaptador SIMULADO marcado); `simulated_label`
  pasó a `channels.py` porque el dashboard lo sigue usando.
- **Canales:** la tabla con todo el formulario en una columna se cambió por una
  ficha por canal (etiqueta, estado, datos, webhook con Copiar, acciones) con la
  edición plegable en «Editar canal» y el alta después del listado. Las casillas
  de verificación del panel ya no se dibujan como cajas grandes (`label.check`).
- **Verificación:** tests de canales, rutas, navegación y dashboard en verde; un
  test nuevo fija el diseño en fichas. Revisado en el navegador en escritorio y
  móvil, tema claro y oscuro.
