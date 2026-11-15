# Tasks — retencion_evidencia_y_privacidad_inicial (feature #57)

Tests nuevos en `services/orchestrator/tests/test_privacy_evidence_retention.py` salvo que se
indique otro archivo.

- [x] T1 — Fake `execute_suppression`: borrar `privacy_consents` por identidades `(channel, external_user_id)` de los contactos de las sesiones del perfil, aplicar tras validar y antes de marcar `executed`; añadir `fail_privacy_consent_delete` y `counts["privacy_consents"]`. Archivo: `services/orchestrator/orchestrator/adapters/repository.py`. Cubre: R11, R12, R13, R14, R16.
- [x] T2 — Postgres `execute_suppression`: añadir `DELETE FROM privacy_consents p USING contacts c ... RETURNING p.id` parametrizado en la misma transacción y `counts["privacy_consents"]`. Cubre: R11, R12, R13, R14, R15, R16.
- [x] T3 — Fake `purge_personal_data`: borrar evidencia con fecha (`occurred_at` o `accepted_at`) anterior al corte y añadir `counts["privacy_consents"]`. Cubre: R18, R19, R20, R21, R22.
- [x] T4 — Postgres `purge_personal_data`: `DELETE FROM privacy_consents WHERE COALESCE(occurred_at, accepted_at) < %s RETURNING id` antes del `INSERT` en `privacy_purge_runs`, y `counts["privacy_consents"]`. Cubre: R18, R19, R20, R21, R22.
- [x] T5 — Test `test_suppression_deletes_consents_of_all_session_identities` (Telegram + WhatsApp del mismo perfil; evidencia de versiones y resultados distintos). Cubre: R11, R12.
- [x] T6 — Test `test_suppression_keeps_other_clients_consents`. Cubre: R13.
- [x] T7 — Test `test_suppression_removed_counts_include_privacy_consents` (con evidencia y con 0). Cubre: R14.
- [x] T8 — Test `test_suppression_failure_in_consent_delete_rolls_back` con Fake (`fail_privacy_consent_delete`: solicitud `pending`, mensajes y memoria intactos, `removed_counts` ausente). Cubre: R16.
- [x] T9 — Test Postgres con conexión simulada `test_postgres_suppression_single_transaction_parametrized`: el `DELETE FROM privacy_consents` usa `%s`/`ANY(%s)` sin interpolar valores, un único `commit` tras el `UPDATE ... executed`, y `rollback` sin `commit` si el DELETE falla. Cubre: R15, R16.
- [x] T10 — Test `test_client_asked_for_notice_after_suppression` (flujo `process_message` tras suprimir: envía aviso y no procesa mensaje). Cubre: R17.
- [x] T11 — Test `test_purge_deletes_consents_older_than_cutoff_by_occurred_at` con evidencia de contacto activo e inactivo, y legada con `occurred_at=None`. Cubre: R18, R21, R22.
- [x] T12 — Test `test_purge_keeps_consent_at_cutoff` (igual al corte se conserva; un segundo antes se borra). Cubre: R19.
- [x] T13 — Test `test_purge_counts_include_privacy_consents` (retorno, `PrivacyPurgeResponse.deleted` y `privacy_purge_runs`). Cubre: R20.
- [x] T14 — Test Postgres con conexión simulada `test_postgres_purge_deletes_consents_in_same_transaction`. Cubre: R18, R20.
- [x] T15 — Test parametrizado (`fake`, `postgres` simulado) `test_repositories_same_counts_for_suppression_and_purge` con el mismo escenario. Cubre: R23.
- [x] T16 — Tests `test_purge_does_not_delete_client_memory` y `test_suppression_still_deletes_client_memory` en `services/orchestrator/tests/test_memory_suppression.py`. Cubre: R9, R10.
- [x] T17 — `render.yaml`: poner `value` en `PRIVACY_NOTICE_VERSION` (`"1.0"`), `PRIVACY_ACCEPT_PHRASE` (`"ACEPTO"`), `PRIVACY_REJECT_PHRASE` (`"NO ACEPTO"`), `PRIVACY_NOTICE_TEXT`, `PRIVACY_ACCEPTED_REPLY` (orchestrator), `PRIVACY_RETENTION_DAYS` (`"30"`) y `PRIVACY_ACTIVE_CASE_MAX_DAYS` (`"15"`) en handover, y `MEMORY_ENABLED` `"true"` con el comentario actualizado. Mantener `fromService` de retención. Cubre: R1, R2, R3, R4, R5.
- [x] T18 — `.env.example`: mismos valores, `MEMORY_ENABLED=true`, comentarios de «aprobado por el dueño». Cubre: R6.
- [x] T19 — Actualizar `scripts/tests/test_render_retencion.py` según design §6 y añadir `test_blueprint_values_match_approved_policy`, `test_notice_text_names_responsible_without_email`, `test_env_example_matches_blueprint_values`. Cubre: R1, R2, R3, R4, R5, R6.
- [x] T20 — Test `test_approved_values_pass_production_validation` (Settings de orchestrator y handover con los valores de `.env.example`). Archivo: `services/orchestrator/tests/test_privacy_evidence_retention.py` y `services/handover/tests/test_production_config.py`. Cubre: R7.
- [x] T21 — `docs/despliegue.md` §2.1 y `contracts/CONTRATOS.md`: política aprobada por el dueño, memoria hasta supresión, evidencia mínima 30 días y borrado anticipado en supresión, quitar `privacy_consents` de «no cubierto»; nota breve en `docs/proyecto.md`/`docs/especificacion.md` de que son valores del dueño sin validación legal. Sin correo ni razón social adicionales. Cubre: R8, R24, R25.
- [x] T22 — Tests de documentación `test_docs_state_owner_policy_and_evidence_retention` y `test_docs_do_not_claim_legal_validation` en `scripts/tests/test_render_retencion.py`. Cubre: R8, R24, R25.
- [x] T23 — Ejecutar `./init.sh` una vez, corregir regresiones de tests de #27/#28/#35/#37/#40 y escribir `progress/impl_retencion_evidencia_y_privacidad_inicial.md` con el mapa de trazabilidad. Cubre: R26.
