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
