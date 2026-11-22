# Tasks — #72 consentimiento_unico_por_cliente

Pruebas en `services/orchestrator/tests/test_consentimiento_unico_cliente.py` salvo
indicación. Para cada test usar el repositorio fake; los de SQL se verifican por la
forma de las consultas con el fake de conexión existente si lo hay, o contra el fake.

- [x] T1 — Añadir `client_consent_retention_days` a `Settings` con validador (vacío o entero >= 1) y propiedad `client_consent_not_before(now)`; documentar `CLIENT_CONSENT_RETENTION_DAYS` en `.env.example` y en la lista de claves de `config.py`. Cubre: R20, R21, R22.
- [x] T2 — Test `test_config_client_consent_retention_valid_and_invalid` en `test_config.py` (vacío ok, `0` y `abc` fallan). Cubre: R22.
- [x] T3 — Añadir DDL de `identidades_cliente` y `consentimientos_cliente` (con índice) al esquema de `adapters/repository.py`. Cubre: R12.
- [x] T4 — Añadir al Protocol `Repository` y a `FakeRepository` (más `tests/fakes.py` si aplica) `has_client_consent_for_identity`, `register_client_login`, `register_client_acceptance_if_linked`, `client_history` y el dataclass `ClientHistoryMessage`. Cubre: R1, R3, R8, R12, R13, R15, R16.
- [x] T5 — Implementar los cuatro métodos en `PostgresRepository` (transacción única en `register_client_login`, `ON CONFLICT DO NOTHING` en el consentimiento, filtro `not_before`). Cubre: R1, R3, R8, R13, R15, R16.
- [x] T6 — Extender `execute_suppression` (fake y Postgres) para borrar `consentimientos_cliente`, `identidades_cliente` y `privacy_consents` de las identidades vinculadas, con las claves nuevas en `removed_counts`. Cubre: R23, R24, R25.
- [x] T7 — Extender `purge_personal_data` (fake y Postgres): borrar `consentimientos_cliente` por plazo solo si hay configuración; nunca `identidades_cliente` por plazo. Cubre: R20, R21.
- [x] T8 — En `domain.py` añadir `has_current_consent` (evidencia por canal o cobertura por cliente) y dejar `_has_current_consent` como alias; usar en `main.py` para `consent_ready`. Cubre: R4, R5, R6, R10.
- [x] T9 — En `_finish_acceptance` llamar `register_client_acceptance_if_linked` con versión, hash y hora del reloj. Cubre: R7, R8, R9.
- [x] T10 — En `login_client`, tras `start_client_session == "ok"`, llamar `register_client_login` dentro de `try/except Exception` con log sin datos personales; no tocar nada en las ramas de fallo. Cubre: R1, R2, R3, R13, R14, R15, R17.
- [x] T11 — Añadir `client_history` en dominio. Cubre: R16.
- [x] T12 — Test `test_login_registers_client_consent_and_identity` (fila con `canal_id` de aceptación y evidencia por canal intacta). Cubre: R1, R2, R13.
- [x] T13 — Test `test_login_keeps_original_client_consent_row` (segundo login desde otro canal no cambia `aceptado_en` ni `canal_id`). Cubre: R3.
- [x] T14 — Test `test_linked_identity_on_other_channel_not_asked_notice` (canal B vinculado sin fila propia: no se envía el aviso y se enruta el texto). Cubre: R4.
- [x] T15 — Test `test_not_asked_after_logout` (cierra sesión; el siguiente texto va al flujo de login, no al aviso). Cubre: R5, R18.
- [x] T16 — Test `test_post_messages_dedup_uses_client_coverage` en `test_main*.py` o `test_consent_before_data.py`: `consent_ready` verdadero con cobertura por cliente. Cubre: R6.
- [x] T17 — Test `test_new_version_asks_once_and_covers_all_channels` (cambia versión, pregunta en el canal A, acepta, el canal B ya no pregunta; la aceptación guarda canal A). Cubre: R7, R8, R9.
- [x] T18 — Test `test_unlinked_identity_still_gets_notice` (identidad nunca vinculada recibe aviso aunque el cliente haya aceptado en otro canal). Cubre: R10.
- [x] T19 — Test `test_unlinked_identity_stores_no_data` (sin contacto, mensaje ni estado). Cubre: R11.
- [x] T20 — Test `test_failed_login_does_not_link` (credenciales inválidas, enlace inválido, credencial revocada, bloqueo, conflicto: sin filas en `identidades_cliente`). Cubre: R14.
- [x] T21 — Test `test_login_reassigns_identity_to_new_client`. Cubre: R15.
- [x] T22 — Test `test_client_history_merges_identities_with_channel`. Cubre: R16.
- [x] T23 — Test `test_link_failure_does_not_break_login_and_asks_again` (fake lanza en `register_client_login`). Cubre: R17.
- [x] T24 — Test `test_login_still_required_for_covered_identity` y `test_no_alternative_identification_routes` (inspecciona rutas de la app y `Settings`: sin ruta ni campo nuevo de identificación o código por canal). Cubre: R18, R19.
- [x] T25 — Tests `test_client_consent_kept_without_retention`, `test_client_consent_purged_after_configured_days` (incluye que deja de cubrir). Cubre: R20, R21.
- [x] T26 — Tests `test_suppression_removes_client_consent_and_identities` (conteos en `removed_counts`) y `test_suppression_removes_privacy_consents_of_all_linked_identities`, `test_suppressed_client_identity_gets_notice_again`. Cubre: R23, R24, R25.
- [x] T27 — Documentar en `contracts/CONTRATOS.md` las tablas, `CLIENT_CONSENT_RETENTION_DAYS`, las claves nuevas de `deleted` y `removed_counts` y el supuesto de legal; añadir `contracts/tests/test_consentimiento_unico_doc.py::test_contratos_documenta_consentimiento_por_cliente`. Cubre: R27.
- [x] T28 — Correr sin modificar la intención `test_consent_before_data.py`, `test_text_consent_telegram.py`, `test_privacy.py`, `test_privacy_purge.py`, `test_memory_suppression.py`, `test_identity_link.py`; ajustar solo fakes si hace falta; `./init.sh` verde. Cubre: R26.
- [x] T29 — Escribir `progress/impl_consentimiento_unico_por_cliente.md` con el mapa R<n> -> test. Cubre: R1-R27.
