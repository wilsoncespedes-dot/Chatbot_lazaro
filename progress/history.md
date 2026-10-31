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
