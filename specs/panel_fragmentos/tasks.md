# #22 panel_fragmentos — Tasks

- [x] T1 — Añadir `ManualSummary`, `ManualListResponse`, `ChunkItem`, `ChunkListResponse` y `ChunkActiveRequest` en `lazaro_contracts`, exportarlos, crear los 4 ejemplos y las 3 secciones de `CONTRATOS.md`. Cubre: R1.
- [x] T2 — Tests de contrato: ejemplos válidos, `StrictBool`, campos extra rechazados, secciones presentes y ninguna fila publicada editada. Cubre: R1, R7.
- [x] T3 — RAG: `list_manuals`, `list_chunks` y `update_active` en Protocol, Fake y Postgres (SQL parametrizado, transacción). Cubre: R2, R3, R5, R6.
- [x] T4 — RAG: `ManualNotFound` y funciones de dominio; registrar las 3 rutas en `main.py`. Cubre: R2–R7.
- [x] T5 — RAG tests en `services/rag/tests/test_list_chunks.py`: listado y orden, fragmentos de manual inexistente, activar/desactivar conservando texto y embedding, 404, 422 y 401 en las 3 rutas. Cubre: R2–R8.
- [x] T6 — Orchestrator: métodos nuevos de `RagClient`/`HttpRagClient`/`FakeRagClient` con `X-Service-Token`, ids escapados y `RagRejected`/`ServiceUnavailable`. Tests del adaptador con `httpx` simulado (cabecera enviada, mapeo 404/415/422 y 5xx/401/cuerpo inválido). Cubre: R10, R13, R15, R17, R18.
- [x] T7 — Orchestrator: `ADMIN_MANUAL_MAX_BYTES` en `config.py` y `.env.example`; `python-multipart` en `requirements.txt`. Cubre: R11.
- [x] T8 — Orchestrator: plantillas en `admin.py` (manuales, fragmentos, error fijo, enlace en nav) y rutas en `admin_routes.py` con orden sesión → CSRF → validación → RAG. Cubre: R9–R20, R22.
- [x] T9 — Tests en `services/orchestrator/tests/test_admin_fragmentos.py`: listado, carga OK/413/422, fragmentos, edición OK/422, activar OK/422, errores 404/415/422/502 sin eco del RAG, sin sesión → 303 sin llamada, CSRF → 403 sin llamada, cabeceras de seguridad y `SERVICE_TOKEN` ausente de todas las respuestas. Cubre: R9–R22.
- [x] T10 — Ejecutar `./init.sh` y los tests de `contracts`, `rag` y `orchestrator`; documentar la trazabilidad en `progress/impl_panel_fragmentos.md`. Cubre: R1–R22.
