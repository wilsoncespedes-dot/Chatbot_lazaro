# #51 respuestas_guardadas — Tasks

Rutas relativas a `services/orchestrator/` salvo indicación.

- [x] T1 — Añadir `SAVED_REPLY_TITLE_MAX_CHARS`, `SAVED_REPLY_TEXT_MAX_CHARS`, `SAVED_REPLIES_MAX` a `orchestrator/config.py` con rangos, `.env.example` y `render.yaml`. Cubre: R23.
- [x] T2 — Añadir `validate_saved_reply_title` y `validate_saved_reply_text` en `orchestrator/annotations.py` y `tests/test_saved_replies_pure.py`. Cubre: R8, R9.
- [x] T3 — Añadir `SavedReply`, `SavedReplyNotFound` y `SavedReplyVariablesNotAllowed` en `domain.py`. Cubre: R9, R11.
- [x] T4 — Extender Protocol, `FakeRepository` y `PostgresRepository` con la tabla `saved_replies` (idempotente) y métodos `add/update/set_active/get/list/count`; sin tocar supresión ni purga. Cubre: R24.
- [x] T5 — Implementar `create_saved_reply`, `update_saved_reply`, `set_saved_reply_active`, `list_saved_replies` en `domain.py` con validación y tope. Cubre: R1, R2, R3, R4, R8, R9, R10, R11.
- [x] T6 — Añadir `GET/POST /admin/respuestas…`, `render_saved_replies` y enlace en la navegación admin, con sesión admin, CSRF y auditoría (`saved_reply_created`, `saved_reply_updated`, `saved_reply_active_changed`) sin texto. Cubre: R1, R2, R3, R5, R6, R7, R12, R21.
- [x] T7 — Extender `CaseView` y `advisor_case_view` con `saved_replies`, `selected_reply` y `reply_notice`; sin respuestas con ventana WhatsApp cerrada. Cubre: R13, R14, R17, R18, R20.
- [x] T8 — Leer `respuesta` en `case_page` (`advisor_routes.py`) y renderizar selector GET y `textarea` prellenado escapado en `advisor_panel.py`; añadir mensajes de error. Cubre: R13, R14, R15, R17, R18, R21, R22.
- [x] T9 — Tests `tests/test_saved_replies.py`: CRUD admin, no-admin, sin sesión, sin CSRF, validación, variables, tope, 404, auditoría sin texto, aplicación inmediata, escape. Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R21.
- [x] T10 — Tests `tests/test_saved_replies_advisor.py`: selector solo con activas, carga en textarea, nada enviado al cargar (`FakeGateway` vacío), edición antes de enviar, respuesta inactiva/inexistente, ventana WhatsApp cerrada con `?respuesta=` forzado, autorización por caso, sin interpolación. Cubre: R13, R14, R15, R16, R17, R18, R19, R20, R22.
- [x] T11 — Actualizar `tests/test_config.py` (variables y rangos inválidos, rutas nuevas en el test de superficie) y `tests/test_repository_schema.py` (tabla idempotente, ausente de supresión/purga). Cubre: R23, R24.
- [x] T12 — Ejecutar `./init.sh` y documentar la trazabilidad R<n> ↔ test en `progress/impl_respuestas_guardadas.md`. Cubre: R1–R24.
