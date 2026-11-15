# #50 notas_internas_y_etiquetas — Tasks

Rutas relativas a `services/orchestrator/` salvo indicación.

- [x] T1 — Añadir variables `CASE_NOTE_MAX_CHARS`, `CASE_NOTES_MAX_PER_CASE`, `CASE_TAG_NAME_MAX_CHARS`, `CASE_TAGS_MAX_PER_CASE` a `orchestrator/config.py` con rangos, y a `.env.example` y `render.yaml`. Cubre: R40.
- [x] T2 — Crear `orchestrator/annotations.py` con `validate_note_text`, `validate_tag_name`, `normalize_tag_key` y `tests/test_annotations_pure.py`. Cubre: R5, R17, R18.
- [x] T3 — Añadir dataclasses `CaseNote`, `CaseTag` y excepciones `TagNameTaken`, `TagNotFound`, `NoteNotFound` en `domain.py`. Cubre: R9, R18, R22.
- [x] T4 — Extender Protocol, `FakeRepository` y `PostgresRepository` con tablas/índices (`case_notes`, `case_tags`, `case_tag_assignments`) y los métodos de notas y etiquetas, incluido `case_tag_map`. Cubre: R10, R39.
- [x] T5 — Implementar `_authorize_case_annotation`, `add_case_note` y `delete_case_note` en `domain.py` sin tocar gateway, `messages` ni `events`. Cubre: R1, R3, R4, R5, R6, R7, R8, R9, R11, R13.
- [x] T6 — Implementar `create_case_tag`, `rename_case_tag`, `set_case_tag_active`, `list_case_tags`, `assign_case_tag`, `remove_case_tag`. Cubre: R14, R15, R16, R17, R18, R20, R21, R22, R23, R24.
- [x] T7 — Extender `CaseView`, `InboxRow`, `advisor_case_view`, `advisor_inbox` y `advisor_all_cases` con notas, etiquetas y filtro `tag` validado antes de `list_cases`. Cubre: R2, R4, R25, R26, R27, R28.
- [x] T8 — Añadir rutas `POST /asesor/cases/{id}/notes`, `/notes/{note_id}/delete`, `/tags`, `/tags/{tag_id}/remove` y parámetro `tag` en `GET /asesor/cases` y `/asesor/todos`, con sesión, CSRF y auditoría (`note_added`, `note_deleted`, `tag_assigned`, `tag_removed`, resultado con código de error). Cubre: R1, R7, R20, R21, R26, R27, R30, R31, R32, R33, R34.
- [x] T9 — Renderizar en `advisor_panel.py` sección de notas (separada del historial, autor y fecha), sección de etiquetas, columna de etiquetas y selector de filtro con `_esc`; añadir mensajes de error nuevos. Cubre: R2, R25, R28, R29.
- [x] T10 — Añadir `GET/POST /admin/etiquetas…`, `render_tags` y enlace en la navegación admin, con auditoría (`tag_created`, `tag_renamed`, `tag_active_changed`) y rechazo de no-admin. Cubre: R14, R15, R16, R17, R18, R19, R29, R30, R31, R33, R34.
- [x] T11 — Borrar notas y asignaciones en `execute_suppression` (Fake y Postgres, misma transacción, conteo `case_notes`), `purge_personal_data` (conteo `case_notes`) y `delete_contact_content`. Cubre: R35, R36, R37, R38.
- [x] T12 — Tests `tests/test_notes.py`: crear/mostrar/borrar nota, permisos por caso, aislamiento entre asesores, longitudes y tope, autor, nota ajena/inexistente, escape, sin sesión, sin CSRF, auditoría sin texto. Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R29, R30, R31, R32, R34.
- [x] T13 — Tests `tests/test_notes_isolation.py`: con una nota centinela, `FakeGateway` no recibe envíos, `messages`/`events`/`case_messages` no la contienen, y un turno de IA, un resumen y la memoria capturados con fakes no la incluyen; respuesta del asesor (texto y plantilla) tampoco. Cubre: R10, R11, R12, R13.
- [x] T14 — Tests `tests/test_tags.py`: CRUD admin, nombre duplicado, longitud, no-admin, asignar/quitar, idempotencia, etiqueta desactivada, tope, permisos por caso, filtro por etiqueta combinado con canal y asignación, tag inválido, vista del caso, auditoría. Cubre: R14, R15, R16, R17, R18, R19, R20, R21, R22, R23, R24, R25, R26, R27, R28, R33, R34.
- [x] T15 — Tests `tests/test_notes_privacy.py`: supresión borra notas y asignaciones de los contactos del cliente y conserva las de otros clientes y las etiquetas; purga por corte e inactividad; rechazo de privacidad. Cubre: R35, R36, R37, R38.
- [x] T16 — Actualizar `tests/test_config.py` (variables, rangos inválidos, rutas nuevas en el test de superficie) y `tests/test_repository_schema.py` (tablas idempotentes). Cubre: R39, R40.
- [x] T17 — Añadir línea en `docs/architecture.md` sobre notas/etiquetas en tablas propias. Cubre: R10.
- [x] T18 — Ejecutar `./init.sh` y documentar la trazabilidad R<n> ↔ test en `progress/impl_notas_internas_y_etiquetas.md`. Cubre: R1–R40.
