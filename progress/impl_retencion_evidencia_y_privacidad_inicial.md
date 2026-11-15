# Implementación — retencion_evidencia_y_privacidad_inicial (#57)

## Resumen

- `FakeRepository` y `PostgresRepository` de orchestrator borran
  `privacy_consents` en la supresión por identidades `(channel, external_user_id)`
  de los contactos de las sesiones del perfil y en la purga por antigüedad
  (`occurred_at`, con respaldo en `accepted_at`). Ambos añaden siempre
  `counts["privacy_consents"]`.
- La supresión conserva la atomicidad: en Fake el fallo inyectado se evalúa
  antes de mutar y en Postgres el `DELETE` va en la misma transacción; un fallo
  hace rollback sin marcar `executed`.
- `client_memory` se mantiene intacta en `purge_personal_data` y sigue
  borrándose en la supresión.
- `render.yaml`, `.env.example` y `docs/despliegue.md` reflejan la política
  aprobada por el dueño el 2026-11-14 (aviso 1.0, ACEPTO/NO ACEPTO, 30/15 días,
  memoria activada). `contracts/CONTRATOS.md`, `docs/proyecto.md` y
  `docs/especificacion.md` documentan la retención de la evidencia y que no hay
  validación legal externa.
- Tests de #28 (`scripts/tests/test_render_retencion.py`) y #40
  (`test_memory_config.py`) actualizados a los valores aprobados; conteos
  exactos de #27/#40 actualizados con `privacy_consents`.

## Trazabilidad

- R1 → `scripts/tests/test_render_retencion.py::test_blueprint_values_match_approved_policy`
- R2 → `scripts/tests/test_render_retencion.py::test_notice_text_names_responsible_without_email`
- R3 → `scripts/tests/test_render_retencion.py::test_blueprint_values_match_approved_policy`
- R4 → `scripts/tests/test_render_retencion.py::test_r11_handover_uses_the_approved_retention_values`
- R5 → `scripts/tests/test_render_retencion.py::test_blueprint_values_match_approved_policy`
- R6 → `scripts/tests/test_render_retencion.py::test_env_example_matches_blueprint_values`
- R7 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_approved_values_pass_production_validation` y `services/handover/tests/test_production_config.py::test_approved_values_pass_production_validation`
- R8 → `scripts/tests/test_render_retencion.py::test_docs_state_owner_policy_and_evidence_retention`
- R9 → `services/orchestrator/tests/test_memory_suppression.py::test_purge_does_not_delete_client_memory`
- R10 → `services/orchestrator/tests/test_memory_suppression.py::test_suppression_still_deletes_client_memory`
- R11 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_suppression_deletes_consents_of_all_session_identities`
- R12 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_suppression_deletes_consents_of_all_session_identities`
- R13 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_suppression_keeps_other_clients_consents`
- R14 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_suppression_removed_counts_include_privacy_consents`
- R15 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_postgres_suppression_single_transaction_parametrized`
- R16 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_suppression_failure_in_consent_delete_rolls_back` y `::test_postgres_suppression_rolls_back_when_consent_delete_fails`
- R17 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_client_asked_for_notice_after_suppression`
- R18 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_purge_deletes_consents_older_than_cutoff_by_occurred_at` y `::test_postgres_purge_deletes_consents_in_same_transaction`
- R19 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_purge_keeps_consent_at_cutoff`
- R20 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_purge_counts_include_privacy_consents` y `::test_postgres_purge_deletes_consents_in_same_transaction`
- R21 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_purge_deletes_consents_older_than_cutoff_by_occurred_at`
- R22 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_purge_deletes_consents_older_than_cutoff_by_occurred_at`
- R23 → `services/orchestrator/tests/test_privacy_evidence_retention.py::test_repositories_same_counts_for_suppression_and_purge`
- R24 → `scripts/tests/test_render_retencion.py::test_docs_state_owner_policy_and_evidence_retention`
- R25 → `scripts/tests/test_render_retencion.py::test_docs_do_not_claim_legal_validation`
- R26 → `./init.sh` (verificación final abajo); tests de #27/#28/#35/#37/#40 ajustados donde dependían de los valores anteriores (`test_privacy_purge.py`, `test_memory_suppression.py`, `test_render_retencion.py`, `test_memory_config.py`, `test_worker_compose.py`).

## Notas

- La política es decisión aprobada por el dueño y no afirma revisión legal externa.

## Verificación final

`bash ./init.sh`: exit 0, 3579 passed, 1 skipped y 2 avisos de deprecación.
T1–T23 completas; queda pendiente la revisión de código Claude.
