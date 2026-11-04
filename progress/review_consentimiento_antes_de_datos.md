# Review — feature #35 consentimiento_antes_de_datos

**Veredicto:** APPROVED

`./init.sh` verde según leader (2143 passed, 1 skipped). Reejecutados por el reviewer en
`services/orchestrator`: `test_consent_before_data.py`, `test_privacy.py`, `test_security.py`,
`test_accounts.py`, `test_config.py`: 123 passed.

## Trazabilidad requirements ↔ tests
- R1: [x] `test_consent_before_data.py::test_staff_reads_happen_before_any_write` (consultar, responder, start)
- R2: [x] `test_consent_before_data.py::test_non_positive_sender_is_never_staff` (no llama a `get_profile_by_telegram_user_id`)
- R3: [x] `test_consent_before_data.py::test_staff_reads_happen_before_any_write[start]`
- R4: [x] `test_accounts.py::test_get_link_token_role_returns_role_only_for_valid_tokens`, `::test_postgres_get_link_token_role_is_single_select`
- R5: [x] mismos dos tests (token/perfil sin cambios en fake; un único SELECT sin UPDATE/INSERT/DELETE en Postgres)
- R6: [x] `test_consent_before_data.py::test_linked_staff_commands_skip_privacy_gate` (asesor/admin × 4 comandos × con/sin config), `test_privacy.py::test_personal_routes_work_without_privacy_configuration`
- R7: [x] `test_linked_staff_commands_skip_privacy_gate`
- R8: [x] `test_start_with_staff_token_links_without_consent` (asesor, admin)
- R9: [x] `test_linked_staff_start_skips_gate`
- R10: [x] `test_unconsented_sender_leaves_no_personal_data`, `test_privacy.py::test_personal_routes_never_create_consent`, `test_security.py::test_security_unconsented_client_responder_reaches_no_other_client`
- R11: [x] `test_unconsented_sender_leaves_no_personal_data` (rag/llm/handover/db_query sin llamadas)
- R12: [x] `test_consented_non_staff_keeps_existing_authorization` (auditoría `forbidden`)
- R13: [x] `test_consented_non_staff_keeps_existing_authorization`, `test_security.py::test_security_unauthorized_client_responder_reaches_no_other_client`
- R14: [x] `test_consented_non_staff_keeps_existing_authorization` (`/responder` → `advisor_command_help`)
- R15: [x] `test_unconsented_sender_leaves_no_personal_data[start_client]`, `test_client_token_survives_until_acceptance`
- R16: [x] mismos (`used_at is None`, perfil sin `telegram_user_id`)
- R17: [x] `test_client_token_survives_until_acceptance`
- R18: [x] `test_unconsented_sender_leaves_no_personal_data` (7 rutas: texto libre, /consultar, /consultar mal formado, /responder, /cerrar, /responder mal formado, /start token cliente)
- R19: [x] `test_acceptance_after_any_route_only_adds_privacy_consent`
- R20: [x] `test_unconsented_sender_only_stores_update_id` (vía HTTP, `repo.processed == {1}`)
- R21: [x] `test_consented_client_free_text_unchanged`
- R22: [x] `test_notice_version_change_blocks_new_data` (texto libre y /consultar)
- R23: [x] `services/telegram_gateway/tests/test_webhook.py::test_dedup_key_stored_with_ttl` (existente)
- R24: [x] `services/telegram_gateway/tests/test_grouping.py::test_buffer_and_group_expire_after_ttl`, `test_message_buffer.py::test_ttl_expires_buffer_and_inflight_group` (existentes)

## Tasks completas
- T1–T26: [x] (todas marcadas en `specs/consentimiento_antes_de_datos/tasks.md`; T26 `./init.sh` ejecutado por el leader, verde)

## Verificaciones específicas
- Ninguna escritura antes del consentimiento: en `domain.py::process_message` (líneas ~881-910) los tres tipos de comando calculan la exención con `_is_linked_staff` y `get_link_token_role` (solo lectura) y llaman a `_privacy_gate` antes de `get_or_create_contact`; la ruta de texto libre conserva la compuerta previa. `_privacy_gate` solo escribe `add_privacy_consent` ante la frase de aceptación.
- Detección de personal solo lectura: `_is_linked_staff` solo usa `get_profile_by_telegram_user_id` (uid <= 0 corta sin consultar); `get_link_token_role` en fake (`repository.py` ~512) solo lee bajo lock; en Postgres (~1138) un único SELECT parametrizado.
- Tests existentes modificados:
  - `test_accounts.py`: solo se añadieron dos tests nuevos (T6, T7); ninguna aserción cambiada.
  - `test_config.py`: no modificado en el working tree (el informe lo menciona solo como fallo de entorno resuelto en `conftest.py`).
  - `test_privacy.py`: `test_personal_routes_never_create_consent` cambia «sin aviso» por «aviso ×4» (exigido por R10/R15 y T21; se mantiene `privacy_consents == []`); `test_personal_routes_work_without_privacy_configuration` vincula un asesor (T22) y añade aserción `link_failed_reply`. Sin aserciones eliminadas.
  - `test_security.py`: el atacante recibe consentimiento previo para seguir probando R13 con todas sus aserciones intactas; se añade un test nuevo para el caso sin consentimiento (R10/R11/R18). No se debilita la prueba de seguridad.
  - `conftest.py`: fixture autouse `_clear_settings_env` no listado en tasks, pero justificado en el informe (aislamiento de variables del shell); hace los tests más deterministas, no los debilita.
- Cambios fuera de alcance: `docs/proyecto.md` §11 lo pide T24 y la restricción de docs; `specs/privacidad_y_retencion_datos/requirements.md` (nota bajo R19) lo pide T25. Ambos en alcance.
- `contracts/`: sin cambios (`git status` vacío).

## Checkpoints
- C1: [x]
- C2: [x] (solo #35 en `in_progress`; `progress/current.md` describe la sesión)
- C3: [x] (sin dependencias nuevas, sin imports entre servicios, SQL parametrizado, sin `print`)
- C4: [x] (adaptadores falsos; prueba de seguridad por ruta presente)
- C5: [x] (pendiente de que el leader registre la sesión en `progress/history.md` al cerrar)
- C6: [x]

## Cambios requeridos
Ninguno.
