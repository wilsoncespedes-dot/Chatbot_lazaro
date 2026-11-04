# Implementación — #38 identidad_credenciales

- T0: `referencias/` no existe en esta máquina; no se reutiliza código de
  terceros (sin cambios en `THIRD_PARTY_NOTICES.md`). Implementación propia.
- Solo se tocó `services/orchestrator/`, `.env.example`, `render.yaml` y la
  documentación; `contracts/` y los gateways no cambian.
- Decisión abierta aplicada (default seguro ya aprobado): renovar una
  credencial revocada responde `409 credential_revoked`; la reactivación
  explícita queda para #42.
- `IDENTITY_LOGIN_REQUIRED` es `true` por defecto; las suites históricas usan
  `false` desde `tests/conftest.py` (R44) y los tests de #38 lo activan.
- Se instaló un `logging.Filter` idempotente sobre `uvicorn.access` que redacta
  `t=` (R25); no se usa `--no-access-log` para conservar el log de acceso.
- `./init.sh` no se ejecutó en esta sesión del implementer; lo ejecuta Claude
  después y añade el resultado a este informe.

## Resumen de cambios

- `orchestrator/identity.py`: firma HMAC del enlace, estados de credencial,
  días restantes, comandos de cierre y política `identity.*`.
- `orchestrator/accounts.py`: scrypt con prefijo y despacho de `verify_password`
  entre scrypt y PBKDF2.
- `orchestrator/domain.py`: emisión de enlaces, login con orden fijo, cierre de
  sesiones, administración de clientes y compuerta de identidad en
  `_route_consented_text`; transiciones nuevas de #37.
- `orchestrator/adapters/repository.py`: 5 tablas, índices únicos parciales y
  métodos en Protocol, `FakeRepository` y `PostgresRepository`.
- `orchestrator/identity_page.py` + `identity_routes.py`: `GET/POST /acceso`
  con HTML propio, sin CDN, encabezados seguros y token de un solo uso.
- `orchestrator/main.py`: registro de `/acceso` y `/clients…`, exención del
  middleware solo para `/acceso`, filtro de log y modelos locales.
- `orchestrator/config.py`, `.env.example`, `render.yaml`: variables y
  validaciones de producción. `privacy.py`/`admin.py`: textos nuevos del panel.
- `docs/architecture.md` y `docs/despliegue.md`: módulo de identidad y variables.

## Trazabilidad

- R1 → `test_identity_link.py::test_accept_button_sends_text_and_link_to_same_channel_and_chat`, `::test_whatsapp_accept_uses_the_external_chat`
- R2 → `test_identity_messages.py::test_awaiting_login_sends_reminder_and_new_link`
- R3 → `test_identity_crypto.py::test_login_token_format_and_signature`, `::test_signature_prefix_binds_the_token_version`
- R4 → `test_identity_link.py::test_issue_link_uses_base_url_and_ttl_and_stores_only_hash`, `test_identity_repository.py::test_login_link_is_stored_by_hash_only_and_previous_link_invalidated`
- R5 → `test_identity_link.py::test_issue_new_link_invalidates_the_previous_one`, `test_identity_messages.py::test_awaiting_login_sends_reminder_and_new_link`
- R6 → `test_identity_link.py::test_issue_link_uses_base_url_and_ttl_and_stores_only_hash`, `test_identity_config.py::test_defaults_match_the_documented_table`
- R7 → `test_identity_link.py::test_missing_base_or_key_omits_link_and_stores_nothing`
- R8 → `test_identity_config.py::test_production_identity_requirements`, `::test_env_example_and_render_declare_identity_variables`
- R9 → `test_identity_link.py::test_missing_label_fails_closed_without_link`, `test_conversation_texts.py::test_identity_texts_do_not_gate_the_consent_flow`
- R10 → `test_identity_routes.py::test_get_with_valid_token_shows_form_without_consuming_it`, `::test_login_page_has_no_external_resources`
- R11 → `test_identity_routes.py::test_get_with_valid_token_shows_form_without_consuming_it`, `::test_acceso_is_public_but_similar_paths_require_service_token`
- R12 → `test_identity_login.py::test_reused_expired_or_tampered_link_is_400`, `test_identity_routes.py::test_invalid_or_used_token_returns_400_without_credentials`
- R13 → `test_identity_crypto.py::test_altered_or_malformed_token_is_rejected`, `test_identity_login.py::test_invalid_signature_does_not_consult_repository`
- R14 → `test_identity_login.py::test_valid_credential_creates_session_and_activates_contact`, `test_identity_routes.py::test_post_success_creates_session_from_the_link_contact`
- R15 → `test_identity_login.py::test_valid_credential_creates_session_and_activates_contact`, `test_identity_repository.py::test_start_session_consumes_link_once_and_reports_conflict`
- R16 → `test_identity_login.py::test_valid_credential_creates_session_and_activates_contact`
- R17 → `test_identity_routes.py::test_post_success_creates_session_from_the_link_contact`
- R18 → `test_identity_login.py::test_contact_is_taken_from_the_link_without_profile_channel_id`, `::test_telegram_profile_without_telegram_user_id_can_login`, `test_identity_messages.py::test_route_never_looks_up_profiles_by_telegram_id`
- R19 → `test_identity_crypto.py::test_scrypt_hash_format_salt_and_verification`
- R20 → `test_identity_crypto.py::test_scrypt_hash_format_salt_and_verification`, `::test_pbkdf2_hashes_from_20_still_verify`, `::test_unknown_prefix_is_rejected`
- R21 → `test_identity_login.py::test_unknown_user_wrong_password_and_staff_profile_share_401`, `test_identity_routes.py::test_error_status_mapping_and_no_password_echo`
- R22 → `test_identity_login.py::test_wrong_password_also_records_failure_and_fake_verification`
- R23 → `test_identity_login.py::test_five_failures_lock_even_a_correct_password`, `test_identity_routes.py::test_five_failures_return_429_even_with_correct_password`
- R24 → `test_identity_login.py::test_success_clears_failed_attempts`
- R25 → `test_identity_routes.py::test_password_and_token_never_leak`, `::test_uvicorn_access_log_redacts_the_t_query_value`
- R26 → `test_identity_login.py::test_second_login_for_same_credential_returns_409_and_keeps_token`, `test_identity_routes.py::test_error_status_mapping_and_no_password_echo`
- R27 → `test_identity_repository.py::test_schema_has_identity_tables_and_partial_indexes`, `::test_two_concurrent_sessions_only_one_wins`, `::test_postgres_start_session_only_maps_unique_violation_to_conflict`
- R28 → `test_identity_messages.py::test_message_with_session_updates_last_activity`, `::test_with_advisor_session_does_not_expire`
- R29 → `test_identity_crypto.py::test_logout_commands_match_normalized_exact_text`, `test_identity_messages.py::test_logout_command_ends_session_and_keeps_privacy_consents`
- R30 → `test_identity_login.py::test_idle_session_is_closed_and_second_login_succeeds`, `::test_with_advisor_session_is_not_treated_as_idle_on_login`, `test_identity_messages.py::test_inactivity_ends_session_and_does_not_call_rag`, `::test_with_advisor_session_does_not_expire`
- R31 → `test_identity_messages.py::test_inactivity_ends_session_and_does_not_call_rag`
- R32 → `test_identity_messages.py::test_logout_command_ends_session_and_keeps_privacy_consents`
- R33 → `test_identity_messages.py::test_active_without_session_returns_to_login`
- R34 → `test_identity_login.py::test_expired_credential_creates_session_but_denies_access`
- R35 → `test_identity_messages.py::test_expired_credential_on_active_contact_denies_access`
- R36 → `test_identity_login.py::test_revoked_not_started_or_missing_credential_is_403`, `test_identity_admin.py::test_login_after_revoke_returns_403`
- R37 → `test_identity_admin.py::test_revoke_ends_the_session_and_notifies`, `test_identity_repository.py::test_identity_audit_and_overrides`
- R38 → `test_identity_admin.py::test_create_client_hashes_password_and_reports_status`, `test_identity_routes.py::test_post_clients_returns_201_without_hash_or_password`
- R39 → `test_identity_admin.py::test_renew_adds_days_from_the_later_of_valid_until_and_now`, `test_identity_routes.py::test_get_renew_revoke_and_close_session`
- R40 → `test_identity_admin.py::test_renewal_reactivates_no_access_contact_with_session`
- R41 → `test_identity_messages.py::test_no_access_with_renewed_credential_is_reactivated_before_routing`
- R42 → `test_identity_admin.py::test_revoke_ends_the_session_and_notifies`, `::test_admin_close_session_ends_with_admin_closed_reason`, `test_identity_routes.py::test_get_renew_revoke_and_close_session`
- R43 → `test_conversation_states.py::test_transition_table_covers_the_documented_paths`
- R44 → `test_identity_messages.py::test_login_disabled_keeps_the_historic_flow`, `::test_login_required_blocks_the_same_message`
- R45 → `test_identity_crypto.py::test_credential_status_five_states`, `::test_days_remaining_never_negative`, `test_identity_admin.py::test_create_client_hashes_password_and_reports_status`
- R46 → `test_identity_admin.py::test_renewing_a_revoked_credential_returns_conflict`, `test_identity_routes.py::test_get_renew_revoke_and_close_session`
- R47 → `test_identity_messages.py::test_missing_state_is_treated_as_awaiting_login`, `::test_login_required_blocks_the_same_message`
- R48 → `test_identity_login.py::test_unknown_user_wrong_password_and_staff_profile_share_401`, `test_identity_repository.py::test_login_attempts_count_prune_and_clear`
- R49 → `test_identity_crypto.py::test_identity_policy_valid_override_wins`, `::test_identity_policy_invalid_override_is_discarded`, `test_identity_link.py::test_issue_link_honors_policy_override`
- R50 → `test_identity_config.py::test_production_identity_requirements`

## Corrección de fallos (aplicada — SOLO estos 3, solo archivos de test)

Diagnóstico contra el spec: el código de aplicación cumple; los 3 fallos son de los tests.
NO modificar código de aplicación (`orchestrator/*.py`); solo los 3 tests indicados.

Estado: los 3 tests quedaron corregidos en este turno; no se tocó código de
aplicación. `./init.sh` lo ejecuta Claude tras esta sesión.

1. `services/orchestrator/tests/test_conversation_texts.py::test_identity_texts_do_not_gate_the_consent_flow`
   - Causa: el fixture `env` de ese archivo no siembra los textos del panel (greeting, rejected_reply,
     login_reminder, suspended_reply, unsupported_reply, confirm_button_reply, accepted_reply,
     notice_text, notice_version), así que `consent_configured` es False por esos campos, no por los de
     identidad. `consent_configured` (domain.py) ya excluye `login_link_label`/`session_closed_reply`
     como pide design.md (R9).
   - Arreglo: en el test, guardar primero `ConversationTexts` con todos los campos requeridos no vacíos
     (p. ej. `replace(get_conversation_texts(), notice_text=..., notice_version=..., accepted_reply=...,
     greeting=..., rejected_reply=..., login_reminder=..., suspended_reply=..., unsupported_reply=...,
     confirm_button_reply=..., login_link_label="", session_closed_reply="")`) y luego afirmar
     `consent_configured(...) is True`.

2. `services/orchestrator/tests/test_identity_link.py::test_accept_button_sends_text_and_link_to_same_channel_and_chat`
   - Causa: `POST /messages` responde `202` por contrato (main.py `status_code=202`); R1 no exige 200.
   - Arreglo: cambiar la aserción a `assert response.status_code == 202`.

3. `services/orchestrator/tests/test_identity_repository.py::test_two_concurrent_sessions_only_one_wins`
   - Causa: `results` se llena en orden de finalización, no por token; `results[0]` no corresponde a
     "h1". Cuando h2 gana y termina primero, el test toma h2 (usado) como "no usado". El FakeRepository
     ya devuelve `conflict` sin marcar `used_at` (R15, R27; design "el token queda sin usar").
   - Arreglo: guardar resultados por token, p. ej. `results: dict[str, str] = {}` y
     `results[token_hash] = repo.start_client_session(...)`; afirmar
     `sorted(results.values()) == ["conflict", "ok"]`, `unused = next(h for h, r in results.items() if r == "conflict")`,
     `repo.get_login_link(unused, NOW) is not None`, y además que el ganador sí quedó consumido
     (`repo.get_login_link(winner, NOW) is None`).

### Resultado de la corrección (verificado por Claude)
- Writer: primer intento cortado por timeout (900 s) sin cambios; el segundo intento terminó `done`.
- Archivos modificados: solo `tests/test_conversation_texts.py`, `tests/test_identity_link.py` y
  `tests/test_identity_repository.py`. No se tocó código de aplicación.
- `.venv/Scripts/python.exe -m pytest services/orchestrator -q -p no:cacheprovider`: sin fallos.
- `./init.sh`: exit 0, 2403 passed, 1 skipped, "Todos los tests pasan".
- Trazabilidad R1/R9/R15/R27 → tests corregidos, sin cambios respecto a la tabla anterior.

## Corrección de revisión (ciclo 1 — aplicación)

Atendidos los 3 cambios requeridos de `progress/review_identidad_credenciales.md`:

1. **R28 — actividad en `with_advisor`.** `_apply_identity_rules` ahora llama a
   `touch_client_session` siempre que haya sesión; solo la expiración se salta
   en `with_advisor` (R30). Test: `test_with_advisor_session_does_not_expire`
   ahora afirma que `last_activity_at` avanza en `with_advisor`.
2. **R30 — login con sesión en `with_advisor`.** `login_client` trata la sesión
   de un contacto en `with_advisor` como no expirada: no la cierra por `idle` y
   responde `SessionConflict` (409) con audit `login_conflict`. Test nuevo:
   `test_with_advisor_session_is_not_treated_as_idle_on_login`.
3. **Solo `UniqueViolation` es conflicto.** `PostgresRepository.start_client_session`
   hace rollback y solo devuelve `"conflict"` ante SQLSTATE `23505`; cualquier
   otro error de BD se relanza. Test nuevo:
   `test_postgres_start_session_only_maps_unique_violation_to_conflict`.
   (El repositorio usa pg8000, no psycopg: el helper `_is_unique_violation`
   reconoce el dict de pg8000 `args[0]["C"]` y también `sqlstate`/`pgcode`.)

Archivos tocados en esta corrección: `orchestrator/domain.py`,
`orchestrator/adapters/repository.py`, `tests/test_identity_messages.py`,
`tests/test_identity_login.py`, `tests/test_identity_repository.py`.

Trazabilidad actualizada: R28 → `test_message_with_session_updates_last_activity`,
`test_with_advisor_session_does_not_expire`; R30 → los anteriores más
`test_idle_session_is_closed_and_second_login_succeeds`,
`test_inactivity_ends_session_and_does_not_call_rag`,
`test_with_advisor_session_is_not_treated_as_idle_on_login`; R27 →
`test_schema_has_identity_tables_and_partial_indexes`,
`test_two_concurrent_sessions_only_one_wins`,
`test_postgres_start_session_only_maps_unique_violation_to_conflict`.

`./init.sh` lo ejecuta Claude tras esta sesión.

### Fallo tras la corrección de revisión (ciclo 1) — intento de corrección 1
`pytest services/orchestrator` falla en 1 test:
- `services/orchestrator/tests/test_identity_repository.py::test_postgres_start_session_only_maps_unique_violation_to_conflict`
  - `NameError: name 'joined' is not defined` en la última línea (`assert "ana" not in joined`, l.299).
  - Causa: el test nuevo se insertó en medio del test anterior (el que construye `joined` con
    `add_identity_audit` / `record_identity_login_failure` / `get_login_link`), y su última aserción
    `assert "ana" not in joined` quedó al final del test nuevo.
  - Arreglo: mover `assert "ana" not in joined` de vuelta al final del test anterior (tras
    `assert "%s" in joined`) y eliminarla del test nuevo. No tocar código de aplicación.
  - Aplicado: `assert "ana" not in joined` vuelve a `test_postgres_identity_sql_is_parameterized`
    y se eliminó del test nuevo. Solo se tocó
    `services/orchestrator/tests/test_identity_repository.py`; no se cambió código de aplicación.
    El resto de la corrección de revisión (R28, R30, solo `UniqueViolation` → conflicto) sigue
    presente en `domain.py` y `adapters/repository.py`. `./init.sh` lo ejecuta Claude tras esta sesión.

## Corrección de revisión (ciclo 1) — resultado verificado por Claude
- Punto 1 (R28): `domain.py` llama a `touch_client_session` siempre que hay sesión; `with_advisor`
  solo se salta la expiración. Test: `test_with_advisor_session_does_not_expire` afirma que
  `last_activity_at` avanza.
- Punto 2 (R30): `login_client` no cierra por `idle` la sesión de un contacto en `with_advisor` →
  `SessionConflict` 409 + audit `login_conflict`. Test nuevo en `test_identity_login.py`:
  `test_with_advisor_session_is_not_treated_as_idle_on_login`.
- Punto 3: `PostgresRepository.start_client_session` hace rollback y solo devuelve `"conflict"` ante
  SQLSTATE 23505 (`_is_unique_violation`); el resto se relanza. Nota: el repositorio usa pg8000, no
  psycopg, por eso se detecta por SQLSTATE (dict `C` de pg8000, `sqlstate`/`pgcode` de psycopg) en vez
  de `psycopg.errors.UniqueViolation`. Test nuevo:
  `test_postgres_start_session_only_maps_unique_violation_to_conflict`.
- Writer: 1 intento de aplicación + 1 corrección (test nuevo insertado dentro del anterior,
  `NameError: joined`). El segundo proceso del writer imprimió `done` y luego fue detenido por el límite
  de tiempo en segundo plano; el cambio ya estaba aplicado.
- `pytest services/orchestrator`: sin fallos. `./init.sh`: exit 0, 2405 passed, 1 skipped,
  "Todos los tests pasan".
