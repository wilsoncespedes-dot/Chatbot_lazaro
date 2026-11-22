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
