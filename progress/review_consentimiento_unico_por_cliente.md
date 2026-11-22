# Review — feature #72 consentimiento_unico_por_cliente

**Veredicto:** APPROVED

`./init.sh` ejecutado por el revisor: verde, 4582 passed, 1 skipped, exit OK.

## Trazabilidad requirements ↔ tests
Los 21 tests citados en `progress/impl_consentimiento_unico_por_cliente.md` existen (verificado por búsqueda de `def`):
- R1, R2, R12, R13: [x] `test_login_registers_client_consent_and_identity`
- R3: [x] `test_login_keeps_original_client_consent_row`
- R4: [x] `test_linked_identity_on_other_channel_not_asked_notice`
- R5: [x] `test_not_asked_after_logout`
- R6: [x] `test_post_messages_dedup_uses_client_coverage` (test_consent_before_data.py)
- R7, R8, R9: [x] `test_new_version_asks_once_and_covers_all_channels`
- R10: [x] `test_unlinked_identity_still_gets_notice`
- R11: [x] `test_unlinked_identity_stores_no_data`
- R14: [x] `test_failed_login_does_not_link`
- R15: [x] `test_login_reassigns_identity_to_new_client`
- R16: [x] `test_client_history_merges_identities_with_channel`
- R17: [x] `test_link_failure_does_not_break_login_and_asks_again`
- R18: [x] `test_login_still_required_for_covered_identity`
- R19: [x] `test_no_alternative_identification_routes`
- R20: [x] `test_client_consent_kept_without_retention`
- R21: [x] `test_client_consent_purged_after_configured_days`
- R22: [x] `test_config_client_consent_retention_valid_and_invalid`
- R23: [x] `test_suppression_removes_client_consent_and_identities`
- R24: [x] `test_suppression_removes_privacy_consents_of_all_linked_identities`
- R25: [x] `test_suppressed_client_identity_gets_notice_again`
- R26: [x] suite existente (#35, #37, #46) verde en init.sh
- R27: [x] `contracts/tests/test_consentimiento_unico_doc.py::test_contratos_documenta_consentimiento_por_cliente`

## Tasks completas
- T1-T29: [x] todas en `[x]` en specs/consentimiento_unico_por_cliente/tasks.md

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x] (sin servicios ni dependencias nuevas; variable nueva en `.env.example`)
- C4: [x]
- C5: [x] (el cierre de sesión e historial corresponden al leader)
- C6: [x]

## Observaciones no bloqueantes
- El `impl_*.md` conserva una nota obsoleta ("`./init.sh` queda pendiente"); queda superada por la sección «Resultado de init.sh» y por la ejecución del revisor.
