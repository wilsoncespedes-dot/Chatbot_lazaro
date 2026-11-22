# Implementación #77 `importacion_clientes`

## Resumen

Importación CSV en dos pasos (vista previa y confirmación) sobre
`/admin/clientes`, con la lógica en `orchestrator/client_import.py`. El archivo
se lee en memoria, nunca se persiste; la vista previa y el resumen viven en un
`ImportStaging` con TTL y ligado a la sesión admin. Las escrituras pasan por el
puerto `FuenteDeClientes`; los clientes importados nacen con credencial
inactiva (hash no verificable y vigencia vencida). Se añadieron `email`,
`phone` y `contact_updated_at` al perfil con migración idempotente, y la
supresión/purga los limpia.

Archivos principales: `orchestrator/client_import.py` (nuevo),
`client_source.py`, `adapters/repository.py`, `domain.py`, `admin_routes.py`,
`admin.py`, `config.py`, `.env.example`, `docs/architecture.md` y
`tests/test_client_import.py` (nuevo).

## Trazabilidad

- R1 → `services/orchestrator/tests/test_client_import.py::test_import_link_visible_for_admin`
- R2 → `services/orchestrator/tests/test_client_import.py::test_non_admin_forbidden`
- R3 → `services/orchestrator/tests/test_client_import.py::test_missing_csrf_403_audited`
- R4 → `services/orchestrator/tests/test_client_import.py::test_parse_comma_and_semicolon`, `::test_bom_and_non_utf8`
- R5 → `services/orchestrator/tests/test_client_import.py::test_parse_comma_and_semicolon`
- R6 → `services/orchestrator/tests/test_client_import.py::test_bom_and_non_utf8`
- R7 → `services/orchestrator/tests/test_client_import.py::test_header_rejects_unknown_and_password_columns`
- R8 → `services/orchestrator/tests/test_client_import.py::test_size_and_rows_limits`
- R9 → `services/orchestrator/tests/test_client_import.py::test_size_and_rows_limits`
- R10 → `services/orchestrator/tests/test_client_import.py::test_file_not_persisted`
- R11 → `services/orchestrator/tests/test_client_import.py::test_header_rejects_unknown_and_password_columns`
- R12 → `services/orchestrator/tests/test_client_import.py::test_preview_lists_all_errors_per_row`
- R13 → `services/orchestrator/tests/test_client_import.py::test_invalid_usuario_id_correo_telefono_per_field`
- R14 → `services/orchestrator/tests/test_client_import.py::test_invalid_usuario_id_correo_telefono_per_field`
- R15 → `services/orchestrator/tests/test_client_import.py::test_invalid_usuario_id_correo_telefono_per_field`
- R16 → `services/orchestrator/tests/test_client_import.py::test_invalid_usuario_id_correo_telefono_per_field`
- R17 → `services/orchestrator/tests/test_client_import.py::test_preview_lists_all_errors_per_row`
- R18 → `services/orchestrator/tests/test_client_import.py::test_normalization`
- R19 → `services/orchestrator/tests/test_client_import.py::test_duplicate_by_id_email_phone_in_base`
- R20 → `services/orchestrator/tests/test_client_import.py::test_duplicate_by_id_email_phone_in_base`
- R21 → `services/orchestrator/tests/test_client_import.py::test_duplicate_by_id_email_phone_in_base`
- R22 → `services/orchestrator/tests/test_client_import.py::test_duplicate_in_file`
- R23 → `services/orchestrator/tests/test_client_import.py::test_conflict_two_existing_clients`
- R24 → `services/orchestrator/tests/test_client_import.py::test_policy_default_is_skip`
- R25 → `services/orchestrator/tests/test_client_import.py::test_import_creates_clients`
- R26 → `services/orchestrator/tests/test_client_import.py::test_update_policy_updates_only_contact`
- R27 → `services/orchestrator/tests/test_client_import.py::test_skip_policy_keeps_existing`
- R28 → `services/orchestrator/tests/test_client_import.py::test_file_duplicate_always_skipped`
- R29 → `services/orchestrator/tests/test_client_import.py::test_failed_rows_reported_and_import_continues`, `::test_username_taken_by_other_client_fails`
- R30 → `services/orchestrator/tests/test_client_import.py::test_summary_counts_and_reasons`
- R31 → `services/orchestrator/tests/test_client_import.py::test_failed_rows_reported_and_import_continues`
- R32 → `services/orchestrator/tests/test_client_import.py::test_expired_or_foreign_token_409`
- R33 → `services/orchestrator/tests/test_client_import.py::test_preview_expires_after_ttl`, `::test_staging_single_use`
- R34 → `services/orchestrator/tests/test_client_import.py::test_csv_export_escapes_formulas`
- R35 → `services/orchestrator/tests/test_client_import.py::test_summary_and_audit_have_no_pii`
- R36 → `services/orchestrator/tests/test_client_import.py::test_import_goes_through_client_source`
- R37 → `services/orchestrator/tests/test_client_import.py::test_imported_client_has_inactive_credential_and_cannot_login`
- R38 → `services/orchestrator/tests/test_client_import.py::test_imported_client_has_inactive_credential_and_cannot_login`
- R39 → `services/orchestrator/tests/test_client_import.py::test_schema_statements_idempotent`
- R40 → `services/orchestrator/tests/test_client_import.py::test_suppression_clears_email_phone`
- R41 → `services/orchestrator/tests/test_client_import.py::test_retention_purge_clears_email_phone`
- R42 → `services/orchestrator/tests/test_client_import.py::test_policy_default_is_skip`, `::test_summary_and_audit_have_no_pii`, `::test_missing_csrf_403_audited`

## Verificación

`./init.sh` queda pendiente de que Claude lo ejecute al cerrar la sesión (el
implementer no ejecuta shell). No se modificaron `feature_list.json`,
`progress/current.md`, `progress/history.md` ni el harness.

## Resultado de init.sh

`./init.sh`: 4760 passed, 1 skipped. Todos los tests pasan. Trazabilidad R1..R42 -> test confirmada arriba.
