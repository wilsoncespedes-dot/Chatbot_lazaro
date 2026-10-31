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
