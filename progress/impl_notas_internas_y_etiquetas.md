# Implementación — #50 notas_internas_y_etiquetas

Estado: T1–T18 completadas; revisión de código aprobada.

## Resumen

- Añade `case_notes`, `case_tags` y `case_tag_assignments` en el orchestrator,
  con aislamiento de notas y borrado en supresión, retención y rechazo de
  privacidad.
- Añade rutas de notas y etiquetas para asesores, filtro por etiqueta y
  administración de etiquetas con sesión, CSRF y auditoría.
- Variables `CASE_*` en `config.py`, `.env.example` y `render.yaml`.
- Revisión detectó falta de auditoría en errores CSRF; DeepSeek la corrigió en
  las siete rutas y añadió pruebas. Ver `progress/review_notas_internas_y_etiquetas.md`.

## Trazabilidad

- R1 → `tests/test_notes.py::test_add_note_redirects_and_audits_without_text`
- R2 → `tests/test_notes.py::test_case_view_shows_notes_separate_from_history`
- R3, R4 → `tests/test_notes.py::test_view_and_add_require_permission_without_reading_or_writing`
- R5 → `tests/test_annotations_pure.py` y `tests/test_notes.py::test_note_validation_rejects_empty_and_too_long`
- R6 → `tests/test_notes.py::test_note_per_case_limit`
- R7 → `tests/test_notes.py::test_author_deletes_own_note_and_audits`
- R8 → `tests/test_notes.py::test_other_author_cannot_delete_note`
- R9 → `tests/test_notes.py::test_missing_note_or_note_from_another_case_returns_404`
- R10, R11 → `tests/test_notes_isolation.py::test_note_never_reaches_channel_history_or_events`
- R12 → `tests/test_notes_isolation.py::test_note_is_not_in_llm_prompt_or_memory_or_summary`
- R13 → `tests/test_notes_isolation.py::test_note_is_not_in_advisor_reply_text_or_whatsapp_template`
- R14–R16 → `tests/test_tags.py::test_admin_creates_renames_and_toggles_preserving_assignments`
- R17 → `tests/test_annotations_pure.py` y `tests/test_tags.py::test_invalid_tag_names_are_rejected`
- R18 → `tests/test_annotations_pure.py` y `tests/test_tags.py::test_duplicate_tag_name_is_case_insensitive`
- R19 → `tests/test_tags.py::test_non_admin_cannot_manage_tags`
- R20, R21 → `tests/test_tags.py::test_assign_is_idempotent_and_remove_works`
- R22 → `tests/test_tags.py::test_disabled_or_missing_tag_cannot_be_assigned`
- R23 → `tests/test_tags.py::test_case_tag_limit`
- R24 → `tests/test_tags.py::test_assign_and_remove_require_case_permission`
- R25 → `tests/test_tags.py::test_case_view_lists_assigned_and_assignable_tags`
- R26, R27 → `tests/test_tags.py::test_tag_filter_combines_with_channel_and_assignment`
- R28 → `tests/test_tags.py::test_inbox_rows_show_only_active_tag_names`
- R29 → `tests/test_notes.py::test_note_text_and_author_are_escaped` y `tests/test_tags.py::test_tag_names_are_escaped`
- R30, R31 → `tests/test_notes.py::test_notes_require_session_and_csrf` y `tests/test_tags.py::test_tag_routes_require_session_and_csrf`
- R32 → `tests/test_notes.py::test_add_note_redirects_and_audits_without_text` y `test_author_deletes_own_note_and_audits`
- R33 → `tests/test_tags.py::test_admin_creates_renames_and_toggles_preserving_assignments` y `test_assign_is_idempotent_and_remove_works`
- R34 → `tests/test_notes.py::test_validation_failure_is_audited` y las tres pruebas `test_csrf_failure_*_is_audited_without_changes` de `test_notes.py`/`test_tags.py`
- R35, R36 → `tests/test_notes_privacy.py::test_suppression_deletes_notes_and_assignments_of_client_contacts`
- R37 → `tests/test_notes_privacy.py::test_retention_purge_deletes_old_and_inactive_notes`
- R38 → `tests/test_notes_privacy.py::test_rejected_privacy_notice_deletes_notes_and_assignments`
- R39 → `tests/test_repository_schema.py::test_schema_declares_case_notes_and_tags`
- R40 → `tests/test_config.py::test_case_annotation_settings_defaults_and_env_example` y `test_case_annotation_settings_reject_out_of_range`

## Verificación

`bash ./init.sh`: exit 0, 3274 passed, 1 skipped y 2 avisos de deprecación.
