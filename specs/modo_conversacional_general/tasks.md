# Tasks — modo_conversacional_general

- [x] T1 — Añadir `CONVERSATIONAL_MODE_ENABLED` y `CONVERSATIONAL_BUSINESS_TERMS` con defaults configurables; documentarlos en `.env.example`. Cubre: R1, R6.
- [x] T2 — Crear prompt conversacional, contrato JSON estricto y parser `general` / `manual_required`. Cubre: R1, R3, R5.
- [x] T3 — Añadir guarda determinista que bloquee respuestas `general` cuando el mensaje contiene un término de negocio configurado. Cubre: R6.
- [x] T4 — Integrar el fallback solo tras búsqueda RAG exitosa sin fragmentos; conservar rechazo, métrica de no-hit y handover para negocio, clasificación manual e inválidos; no invocar el LLM si el guardia detecta inyección. Cubre: R2-R5, R9-R10, R15.
- [x] T5 — Reutilizar `_memory_context`, `_send` y el repositorio/outbox actuales; guardar el texto completo en historial. Cubre: R7-R8, R11-R12.
- [x] T6 — Añadir tests de prompt, parser, respuestas general/manual, keyword guard, memoria habilitada/deshabilitada, RAG no disponible, historial completo, outbox e inyección. Cubre: R1-R12, R15.
- [x] T7 — Añadir `test_conversation_reuses_existing_schema_and_outbox` (R13) y `test_conversation_mode_does_not_add_a_service` (R14) como checks estructurales explícitos. Cubre: R13-R14.
- [x] T8 — Añadir trazabilidad R1-R15 y ejecutar la verificación: `python -m compileall` pasó; `./init.sh` falló antes de pytest por WSL/CRLF y el Python disponible no tiene pytest. Cubre: R1-R15.
- [x] T9 — Revisión estática aprobada; por instrucción del usuario, marcar `done` dejando constancia de que pytest no se ejecutó (el entorno aún requiere configurar `venv` y corregir CRLF). Cubre: R1-R15.
