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
