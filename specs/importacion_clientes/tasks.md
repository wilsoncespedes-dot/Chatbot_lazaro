# Tasks — #77 `importacion_clientes`

Ruta base: `services/orchestrator/`. Pruebas en `tests/test_client_import.py` salvo indicación.

- [x] T1 — Añadir `CLIENT_IMPORT_MAX_BYTES`, `CLIENT_IMPORT_MAX_ROWS`, `CLIENT_IMPORT_PREVIEW_TTL_SECONDS` en `orchestrator/config.py` y `.env.example`. Cubre: R8, R9, R33.
- [x] T2 — Añadir `email`/`phone` opcionales a `Profile` en `domain.py`. Cubre: R39.
- [x] T3 — Repositorio: sentencias de esquema (`email`, `phone`, `contact_updated_at`, índices) y métodos `find_client_id_by_email`, `find_client_id_by_phone`, `update_client_contact`, `create_client_credential(..., email, phone)` en Protocol, `InMemoryRepository` y `PostgresRepository`. Cubre: R20, R21, R26, R39.
- [x] T4 — Limpiar `email`/`phone`/`contact_updated_at` en la supresión y en `purge_personal_data(cutoff)` (ambos repositorios). Cubre: R40, R41.
- [x] T5 — Ampliar `FuenteDeClientes` y `FuenteClientesLocal` con `buscar_por_correo`, `buscar_por_telefono`, `actualizar_contacto` y `crear(..., correo, telefono)`. Cubre: R36.
- [x] T6 — Crear `orchestrator/client_import.py`: `parse_csv` (UTF-8/BOM, detección `,`/`;`, encabezados, límites, rechazo de columnas no documentadas). Cubre: R4, R5, R6, R7, R8, R9, R11.
- [x] T7 — En `client_import.py`: validación y normalización por campo (`usuario`, `id`, `correo`, `telefono`) y `FieldError`. Cubre: R13, R14, R15, R16, R17, R18.
- [x] T8 — En `client_import.py`: `build_plan` con duplicados en base (id, correo, teléfono), en archivo y `conflicto`. Cubre: R19, R20, R21, R22, R23.
- [x] T9 — En `client_import.py`: `run_import` (crear con credencial inactiva, actualizar/saltar, fallos aislados, resumen sin PII). Cubre: R25, R26, R27, R28, R29, R30, R31, R37, R38.
- [x] T10 — En `client_import.py`: `ImportStaging` (memoria, TTL, un solo uso, ligado a sesión), `csv_safe` y `summary_to_csv`. Cubre: R10, R33, R34, R35.
- [x] T11 — Rutas en `admin_routes.py` (GET formulario, POST vista previa, POST confirmar, GET resumen CSV) con sesión admin, CSRF auditado, lectura acotada del upload y auditoría `client_import_preview`/`client_import`. Cubre: R1, R2, R3, R10, R12, R24, R32, R42.
- [x] T12 — Vistas en `admin.py`: enlace «Importar clientes» en `render_clients`, `render_import_form`, `render_import_preview` (filas, errores por campo, selector de política con «Saltar» por defecto), `render_import_summary`; todo escapado. Cubre: R1, R12, R17, R24, R30.
- [x] T13 — Pruebas de parseo: `test_parse_comma_and_semicolon`, `test_bom_and_non_utf8`, `test_header_rejects_unknown_and_password_columns`, `test_size_and_rows_limits`. Cubre: R4, R5, R6, R7, R8, R9, R11.
- [x] T14 — Pruebas de validación: `test_invalid_usuario_id_correo_telefono_per_field`, `test_normalization`, `test_preview_lists_all_errors_per_row`. Cubre: R13, R14, R15, R16, R17, R18, R12.
- [x] T15 — Pruebas de duplicados: `test_duplicate_by_id_email_phone_in_base`, `test_duplicate_in_file`, `test_conflict_two_existing_clients`, `test_policy_default_is_skip`. Cubre: R19, R20, R21, R22, R23, R24.
- [x] T16 — Pruebas de ejecución: `test_import_creates_clients`, `test_update_policy_updates_only_contact`, `test_skip_policy_keeps_existing`, `test_file_duplicate_always_skipped`, `test_failed_rows_reported_and_import_continues`, `test_summary_counts_and_reasons`, `test_imported_client_has_inactive_credential_and_cannot_login`. Cubre: R25, R26, R27, R28, R29, R30, R31, R37, R38.
- [x] T17 — Pruebas de fuente y esquema: `test_import_goes_through_client_source` (fuente falsa inyectada), `test_schema_statements_idempotent`, `test_suppression_clears_email_phone`, `test_retention_purge_clears_email_phone`. Cubre: R36, R39, R40, R41.
- [x] T18 — Pruebas de seguridad y rutas: `test_non_admin_forbidden`, `test_missing_csrf_403_audited`, `test_expired_or_foreign_token_409`, `test_preview_expires_after_ttl`, `test_staging_single_use`, `test_file_not_persisted` (sin archivos nuevos ni filas con el contenido), `test_csv_export_escapes_formulas`, `test_summary_and_audit_have_no_pii`, `test_import_link_visible_for_admin`. Cubre: R1, R2, R3, R10, R32, R33, R34, R35, R42.
- [x] T19 — Documentar el formato del CSV, límites y supuestos S1-S7 en `docs/architecture.md`. Cubre: R4, R7, R8, R9.
- [ ] T20 — Ejecutar `./init.sh` verde y escribir `progress/impl_importacion_clientes.md` con el mapa de trazabilidad R→test. Cubre: todos. **Nota:** el informe ya está escrito; `./init.sh` lo ejecuta Claude al cerrar la sesión (el implementer no ejecuta shell).
