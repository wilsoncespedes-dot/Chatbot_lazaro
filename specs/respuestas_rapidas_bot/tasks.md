# Tasks — #71 respuestas_rapidas_bot

- [x] T1 — Añadir `QuickReply`, `QuickReplyImage` y los errores `QuickReplyInvalid`, `QuickReplyImageInvalid`, `QuickReplyNotFound` en `domain.py`. Cubre: R1, R5.
- [x] T2 — Crear `quick_replies.py` puro: `parse_triggers`, `pick_reply` (palabras completas, prioridad, desempate, ignora inactivas). Cubre: R6, R13, R14, R15, R16.
- [x] T3 — Añadir a `quick_replies.py` `validate_image` (firma PNG/JPEG/WebP, tamaño, vacío) y `build_blocks` (imagen/enlace/texto degradado, omisión sin URL). Cubre: R24, R25, R32, R33, R34, R35.
- [x] T4 — Añadir `supports_images` a `ChannelPolicy`/`policy_from_info`/`default_policy` en `channels.py`. Cubre: R32, R33.
- [x] T5 — Añadir `quick_reply_image_max_bytes` en `config.py` y `QUICK_REPLY_IMAGE_MAX_BYTES` en `.env.example`. Cubre: R24, R25.
- [x] T6 — Repositorio: protocolo, `FakeRepository` y `PostgresRepository` con tablas `quick_replies` y `quick_reply_images` (sin inserts de contenido) y los 8 métodos. Cubre: R1, R31, R36.
- [x] T7 — CRUD en `domain.py` (`create/update/set_active/list`) con validación de enlace https, prioridad, URL de imagen, exclusión archivo+URL, base pública, reemplazo y borrado de imagen. Cubre: R2, R3, R4, R5, R7, R8, R28, R29, R30, R31.
- [x] T8 — Crear `quick_replies_routes.py` con páginas `/admin/respuestas-rapidas` (admin, CSRF, auditoría, sesión) y `GET /media/respuestas/{id}`; registrarlo en `main.py`. Cubre: R2, R3, R4, R9, R10, R11, R12, R26, R27.
- [x] T9 — `render_quick_replies` y enlace de menú en `admin.py` (formulario multipart sin JS). Cubre: R2, R3, R4.
- [x] T10 — `_send_blocks` y `_try_quick_reply` en `domain.py`; enganchar en `_resolve_and_run` tras la intención de compra por frase y antes del router, solo en `active`, con evento `quick_reply`, historial, `_create_case_after_intent` y tolerancia a fallos. Cubre: R17, R18, R19, R20, R21, R22, R23.
- [x] T11 — Nota de `GET /media/respuestas/{id}` en `contracts/CONTRATOS.md` (y su test de documentación si existe). Cubre: R26.
- [x] T12 — Tests puros `services/orchestrator/tests/test_quick_replies_pure.py`: coincidencia, palabras completas, prioridad y empate, inactivas, `validate_image`, `build_blocks`, degradación. Cubre: R13, R14, R15, R16, R24, R25, R32, R33, R34, R35.
- [x] T13 — Tests de administración `test_quick_replies_admin.py`: alta/edición/activación, validaciones 422, permisos 403 por rol, sin sesión, CSRF, auditoría, subida válida/ inválida, archivo+URL, sin base pública, reemplazo borra imagen, media `200` con nosniff y `404`. Cubre: R1–R12, R24–R31.
- [x] T14 — Tests de flujo `test_quick_replies_flow.py`: coincidencia en `active` sin llamar al LLM/RAG (fakes que fallan), evento y historial, estados excluidos (consentimiento, asesor, login, no_access), prioridad de supresión/traspaso, degradación por capacidades del directorio, intención de compra + caso, fallo del repositorio continúa al RAG. Cubre: R17–R23, R32, R33.
- [x] T15 — Test de esquema `test_quick_replies_schema.py`: las tablas existen en el DDL y `FakeRepository` arranca vacío, sin datos sembrados en el código. Cubre: R1, R36.
- [ ] T16 — `./init.sh` verde e informe `progress/impl_respuestas_rapidas_bot.md` con el mapa de trazabilidad R<n> ↔ test. Cubre: R1–R36.
