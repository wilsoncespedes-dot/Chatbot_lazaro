# Bitácora histórica (append-only)

> Cada vez que se cierra una sesión, su resumen se añade aquí.
> No edites entradas anteriores. Solo añades al final.

---

## 2026-10-30 — Bootstrap del arnés para el chatbot Lázaro
- **Agente:** humano + Claude (preparación del arnés).
- **Cambios:** arnés SDD adaptado desde el ejemplo de notas: se quitó la app
  de ejemplo; docs reescritos para Python + FastAPI en monorepo de
  microservicios (`docs/architecture.md`, `conventions.md`, `verification.md`);
  contexto del proyecto en `docs/proyecto.md`; `feature_list.json` con las 8
  features de la versión mínima; pytest en lugar de unittest; bloqueo de
  lectura de `.env` para los agentes; rutas `services/` protegidas para el leader.
- **Resultado:** `./init.sh` verde (aún sin tests: normal antes de la feature 2).

## 2026-10-30 — Feature #1 contratos_servicios (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec revisión 1 SPEC_CHANGES_REQUESTED → corregido; revisión 2
  SPEC_APPROVED (`progress/specreview_contratos_servicios.md`) → `in_progress`
  con `auto_approved: true` → implementer T1–T19 → review APPROVED
  (`progress/review_contratos_servicios.md`).
- **Cambios:** `contracts/CONTRATOS.md` (8 rutas + reglas comunes + supuestos
  S1–S10), paquete `contracts/lazaro_contracts/` (20 modelos Pydantic v2,
  incluido `ErrorResponse`), `contracts/examples/` (21 JSON),
  `contracts/tests/`, `contracts/requirements.txt` (`pydantic>=2.12,<3`) y una
  línea en `requirements-dev.txt`. Informe: `progress/impl_contratos_servicios.md`.
- **Resultado:** `./init.sh` verde, 273 tests pasan. R1–R52 cubiertos.
- **Pendiente humano:** revisar el spec auto-aprobado; confirmar que los
  cambios de `.claude/settings.json` (modo nocturno) se restauran con
  `./modo.sh` y no se commitean con la feature; decidir en la feature 2 cómo
  llega `lazaro_contracts` a las imágenes Docker.

## 2026-10-30 — Feature #2 esqueleto_servicios (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec vuelta 1 SPEC_CHANGES_REQUESTED, vuelta 2 SPEC_APPROVED →
  `in_progress` con `auto_approved: true` → implementer T1–T19 → review APPROVED
  (`progress/review_esqueleto_servicios.md`).
- **Cambios:** 4 servicios FastAPI en `services/` (telegram_gateway,
  orchestrator, rag, handover) con `/health`, auth por `X-Service-Token`,
  Dockerfile y tests; `docker-compose.yml` (postgres con pgvector, redis, 4
  servicios), script SQL de init, `.env.example`, `.github/workflows/ci.yml`,
  `.dockerignore`, `scripts/`. Informe: `progress/impl_esqueleto_servicios.md`.
- **Resultado:** `./init.sh` verde, 386 tests pasan.
- **Pendiente humano:** revisar el spec auto-aprobado.

## 2026-10-30 — Feature #3 telegram_gateway (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec aprobado (`progress/specreview_telegram_gateway.md`) →
  `in_progress` con `auto_approved: true` → implementer → review APPROVED
  (`progress/review_telegram_gateway.md`).
- **Cambios:** `services/telegram_gateway/` con webhook protegido por secreto,
  dedup en Redis, cliente del orquestador, envío a Telegram (`POST /send`),
  adaptadores con versiones falsas y tests. Informe: `progress/impl_telegram_gateway.md`.
- **Resultado:** `./init.sh` verde.
- **Pendiente humano:** revisar el spec auto-aprobado.

## 2026-10-30 — Feature #4 orquestador_basico (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec aprobado (`progress/specreview_orquestador_basico.md`) →
  `in_progress` con `auto_approved: true` → implementer T1–T29 → review APPROVED
  (`progress/review_orquestador_basico.md`).
- **Cambios:** `services/orchestrator/` con `POST /messages` (202, dedup por
  `update_id`), contactos e historial, eventos de decisión, búsqueda en RAG,
  respuesta con LLM, `NO_ANSWER_REPLY` + traspaso sin resultados, traspaso por
  palabras clave, adaptadores con versiones falsas y tests. Informe:
  `progress/impl_orquestador_basico.md`.
- **Resultado:** `./init.sh` verde, 460 tests pasan.
- **Pendiente humano:** revisar el spec auto-aprobado.

## 2026-10-30 — Feature #5 rag_ingesta_busqueda (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec revisado (`progress/specreview_rag_ingesta_busqueda.md`) →
  `in_progress` con `auto_approved: true` → implementer T1–T17 → review APPROVED
  (`progress/review_rag_ingesta_busqueda.md`).
- **Cambios:** servicio RAG: `POST /manuals` (PDF/DOCX, extracción, chunking,
  embeddings), `POST /search` con umbral y `top_k`, adaptadores de embeddings y
  repositorio (falso en memoria + pgvector), `scripts/cargar_manual.py`, variables
  nuevas en `.env.example` y tests. Informe: `progress/impl_rag_ingesta_busqueda.md`.
- **Resultado:** `./init.sh` verde, 498 tests pasan.
- **Pendiente humano:** revisar el spec auto-aprobado; calibrar umbral 0.75 y modelo de embeddings con un manual real.

## 2026-10-30 — Feature #6 no_inventar (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec revisado (`progress/specreview_no_inventar.md`) →
  `in_progress` con `auto_approved: true` → implementer → review APPROVED
  (`progress/review_no_inventar.md`).
- **Cambios:** barrera anti-alucinaciones en el orquestador: salida JSON del LLM
  `{answer, citations}`, validación de citas (chunk_id, quote literal) y números,
  rechazo fijo `NO_ANSWER_REPLY` con evento `invalid_answer`, tests de seguridad.
  Informe: `progress/impl_no_inventar.md`.
- **Resultado:** `./init.sh` verde, 527 tests pasan.
- **Pendiente humano:** revisar el spec auto-aprobado.

## 2026-10-30 — Feature #8 evaluacion (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec revisado (`progress/specreview_evaluacion.md`) →
  `in_progress` con `auto_approved: true` → implementer → review APPROVED
  (`progress/review_evaluacion.md`).
- **Cambios:** `eval/` con `preguntas.json` (>=15 preguntas), manual de ejemplo,
  `scoring.py`, `run_eval.py` (informe `eval/resultados_<fecha>.md`), tests y
  `EVAL_SINK_PORT` en `.env.example`. Informe: `progress/impl_evaluacion.md`.
- **Resultado:** `./init.sh` verde, 565 tests pasan.
- **Pendiente humano:** revisar el spec auto-aprobado.

## 2026-10-30 — Feature #9 contrato_asignar_caso (done)
- **Agente:** leader (modo supervisado) + spec_author, reviewer, implementer.
- **Modo:** supervisado (spec aprobado por el humano)
- **Flujo:** spec (`specs/contrato_asignar_caso/`) revisado
  (`progress/specreview_contrato_asignar_caso.md`) → aprobación humana **sin R13**
  (el humano retiró R13: no se toca la fila 404 existente de Reglas comunes) →
  `in_progress` → implementer → review APPROVED
  (`progress/review_contrato_asignar_caso.md`).
- **Cambios:** ruta aditiva `POST /cases/{id}/assign` en `contracts/CONTRATOS.md`
  (con supuesto S11), modelos `CaseAssignRequest` y `CaseAssignResponse` en
  `lazaro_contracts/cases.py` exportados en `__init__.py`, ejemplos
  `case_assign_request.json` y `case_assign_response.json`, y tests de contrato.
  Informe: `progress/impl_contrato_asignar_caso.md`.
- **Resultado:** `./init.sh` verde, 598 tests pasan.
- **Siguiente:** desbloquea la #7 `traspaso_asesor`.

## 2026-10-31 — Feature #7 traspaso_asesor (done)
- **Agente:** leader + spec_author, reviewer, implementer.
- **Modo:** spec auto-aprobado en nocturno; bloqueada allí
  (`progress/blocked_traspaso_asesor.md`) y retomada en supervisado.
- **Flujo:** dependía de la #9 `contrato_asignar_caso` (ruta
  `POST /cases/{id}/assign`); con la #9 cerrada → implementer → review APPROVED
  (`progress/review_traspaso_asesor.md`). El humano confirmó los supuestos
  R10 y R11.
- **Cambios:** servicio handover con `POST /handover` (crea/reutiliza caso, avisa
  a `ADVISOR_CHAT_IDS`, registra avisos, `no_advisors`), `POST /cases/{id}/assign`,
  `POST /cases/{id}/close`, `POST /cases/check-timeouts` con reloj inyectado,
  adaptadores gateway y repositorio con versiones falsas; en el orquestador
  `POST /cases/{id}/reply` y `NO_ADVISORS_REPLY`; tests de seguridad.
  Spec: `specs/traspaso_asesor/`. Informe: `progress/impl_traspaso_asesor.md`.
- **Resultado:** `./init.sh` verde, 674 tests pasan.

## 2026-10-31 — Claude coordina y OpenCode/DeepSeek escribe
- **Agente:** Claude + OpenCode/DeepSeek.
- **Cambios:** OpenCode configurado con proveedor DeepSeek y un agente
  `implementer` con permisos acotados; `scripts/run_opencode_writer.sh` valida
  que la feature esté `in_progress` y delega escritura. Claude conserva SDD,
  revisión y ejecución de `./init.sh` en modo supervisado y nocturno.
  Documentación actualizada en `AGENTS.md`, `CLAUDE.md` y `README.md`.
- **Verificación:** `./init.sh` verde (674 tests); `opencode debug agent`
  confirma el modelo DeepSeek y que Bash y la edición de `feature_list.json`
  están denegados al writer; sintaxis de scripts verificada.
- **Pendiente:** conectar la credencial DeepSeek en OpenCode. La lista local de
  credenciales aún solo muestra Anthropic; no se ejecutó una llamada real al
  modelo. Las features #10–#16 continúan `blocked` y el puente se niega a
  escribirlas hasta que una esté aprobada y pase a `in_progress`.

## 2026-10-31 — Feature #13 contrato_autorizacion_asesores (done)
- **Agente:** leader (modo supervisado) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek Flash como writer.
- **Modo:** supervisado (spec aprobado por el humano).
- **Flujo:** spec (`specs/contrato_autorizacion_asesores/`) revisado
  (`progress/specreview_contrato_autorizacion_asesores.md`) → decisiones del
  humano → `in_progress` → OpenCode T1–T53 → review APPROVED
  (`progress/review_contrato_autorizacion_asesores.md`).
- **Decisiones del humano (2026-10-31):** C1 precedencia 403 → 404 → 409 → 403
  (otro asesor); C2 `close` sobre `closed` mantiene S8 (200 sin cambios);
  C3 fallo cerrado con la fila `502 upstream_error` ya publicada de reply;
  C5 reply sobre `closed` → `409 case_closed` sin enviar nada (descarta
  `403 forbidden`); C6 el orquestador autoriza antes de comprobar el caso;
  (d) `assign` de un caso `assigned` por otro asesor → 403; D4 de la #16
  opción (a): la línea `Llama` de `authorize` nombra `/cerrar`.
- **Excepciones a «no editar lo publicado»:** E1, la «Dónde» de la fila común
  `409 | case_closed` añade `/cases/{id}/reply` (C5); E2, la fila S11 cambia
  para que otro asesor reciba 403 (d). S12 documenta ambos cambios.
- **Cambios:** ruta `POST /cases/{id}/authorize` en `contracts/CONTRATOS.md`,
  filas `403 forbidden` (común, reply, close, assign), fila `409 case_closed`
  en reply, supuesto S12; modelos de autorización en `lazaro_contracts/cases.py`
  exportados en `__init__.py`; ejemplos `case_authorize_request.json` y
  `case_authorize_response.json`; tests de contrato. Informe:
  `progress/impl_contrato_autorizacion_asesores.md`.
- **Resultado:** `./init.sh` verde, 742 tests pasan (antes 674; 374 en
  `contracts`). R1–R53 cubiertos.
- **Pendiente:** C5 deja desalineados los specs de la #14 (D5, D7) y la #16
  (R14, Rec. 2, D6); ver design §9 de la #13.

## 2026-10-31 — Feature #10 validacion_config_asesores (done)
- **Agente:** leader (modo supervisado) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek Flash como writer.
- **Modo:** supervisado (spec aprobado por el humano).
- **Flujo:** spec (`specs/validacion_config_asesores/`) revisado
  (`progress/specreview_validacion_config_asesores.md`) → decisiones del humano
  → `in_progress` → OpenCode T1–T22 → review APPROVED
  (`progress/review_validacion_config_asesores.md`).
- **Decisiones del humano (2026-10-31):** S1 la posición se cuenta desde 1 sobre
  todos los trozos, incluidos los vacíos; S2 solo `-?[0-9]+` es entero (se
  rechazan `+5`, `1_000`, `1.0`, `1e3`, dígitos no ASCII); S3 duplicado por
  valor entero (`7` = `007`); S4 el mensaje de duplicado da las posiciones sin
  el id; S5 `hide_input_in_errors=True` en `Settings`; S6 `advisors_configured`
  a INFO y `no_advisors_configured` a WARNING; S7 solo se informa del primer
  error. Ids negativos siguen válidos.
- **Cambio sobre la #7:** R23 modificada (autorizado por el humano): las
  entradas vacías se siguen descartando, pero una no numérica o un id repetido
  hacen fallar `Settings()` y handover no arranca. Nota añadida en
  `specs/traspaso_asesor/requirements.md` §R23; el test
  `test_advisor_ids_discards_blank_and_non_numeric` se ajustó sin quitar
  aserciones.
- **Cambios:** `services/handover/handover/config.py` (validación de
  `ADVISOR_CHAT_IDS`), `handover/main.py` (log de arranque con el número de
  asesores, sin ids), `tests/test_config.py` y `tests/test_startup.py`.
  Informe: `progress/impl_validacion_config_asesores.md`.
- **Writer verificado:** `deepseek/deepseek-flash` (OpenCode 1.19.0; solo ese
  proveedor y modelo en la sesión).
- **Resultado:** `./init.sh` verde, 766 tests pasan (antes 742; +24).

## 2026-10-31 — Feature #17 contrato_cierre_casos_huerfanos (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek Flash como writer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec (`specs/contrato_cierre_casos_huerfanos/`) revisado
  (`progress/specreview_contrato_cierre_casos_huerfanos.md`) → `in_progress` con
  `auto_approved: true` → OpenCode T2–T13 (T1, T14–T17 el puente) → review
  APPROVED (`progress/review_contrato_cierre_casos_huerfanos.md`).
- **Cambios:** única línea publicada editada: la fila S12 de
  `contracts/CONTRATOS.md` (excepción cerrada H1, solo tres inserciones, nada
  borrado). Define caso huérfano (`assigned` cuyo `advisor_id` es nulo o ya no
  está en `ADVISOR_CHAT_IDS`): lo cierra cualquier asesor registrado (`close` y
  `authorize(close)` → `200 allowed=true`, sin reasignar), pero `reply`,
  `authorize(reply)` y `assign` siguen dando `403 forbidden`; el cuarto escalón
  de la precedencia no aplica a `close`/`authorize(close)` sobre un huérfano;
  procedimiento de retirada (el asesor cierra sus casos antes; handover
  registrará al arrancar cuántos huérfanos hay, sin ids, lo implementa la #14).
  11 tests nuevos al final de `contracts/tests/test_contratos_doc.py`, sin borrar
  ni debilitar ninguno. Informe: `progress/impl_contrato_cierre_casos_huerfanos.md`.
- **Regla del `advisor_id` nulo:** decidida por el humano (2026-10-31): un
  `assigned` con `advisor_id` nulo es huérfano (R1).
- **Dudas abiertas (design §7):** reenvío de mensajes del cliente a un asesor
  retirado (Ley 1581, S13/#15); momento en que un asesor deja de estar en la
  lista (tras reiniciar handover); `closed_by` al cerrar un huérfano (lo
  confirma la #14); detalles del recuento al arrancar (#14); aviso al cliente o
  al asesor que cierra (A12 de la #16); caso `assigned` de un asesor activo que
  nunca lo cierra (opción F).
- **Writer verificado:** `deepseek/deepseek-flash` (`opencode export` de la
  sesión: solo ese proveedor y modelo).
- **Resultado:** `./init.sh` verde, 777 tests pasan (antes 766; +11; 385 en
  `contracts`). R1–R15 cubiertos.
- **Pendiente humano:** revisar el spec auto-aprobado y las dudas de design §7.

## 2026-11-01 — Feature #14 autorizacion_asesores (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek Flash como writer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec (`specs/autorizacion_asesores/`) revisado
  (`progress/specreview_autorizacion_asesores.md`) → `in_progress` con
  `auto_approved: true` → OpenCode → review APPROVED
  (`progress/review_autorizacion_asesores.md`).
- **Cambios:** handover implementa `POST /cases/{id}/authorize` y aplica las
  reglas de S12 a `assign` y `close` (`403 forbidden` sin modificar el caso,
  denegación registrada); el orquestador pide autorización antes de enviar
  `reply` (`403` sin envío + `advisor_forbidden`; handover caído → `502`).
  Informe: `progress/impl_autorizacion_asesores.md`.
- **Decisiones aplicadas:** solo `ADVISOR_CHAT_IDS`; C5 (`409 case_closed`
  sin evento); assign/close condicionales; `threading.Lock` en
  `PostgresCaseRepository`; huérfanos se cierran pero no se responden ni
  asignan; recuento de huérfanos en el `lifespan`.
- **Pendiente:** T7b (`test_timeout_races.py`) se aplica al implementar la #12.
- **Writer verificado:** `deepseek/deepseek-flash` (`opencode export` de la
  sesión `ses_e6a8ab727ffes1iFGtW33EjFUR`: ningún otro modelo).
- **Resultado:** `./init.sh` verde, 887 tests pasan (antes 777; +110).

## 2026-11-01 — Feature #11 registro_solicitudes_traspaso (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek como writer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec (`specs/registro_solicitudes_traspaso/`) revisado →
  `in_progress` con `auto_approved: true` → OpenCode sin ciclos de corrección
  → review APPROVED (`progress/review_registro_solicitudes_traspaso.md`).
- **Cambios:** handover guarda un registro por cada `POST /handover` (nuevo,
  reutilización, `no_advisors`, avisos fallidos y `error`) con repositorio
  falso y Postgres (SQL parametrizado, `CREATE TABLE IF NOT EXISTS`); sin
  copia de textos de mensajes. Solo `services/handover/`; contratos y
  orquestador sin cambios. Informe: `progress/impl_registro_solicitudes_traspaso.md`.
- **Resultado:** `./init.sh` verde, 912 tests pasan (antes 887; +25). R1–R21 cubiertos.
- **Pendiente humano:** revisar el spec auto-aprobado y los supuestos S1–S4,
  S6 y Retención del design marcados «REVISAR»; abrir una feature de
  retención y borrado de registros antes de producción.

## 2026-11-01 — Feature #12 vencimiento_automatico (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek como writer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec (`specs/vencimiento_automatico/`) auto-aprobado en la quinta
  vuelta (`progress/specreview_vencimiento_automatico.md`) → `in_progress` con
  `auto_approved: true` → OpenCode → review APPROVED
  (`progress/review_vencimiento_automatico.md`).
- **Cambios:** `scripts/vencer_casos.py` (llamada única o bucle con
  `--intervalo`, sin registrar `SERVICE_TOKEN`); servicio `timeouts_worker` en
  `docker-compose.yml` sin puertos; variables `CHECK_TIMEOUTS_INTERVAL_SECONDS`
  y `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` en `.env.example`; en handover,
  reclamación condicional del vencimiento (`timeout_claimed_at`, `ALTER TABLE
  ... ADD COLUMN IF NOT EXISTS`), `UPDATE` condicionales para `timed_out` y
  reutilización, sin dobles envíos de `HANDOVER_TIMEOUT_REPLY`. Informe:
  `progress/impl_vencimiento_automatico.md`.
- **T7b de la #14:** aplicada (`test_timeout_races.py` usa la firma con
  `env.settings`); marcada `[x]` en `specs/autorizacion_asesores/tasks.md`.
- **Resultado:** `./init.sh` verde, 965 tests pasan (antes 912; +53). R1–R30 cubiertos.
- **Pendiente humano:** revisar el spec auto-aprobado; decidir D3
  (`CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`), D4 (caducidad de la reclamación
  = `HANDOVER_TIMEOUT_SECONDS`), D5 (`restart: unless-stopped`, sin reintento
  rápido) y D6: despliegue en Render sigue PENDIENTE (Cron Job, worker o
  GitHub Actions `schedule`; no se desplegó nada). Observaciones no
  bloqueantes del review: `_parse_positive` acepta `nan`/`inf`; otra excepción
  del gateway distinta de `ServiceUnavailable` deja la reclamación hasta que
  caduque.

## 2026-11-01 — Feature #15 contrato_conversacion_caso (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer
  (puente) con OpenCode/DeepSeek como writer.
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec (`specs/contrato_conversacion_caso/`) auto-aprobado →
  `in_progress` con `auto_approved: true` → OpenCode → review APPROVED
  (`progress/review_contrato_conversacion_caso.md`).
- **Cambios:** solo `contracts/`. `CaseClientMessageRequest` y
  `CaseClientMessageResponse` (`status: forwarded | not_assigned`) en
  `lazaro_contracts/cases.py`, exportados en `__all__`; 3 ejemplos JSON
  nuevos; sección `### POST /cases/{id}/client-message` en `CONTRATOS.md`
  (expone `handover`, llama `orchestrator`; errores 401/422/404/502/500);
  línea `- **Llama:**` de `POST /cases/{id}/close` ampliada con
  `orchestrator`; supuesto `S13`. `POST /messages` y `## Reglas comunes`
  intactos. Informe: `progress/impl_contrato_conversacion_caso.md`.
- **Resultado:** `./init.sh` verde, 1014 tests pasan; `contracts` 434
  (antes 385; +49). R1–R39 cubiertos.
- **Pendiente humano:** revisar el spec auto-aprobado; la #16 sigue
  bloqueada hasta alinear su spec con C5 de la #13.

## 2026-11-01 — Feature #18 candado_repositorio_orquestador (done)
- **Agente:** leader (modo nocturno) + spec_author, reviewer, implementer (puente a OpenCode/DeepSeek).
- **Modo:** nocturno (spec auto-aprobado por reviewer, pendiente de revisión humana)
- **Flujo:** spec SPEC_APPROVED (`progress/specreview_candado_repositorio_orquestador.md`) →
  `in_progress` con `auto_approved: true` → primer intento bloqueado (OpenCode colgado al
  arrancar, probable `opencode.exe` huérfano) → relanzado, OpenCode completó T1–T5 →
  review APPROVED (`progress/review_candado_repositorio_orquestador.md`); T6 marcada al cerrar.
- **Cambios:** `services/orchestrator/orchestrator/adapters/repository.py` (`import threading`,
  `self._lock`, `with self._lock:` en `_run`; SQL, firmas y `_SCHEMA` sin tocar) y nuevo
  `services/orchestrator/tests/test_repository_lock.py`. Informe:
  `progress/impl_candado_repositorio_orquestador.md`. Se eliminó
  `progress/blocked_candado_repositorio_orquestador.md` (bloqueo resuelto).
- **Resultado:** `./init.sh` verde, 1017 tests pasan. R1–R7 cubiertos; ningún test eliminado
  ni debilitado.
- **Pendiente humano:** revisar el spec auto-aprobado; la #16 sigue bloqueada hasta alinear
  su spec con C5 (ya no depende de la #18).

## 2026-11-01 — Feature #16 conversacion_cliente_asesor (done)
- Implementación completada por OpenCode/DeepSeek Flash; tests T0 y T69 verificados con `./init.sh`.
- Reviewer: APPROVED (`progress/review_conversacion_cliente_asesor.md`).
- Resultado: 1185 tests pasan; feature #16 marcada `done`.

## 2026-11-01 — Feature #19 edicion_fragmentos (done)
- API `PATCH /chunks/{id}` para editar texto con embedding recalculado y metadatos preservados.
- Writer: OpenCode / DeepSeek Flash. Reviewer: APPROVED (`progress/review_edicion_fragmentos.md`).
- `./init.sh`: 1232 tests pasan. Spec aprobado automáticamente en modo nocturno; pendiente de revisión humana.

## 2026-11-01 — Feature #20 verificacion_cuentas (done)
- Perfiles internos con roles, contraseñas PBKDF2 y vínculo Telegram por token aleatorio de un solo uso y expiración.
- Writer: OpenCode / DeepSeek Flash. Reviewer: APPROVED (`progress/review_verificacion_cuentas.md`).
- `./init.sh`: 1268 tests pasan. Spec auto-aprobado en modo nocturno; pendiente de revisión humana.


## 2026-11-01 — Feature #21 panel_administracion (done)
- Panel administrativo del orquestador con login de administrador, sesiones/CSRF, alta y gestión de perfiles, enlaces de vinculación Telegram, eventos recientes redactados y limitación persistente de intentos.
- Writer: OpenCode / DeepSeek Flash. Reviewer: APPROVED (`progress/review_panel_administracion.md`).
- Revisión corrigió el tiempo del login para que usuario inexistente, contraseña incorrecta y rol no administrador hagan un PBKDF2; prueba nueva lo verifica.
- `./init.sh`: 1310 tests pasan. Docker: orquestador reconstruido; servicios del proyecto levantados y PostgreSQL healthy.


## 2026-11-01 — Feature #22 panel_fragmentos (done)
- El panel permite cargar manuales, listar sus fragmentos, editar texto y activar/desactivar fragmentos. Se añadieron 3 rutas al contrato del RAG y modelos/ejemplos.
- Writer: OpenCode / DeepSeek Flash. Reviewer: APPROVED (`progress/review_panel_fragmentos.md`).
- `./init.sh`: 1398 tests pasan. Docker reconstruido para RAG y orquestador; los cuatro `/health` y `/admin/login` responden HTTP 200; PostgreSQL healthy.


## 2026-11-01 — Feature #23 bootstrap_administrador (done)
- Comando local `python -m orchestrator.bootstrap_admin --username <nombre>` crea el primer admin con contraseña oculta, PBKDF2 y sin endpoint público ni credenciales por defecto.
- Claude reviewer: APPROVED (`progress/review_bootstrap_administrador.md`). `./init.sh`: 1416 tests pasan.

## 2026-11-01 — Feature #24 despliegue_produccion (done)
- Preparación Render: Blueprint, secretos/configuración de producción, webhook Telegram, build Docker en CI y procedimiento de despliegue; no se crearon recursos ni se desplegó.
- Writer: OpenCode / DeepSeek Flash; Claude revisó y aprobó (`progress/review_despliegue_produccion.md`).
- `./init.sh`: 1561 tests pasan. Se corrigió validación de Settings snake_case y los tests de variables ausentes.

## 2026-11-01 — Feature #25 clasificador_consultas (done)
- Panel para categorías/keywords y umbral; clasificador local determinista registra puntuación/confianza y deja intactos RAG, respuestas y permisos.
- Spec redactado por Claude; revisión enfocada Codex `SPEC_APPROVED`; código writer OpenCode/DeepSeek Flash; revisión Codex `APPROVED` (`progress/review_clasificador_consultas.md`).
- `./init.sh`: 1658 tests pasan.

## 2026-11-01 — Feature #26 consulta_bd_lenguaje_natural (done)
- `/consultar` solo en chat privado para asesor con perfil Telegram vinculado; SQL restringido a vistas/columnas allowlisted y conexión PostgreSQL read-only con timeout, límite de filas y rollback. Auditoría guarda hash, estado, vistas y conteo.
- `DB_QUERY_ENABLED=false` por defecto. Habilitarla requiere que el dueño acepte compartir el esquema estático permitido con el proveedor, configure vistas y DSN de rol read-only.
- Spec y revisiones de seguridad: Claude APPROVED (`progress/specreview_consulta_bd_lenguaje_natural.md`, `progress/review_consulta_bd_lenguaje_natural.md`). Writer OpenCode/DeepSeek Flash.
- `./init.sh`: 1777 tests pasan; hardening final de cierre de conexión y parser ASCII revisado por Claude.


## 2026-11-01 — Feature #27 privacidad_y_retencion_datos (done)
- Consentimiento explícito antes de procesar mensajes de cliente; purga transaccional de casos y contactos por retención, con worker periódico en Docker Compose.
- Writer: OpenCode / DeepSeek Flash; revisión de código Claude APPROVED (`progress/review_privacidad_y_retencion_datos.md`). `./init.sh`: 1854 tests pasan (1 warning de Starlette/httpx).
- La producción sigue requiriendo valores definidos por el dueño para el aviso, versión, frase de aceptación y plazos. La revisión detectó que falta integrar el worker y las variables en Render; seguimiento #28.


## 2026-11-01 — Feature #28 despliegue_retencion (done)
- Añadido `retention-worker` privado en Render, configuración `PRIVACY_*` con fuente única del plazo, y documentación de despliegue/bloqueos del dueño.
- Spec y revisión de código Claude APPROVED (`progress/specreview_despliegue_retencion.md`, `progress/review_despliegue_retencion.md`); writer OpenCode / DeepSeek Flash. `./init.sh`: 1877 tests pasan (1 warning).
- No se desplegó; queda validar `envVarKey` al crear el Blueprint y completar los valores legales/operativos del dueño antes de producción.
