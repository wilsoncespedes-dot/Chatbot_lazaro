# Implementación — privacidad_y_retencion_datos (#27)

Feature `in_progress`, spec aprobada. Implementadas T1–T35. T36 queda a medias por
límite de herramientas: la trazabilidad está aquí y `./init.sh` lo ejecuta Claude al
cerrar la sesión (el implementer no ejecuta shell).

## Resumen

- **contracts**: `PrivacyPurgeRequest`/`PrivacyPurgeResponse`, ejemplos y sección de
  `POST /privacy/purge` (handover → orchestrator, `closed_active_cases`, 401/503).
- **orchestrator**: puerta de consentimiento antes de crear contacto; aceptación solo
  con igualdad normalizada; `privacy_consents` con versión y sha256; `POST /privacy/purge`
  con corte por antigüedad y conservación de tablas operativas.
- **handover**: validación de los dos plazos; `POST /privacy/purge` que borra cerrados
  antiguos y cierra+borra activos expirados con sus solicitudes en una transacción.
- **worker**: `scripts/purgar_datos.py` (handover primero y salto del orchestrator si
  falla), `retention_worker` en Compose, COPY en el Dockerfile y variables en `.env`.
- Tests existentes ajustados solo donde la spec lo exige: fixture del orquestador con
  configuración y consentimiento; rutas esperadas; configuración de producción; conteo
  de tablas de handover. No se eliminó ninguna aserción.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_production_config.py::test_missing_required_variable_is_rejected`
- R2 → `services/orchestrator/tests/test_config.py::test_retention_days_must_be_positive_integer`
- R3 → `services/orchestrator/tests/test_config.py::test_notice_must_contain_the_acceptance_phrase`
- R4 → `services/orchestrator/tests/test_privacy.py::test_without_privacy_config_drops_client_route`
- R5 → `services/orchestrator/tests/test_privacy.py::test_without_privacy_config_drops_client_route`
- R6 → `services/orchestrator/tests/test_privacy.py::test_without_privacy_config_drops_client_route`
- R7 → `services/orchestrator/tests/test_privacy.py::test_without_consent_sends_notice_and_stores_nothing`
- R8 → `services/orchestrator/tests/test_privacy.py::test_without_consent_sends_notice_and_stores_nothing`
- R9 → `services/orchestrator/tests/test_privacy.py::test_exact_acceptance_records_consent`
- R10 → `services/orchestrator/tests/test_privacy.py::test_exact_acceptance_records_consent`
- R11 → `services/orchestrator/tests/test_privacy.py::test_exact_acceptance_records_consent`
- R12 → `services/orchestrator/tests/test_privacy.py::test_acceptance_with_extra_text_does_not_record_consent`
- R13 → `services/orchestrator/tests/test_privacy.py::test_acceptance_with_extra_text_does_not_record_consent`
- R14 → `services/orchestrator/tests/test_privacy.py::test_personal_routes_never_create_consent`
- R15 → `services/orchestrator/tests/test_privacy.py::test_version_change_requires_new_acceptance_and_keeps_old_rows`
- R16 → `services/orchestrator/tests/test_privacy.py::test_current_consent_keeps_the_normal_flow`
- R17 → `services/orchestrator/tests/test_privacy.py::test_consent_store_failure_returns_500_without_confirmation`
- R18 → `services/orchestrator/tests/test_privacy.py::test_consent_store_failure_returns_500_without_confirmation`
- R19 → `services/orchestrator/tests/test_privacy.py::test_personal_routes_work_without_privacy_configuration`
- R20 → `services/orchestrator/tests/test_privacy_purge.py::test_purge_requires_service_token`
- R21 → `services/orchestrator/tests/test_privacy_purge.py::test_purge_without_retention_days_returns_503_and_deletes_nothing`
- R22 → `services/orchestrator/tests/test_privacy_purge.py::test_messages_and_events_boundaries`
- R23 → `services/orchestrator/tests/test_privacy_purge.py::test_messages_and_events_boundaries`
- R24 → `services/orchestrator/tests/test_privacy_purge.py::test_inactive_contact_is_deleted_with_case_links`
- R25 → `services/orchestrator/tests/test_privacy_purge.py::test_active_contacts_are_preserved`
- R26 → `services/orchestrator/tests/test_privacy_purge.py::test_operational_tables_and_consents_are_preserved`
- R27 → `services/orchestrator/tests/test_privacy_purge.py::test_response_and_purge_run_are_saved`
- R28 → `services/orchestrator/tests/test_privacy_purge.py::test_response_and_purge_run_are_saved`
- R29 → `services/handover/tests/test_production_config.py::test_missing_required_variable_is_rejected`
- R30 → `services/handover/tests/test_config.py::test_privacy_days_must_be_positive_integer`
- R31 → `services/handover/tests/test_config.py::test_active_case_limit_must_be_strictly_less`
- R32 → `services/handover/tests/test_privacy_purge.py::test_purge_without_retention_config_returns_503`
- R33 → `services/handover/tests/test_privacy_purge.py::test_purge_requires_service_token`
- R34 → `services/handover/tests/test_privacy_purge.py::test_closed_cases_before_cutoff_are_deleted`
- R35 → `services/handover/tests/test_privacy_purge.py::test_expired_active_cases_are_closed_and_deleted_with_their_requests`
- R36 → `services/handover/tests/test_privacy_purge.py::test_expired_active_cases_are_closed_and_deleted_with_their_requests`
- R37 → `services/handover/tests/test_privacy_purge.py::test_expired_active_cases_are_closed_and_deleted_with_their_requests`
- R38 → `services/handover/tests/test_privacy_purge.py::test_requests_are_deleted_by_received_at`
- R39 → `services/handover/tests/test_privacy_purge.py::test_notifications_and_denials_are_preserved`
- R40 → `services/handover/tests/test_privacy_purge.py::test_expired_active_cases_are_closed_and_deleted_with_their_requests`
- R41 → `services/handover/tests/test_purgar_datos.py::test_calls_handover_then_orchestrator_with_token_and_empty_body`
- R42 → `services/handover/tests/test_purgar_datos.py::test_calls_handover_then_orchestrator_with_token_and_empty_body`
- R43 → `services/handover/tests/test_purgar_datos.py::test_handover_failure_skips_orchestrator_and_exits_nonzero`
- R44 → `services/handover/tests/test_purgar_datos.py::test_exit_zero_only_when_both_calls_are_200`
- R45 → `services/handover/tests/test_purgar_datos.py::test_orchestrator_failure_exits_nonzero`
- R46 → `services/handover/tests/test_purgar_datos.py::test_loop_continues_after_a_failure_and_repeats_the_order`
- R47 → `services/handover/tests/test_worker_compose.py::test_retention_worker_runs_the_purge_script_in_a_loop`
- R48 → `services/handover/tests/test_worker_compose.py::test_handover_dockerfile_copies_the_purge_script`
- R49 → `services/handover/tests/test_worker_compose.py::test_retention_worker_publishes_no_ports`
- R50 → `services/handover/tests/test_worker_compose.py::test_env_example_declares_privacy_variables_empty`
- R51 → `contracts/tests/test_privacy.py::test_doc_section_names_both_services_and_order`
- R52 → `contracts/tests/test_privacy.py::test_models_are_exported`

## Supuestos pendientes de aprobación del dueño (S1–S6)

- **S1** texto del aviso, finalidades, responsable y canal de derechos:
  `PRIVACY_NOTICE_TEXT` vacío (falla cerrado).
- **S2** versión del aviso: `PRIVACY_NOTICE_VERSION` vacío.
- **S3** frase de aceptación y respuesta: `PRIVACY_ACCEPT_PHRASE` y
  `PRIVACY_ACCEPTED_REPLY` vacíos.
- **S4** plazo de retención: `PRIVACY_RETENTION_DAYS` vacío; `/privacy/purge` → 503.
- **S5** cuánto conservar `privacy_consents`: #27 no la purga.
- **S6** vida máxima de casos activos: `PRIVACY_ACTIVE_CASE_MAX_DAYS` vacío y menor que
  la retención; sin él producción no arranca y la purga de handover da 503.

Producción exige las 5 variables del orchestrator y las 2 de handover. No hay plazos
ni textos por defecto. No se desplegó nada ni se ejecutaron purgas externas.

## Notas para la revisión

- La aceptación se procesa en la petición HTTP (no en `BackgroundTasks`) solo para poder
  devolver `500` si falla el guardado (R18). El resto de mensajes sigue en background.
- Los fixtures existentes del orchestrator conceden consentimiento vigente para no
  alterar el flujo previo; las pruebas de privacidad lo desactivan explícitamente.
- Queda pendiente que Claude ejecute `./init.sh` (T36).

## Corrección solicitada tras ./init.sh
- Resultado: 1 failed, 1853 passed.
- Falla: `contracts/tests/test_privacy.py::test_doc_section_documents_response_and_errors`; la sección `/privacy/purge` de `contracts/CONTRATOS.md` debe documentar el error `401 unauthorized` explícitamente. Añade la documentación donde corresponde y verifica que no cambie el contrato de autenticación.
- No ejecutes shell. Actualiza los tests/tareas afectados y este informe. El líder ejecutará `./init.sh`.

### Corrección aplicada
- En la tabla de errores de `### POST /privacy/purge` de `contracts/CONTRATOS.md` los códigos
  aparecen entrecomillados como en la tabla común: `401` → `` `unauthorized` `` (R20, R33),
  `422` → `` `validation_error` ``, `503` → `` `privacy_not_configured` `` (R21, R32) y
  `500` → `` `internal_error` ``. Así el test encuentra los fragmentos `` `unauthorized` `` y
  `` `privacy_not_configured` `` dentro de la sección.
- No se tocó la regla de autenticación ni el middleware: el token sigue aplicándose igual que
  antes y la tabla común de errores no cambia. `POST /privacy/purge` no forma parte de `ROUTES`
  de `test_contratos_doc.py`, así que el formato de su tabla no afecta a otros tests.
- Sin cambios de código ni de tests; T1–T35 siguen completadas y T36 queda pendiente de que el
  líder ejecute `./init.sh`.
