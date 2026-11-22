# Implementación — #72 consentimiento_unico_por_cliente

## Resumen

- `Settings.client_consent_retention_days` (vacío = sin caducidad) con validador y
  `client_consent_not_before(now)`; documentado en `.env.example`.
- Tablas `identidades_cliente` y `consentimientos_cliente` en el esquema Postgres.
- `Repository` (Protocol, `FakeRepository` y `PostgresRepository`):
  `has_client_consent_for_identity`, `register_client_login`,
  `register_client_acceptance_if_linked` y `client_history`.
- Dominio: `has_current_consent` (evidencia por canal o cobertura por cliente),
  `_has_current_consent` como alias, registro en login y aceptación, e historial
  unificado por cliente.
- `main.py` decide `consent_ready` con `_has_current_consent`.
- Supresión y purga borran/retienen las tablas nuevas según el spec, con las claves
  nuevas en `removed_counts`/`deleted`.
- `contracts/CONTRATOS.md` documenta tablas, variable, claves y supuesto legal.

Nota: `./init.sh` queda pendiente de la ejecución de Claude al cerrar la sesión.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_consentimiento_unico_cliente.py::test_login_registers_client_consent_and_identity`
- R2 → `...::test_login_registers_client_consent_and_identity`
- R3 → `...::test_login_keeps_original_client_consent_row`
- R4 → `...::test_linked_identity_on_other_channel_not_asked_notice`
- R5 → `...::test_not_asked_after_logout`
- R6 → `services/orchestrator/tests/test_consent_before_data.py::test_post_messages_dedup_uses_client_coverage`
- R7 → `...::test_new_version_asks_once_and_covers_all_channels`
- R8 → `...::test_new_version_asks_once_and_covers_all_channels`
- R9 → `...::test_new_version_asks_once_and_covers_all_channels`
- R10 → `...::test_unlinked_identity_still_gets_notice`
- R11 → `...::test_unlinked_identity_stores_no_data`
- R12 → `...::test_login_registers_client_consent_and_identity` y
  `...::test_client_history_merges_identities_with_channel`
- R13 → `...::test_login_registers_client_consent_and_identity`
- R14 → `...::test_failed_login_does_not_link`
- R15 → `...::test_login_reassigns_identity_to_new_client`
- R16 → `...::test_client_history_merges_identities_with_channel`
- R17 → `...::test_link_failure_does_not_break_login_and_asks_again`
- R18 → `...::test_login_still_required_for_covered_identity` y
  `...::test_not_asked_after_logout`
- R19 → `...::test_no_alternative_identification_routes`
- R20 → `...::test_client_consent_kept_without_retention`
- R21 → `...::test_client_consent_purged_after_configured_days`
- R22 → `services/orchestrator/tests/test_config.py::test_config_client_consent_retention_valid_and_invalid`
- R23 → `...::test_suppression_removes_client_consent_and_identities`
- R24 → `...::test_suppression_removes_privacy_consents_of_all_linked_identities`
- R25 → `...::test_suppressed_client_identity_gets_notice_again`
- R26 → `services/orchestrator/tests/test_consent_before_data.py`,
  `test_text_consent_telegram.py`, `test_privacy.py`, `test_privacy_purge.py`,
  `test_memory_suppression.py`, `test_identity_link.py` (intención intacta salvo
  las claves nuevas exigidas en los conteos de supresión).
- R27 → `contracts/tests/test_consentimiento_unico_doc.py::test_contratos_documenta_consentimiento_por_cliente`

## Corrección (intento 2)

- `test_consentimiento_unico_cliente.py`: `_login_contact` ahora asegura la
  credencial con `_ensure_client` (crea `cliente1`/`cliente2` con
  `create_client`, que hashea `clave-segura-123` con `password_scrypt_n`) solo
  si el usuario aún no existe; los tests que ya creaban el cliente no duplican.
- `test_identity_repository.py::test_postgres_identity_sql_is_parameterized`:
  se usa el usuario `usuario-x` en lugar de `ana` para que la aserción no
  choque con la subcadena de `canal_id` del nuevo DDL.

## Fallo de init.sh (intento 1) - corregir

5 tests fallan (4577 pasan):
1. `test_consentimiento_unico_cliente.py`: `test_linked_identity_on_other_channel_not_asked_notice`,
   `test_not_asked_after_logout`, `test_unlinked_identity_still_gets_notice`,
   `test_login_still_required_for_covered_identity` -> `ClientLoginFailed: Usuario o contraseña
   incorrectos` en `_login_contact`/`_login`: el helper de test no crea bien las credenciales
   del cliente (usuario `cliente1`, clave `clave-segura-123`). Revisa cómo
   `test_identity_link.py` siembra credenciales (hash scrypt con la clave de settings) y haz
   que el helper lo imite.
2. `test_identity_repository.py::test_postgres_identity_sql_is_parameterized`: `assert "ana" not
   in joined` falla porque el nuevo DDL contiene "canal_id" (subcadena "ana"). Corrige el test
   usando un valor de usuario que no sea subcadena del DDL (p. ej. "usuario-x") en ese test.
Salida completa: progress/init_72.log

## Resultado de init.sh

Tras una corrección delegada a OpenCode (helper de credenciales en los tests nuevos y valor no
colisionante en `test_postgres_identity_sql_is_parameterized`): `./init.sh` OK, 4582 passed,
1 skipped (log: progress/init_72b.log). Trazabilidad R1..R27 -> test presente arriba.
