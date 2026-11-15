# Review — feature 57 (retencion_evidencia_y_privacidad_inicial)

**Veredicto:** APPROVED

`./init.sh` terminó con exit 0: 3579 passed, 1 skipped. No lo repetí.

## Trazabilidad requirements ↔ tests
Todos los tests están en `progress/impl_retencion_evidencia_y_privacidad_inicial.md`. Como las tasks T5–T22 enumeran esos tests por nombre, los verifiqué contra esa lista y contra el código.
- R1, R3, R5: [x] `test_blueprint_values_match_approved_policy`
- R2: [x] `test_notice_text_names_responsible_without_email`
- R4: [x] `test_r11_handover_uses_the_approved_retention_values`
- R6: [x] `test_env_example_matches_blueprint_values`
- R7: [x] `test_approved_values_pass_production_validation` (orchestrator y handover)
- R8, R24: [x] `test_docs_state_owner_policy_and_evidence_retention`
- R9, R10: [x] `test_purge_does_not_delete_client_memory`, `test_suppression_still_deletes_client_memory`
- R11, R12: [x] `test_suppression_deletes_consents_of_all_session_identities`
- R13: [x] `test_suppression_keeps_other_clients_consents`
- R14: [x] `test_suppression_removed_counts_include_privacy_consents`
- R15: [x] `test_postgres_suppression_single_transaction_parametrized`
- R16: [x] `test_suppression_failure_in_consent_delete_rolls_back`, `test_postgres_suppression_rolls_back_when_consent_delete_fails`
- R17: [x] `test_client_asked_for_notice_after_suppression`
- R18–R22: [x] `test_purge_deletes_consents_older_than_cutoff_by_occurred_at`, `test_purge_keeps_consent_at_cutoff`, `test_purge_counts_include_privacy_consents`, `test_postgres_purge_deletes_consents_in_same_transaction`
- R23: [x] `test_repositories_same_counts_for_suppression_and_purge`
- R25: [x] `test_docs_do_not_claim_legal_validation`
- R26: [x] `./init.sh` verde

## Verificación en el código
- **Supresión en Postgres** (`repository.py` ~5132-5158): el `DELETE FROM privacy_consents p USING contacts c` está parametrizado con `ANY(%s)` y usa `channel` más `external_user_id`, con `COALESCE` hacia `telegram_user_id`. Va en la misma transacción que el `UPDATE ... executed`, y hay un único `commit`. Ante una excepción hace `rollback` y relanza.
- **Supresión en Fake** (~2376-2458): las identidades salen de los contactos de todas las sesiones del perfil, así que cubre varios canales. El fallo inyectado `fail_privacy_consent_delete` se lanza antes de cualquier mutación, así que no queda nada borrado y la solicitud sigue `pending`. `counts["privacy_consents"]` siempre está presente.
- **Purga en Postgres** (~5277-5300): `COALESCE(occurred_at, accepted_at) < %s`, estrictamente menor, antes del `INSERT` en `privacy_purge_runs`. El conteo está incluido y no depende de si el contacto está activo.
- **Purga en Fake** (~2030-2047): mismo criterio.
- **Memoria:** la purga no borra `client_memory`, y la supresión sí lo hace y lo informa.
- **Render:** `render.yaml` tiene los valores aprobados, `MEMORY_ENABLED` en `"true"` y `fromService` de `PRIVACY_RETENTION_DAYS` en orchestrator. Handover declara 30 y 15. Un test cruza `.env.example` con el Blueprint.
- **Docs:** `docs/despliegue.md` y `docs/proyecto.md` dicen explícitamente que no hay revisión legal externa y que la política queda pendiente de ella. No afirman validación legal independiente.

## Tasks completas
- T1–T23: [x] (todas en `[x]` en `specs/retencion_evidencia_y_privacidad_inicial/tasks.md`)

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x]
- C4: [x]
- C5: [x] (el cierre de `progress/history.md` y el estado de la feature quedan para el leader)
- C6: [x]

## Cambios requeridos
Ninguno.
