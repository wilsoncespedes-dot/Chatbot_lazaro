# Implementación — consentimiento_antes_de_datos (feature #35)

Feature `in_progress`, spec aprobada. Implementadas T1–T26 y corregidos los 3 fallos de
`./init.sh` (ver «Corrección aplicada»). `./init.sh` en verde; pendiente de revisión.

## Resumen

- **Repositorio (`orchestrator/adapters/repository.py`)**: `get_link_token_role`
  de solo lectura en el Protocol, `FakeRepository` y `PostgresRepository` (un único
  `SELECT` con `used_at IS NULL` y `expires_at > now`).
- **Dominio (`orchestrator/domain.py`)**: `STAFF_ROLES`, `_is_linked_staff` (uid <= 0
  nunca consulta el repositorio) y `process_message` reordenado: primero se leen el
  perfil y, en `/start`, el rol del token; solo después la compuerta y, si pasa o el
  remitente es personal vinculado, `get_or_create_contact` y los manejadores actuales.
  La ruta de texto libre no cambia.
- **Pruebas**: nuevo `test_consent_before_data.py` (seguridad por ruta, `processed_updates`,
  aceptación posterior, orden lectura→escritura, personal, `/start`, no regresión y
  cambio de versión); `test_accounts.py` cubre `get_link_token_role` (fake y Postgres con
  cursor falso); se ajustaron T21 y T22 de `test_privacy.py` sin eliminar aserciones.
- **Docs**: `docs/proyecto.md` §11 documenta el consentimiento previo salvo personal
  vinculado y el tratamiento técnico mínimo (Redis `DEDUP_TTL_SECONDS`, búfer
  `MESSAGE_GROUPING_BUFFER_TTL_SECONDS`, `processed_updates` solo `update_id`). En
  `specs/privacidad_y_retencion_datos/requirements.md` R19 queda marcado como reemplazado
  por R6–R10 de la #35.
- **Sin cambios** en `contracts/`, `services/telegram_gateway/`, `services/handover/`,
  `main.py` ni el esquema SQL.

## Observaciones del spec review atendidas

1. R4 se implementa como una única regla de retorno en `get_link_token_role`.
2. T10 usa `env.post` (pasa por `mark_update_if_new`), no `process_message` directo.
3. T22 comprueba que `/start token-invalido` del personal vinculado envía
   `link_failed_reply` (S2/R9), no solo la ausencia del aviso.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_consent_before_data.py::test_staff_reads_happen_before_any_write`
- R2 → `services/orchestrator/tests/test_consent_before_data.py::test_non_positive_sender_is_never_staff`
- R3 → `services/orchestrator/tests/test_consent_before_data.py::test_staff_reads_happen_before_any_write`
- R4 → `services/orchestrator/tests/test_accounts.py::test_get_link_token_role_returns_role_only_for_valid_tokens`
  y `services/orchestrator/tests/test_accounts.py::test_postgres_get_link_token_role_is_single_select`
- R5 → `services/orchestrator/tests/test_accounts.py::test_get_link_token_role_returns_role_only_for_valid_tokens`
  y `services/orchestrator/tests/test_accounts.py::test_postgres_get_link_token_role_is_single_select`
- R6 → `services/orchestrator/tests/test_consent_before_data.py::test_linked_staff_commands_skip_privacy_gate`
  y `services/orchestrator/tests/test_privacy.py::test_personal_routes_work_without_privacy_configuration`
- R7 → `services/orchestrator/tests/test_consent_before_data.py::test_linked_staff_commands_skip_privacy_gate`
- R8 → `services/orchestrator/tests/test_consent_before_data.py::test_start_with_staff_token_links_without_consent`
- R9 → `services/orchestrator/tests/test_consent_before_data.py::test_linked_staff_start_skips_gate`
- R10 → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`
  y `services/orchestrator/tests/test_privacy.py::test_personal_routes_never_create_consent`
- R11 → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`
- R12 → `services/orchestrator/tests/test_consent_before_data.py::test_consented_non_staff_keeps_existing_authorization`
- R13 → `services/orchestrator/tests/test_consent_before_data.py::test_consented_non_staff_keeps_existing_authorization`
- R14 → `services/orchestrator/tests/test_consent_before_data.py::test_consented_non_staff_keeps_existing_authorization`
- R15 → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`
  y `services/orchestrator/tests/test_consent_before_data.py::test_client_token_survives_until_acceptance`
- R16 → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`
  y `services/orchestrator/tests/test_consent_before_data.py::test_client_token_survives_until_acceptance`
- R17 → `services/orchestrator/tests/test_consent_before_data.py::test_client_token_survives_until_acceptance`
- R18 → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_leaves_no_personal_data`
  y `services/orchestrator/tests/test_security.py::test_security_unconsented_client_responder_reaches_no_other_client`
  (R10 y R11 también)
- R19 → `services/orchestrator/tests/test_consent_before_data.py::test_acceptance_after_any_route_only_adds_privacy_consent`
- R20 → `services/orchestrator/tests/test_consent_before_data.py::test_unconsented_sender_only_stores_update_id`
- R21 → `services/orchestrator/tests/test_consent_before_data.py::test_consented_client_free_text_unchanged`
- R22 → `services/orchestrator/tests/test_consent_before_data.py::test_notice_version_change_blocks_new_data`
- R23 → `services/telegram_gateway/tests/test_webhook.py::test_dedup_key_stored_with_ttl`
  (existente, sin cambios)
- R24 → `services/telegram_gateway/tests/test_grouping.py::test_buffer_and_group_expire_after_ttl`
  y `services/telegram_gateway/tests/test_message_buffer.py::test_ttl_expires_buffer_and_inflight_group`
  (existentes, sin cambios)

## Corrección aplicada — fallos de `./init.sh` (intento 1)

`./init.sh` dio 3 fallos. Se corrigieron SOLO estos hallazgos; no se tocó código de
producción (`orchestrator/*.py`): ninguno era una regresión del código.

- **F1/F2 (aplicado)**: `services/orchestrator/tests/conftest.py` tiene el fixture
  `autouse=True` `_clear_settings_env` que borra del entorno, vía `monkeypatch.delenv`,
  todas las variables que mapean a campos de `Settings` (`Settings.model_fields` en
  mayúsculas). Los dos tests afectados no se modificaron.
- **F3 (aplicado)**: `test_security_unauthorized_client_responder_reaches_no_other_client`
  registra ahora el consentimiento vigente del atacante antes de los posts, conservando
  todas sus aserciones. Se añadió
  `test_security_unconsented_client_responder_reaches_no_other_client` (R10, R11, R18):
  sin consentimiento solo se envía el aviso al remitente y no hay llamadas a handover,
  RAG ni LLM ni filas de datos personales.

### F1 y F2 — fuga de variables de entorno del proceso hacia `Settings` (aislamiento de pruebas)

- `tests/test_accounts.py::test_issue_link_token_link_is_null_without_bot_username`:
  `link` sale `https://t.me/<bot>?start=...` en vez de `None`.
- `tests/test_config.py::test_notice_and_phrase_are_compared_normalized`:
  `settings.privacy_configured` sale `True` en vez de `False`.
- Causa: `Settings` (pydantic-settings, sin `env_file`) lee variables del entorno del
  proceso; el shell donde corre `init.sh` tiene definidas `TELEGRAM_BOT_USERNAME` y
  `PRIVACY_*`. Ni `config.py` ni `test_config.py` cambiaron en esta feature: las
  expectativas de los tests siguen siendo correctas.
- Corrección aplicada: en `services/orchestrator/tests/conftest.py` se añadió un fixture
  `autouse=True` que con `monkeypatch.delenv(..., raising=False)` elimina del entorno
  todas las variables que mapean a campos de `Settings` (itera
  `Settings.model_fields` y borra el nombre en mayúsculas), para que cada test use solo
  los valores que pasa explícitamente. Los dos tests no se modificaron.

### F3 — expectativa antigua que el spec cambia a propósito

- `tests/test_security.py::test_security_unauthorized_client_responder_reaches_no_other_client`:
  el atacante (uid 20, sin consentimiento, no personal) ahora recibe
  `PRIVACY_NOTICE_TEXT` en vez de `advisor_command_forbidden_reply`. Es lo que exigen
  R10/R11/R18 de la #35; R13 conserva `advisor_command_forbidden_reply` solo con
  consentimiento vigente.
- Corrección aplicada (solo en ese test, conservando su intención: el cliente no
  autorizado no alcanza a otro cliente):
  1. Antes de los posts existentes se registró consentimiento vigente del atacante con
     `env.repo.add_privacy_consent(20, env.settings.privacy_notice_version,
     notice_sha256(env.settings.privacy_notice_text), FIXED_NOW)` (con el import de
     `notice_sha256` de `orchestrator.privacy`). Así el resto del test sigue
     probando `advisor_command_forbidden_reply`, el evento `advisor_forbidden` y
     `advisor_command_failed_reply` sin cambios en sus aserciones.
  2. Se añadió el test
     `test_security_unconsented_client_responder_reaches_no_other_client` (R10, R11, R18):
     contacto 10/100 con `case-1` vinculado; remitente uid 30 / chat 300 sin
     consentimiento ni perfil envía `/responder case-1 Te escribo yo` por `env.post(...,
     consent=False)`; aserta que `env.gateway.sent == [(300, env.settings.privacy_notice_text)]`,
     que nada se envió al chat 100, que `env.handover` no recibió llamadas (se comprueban
     todas las listas de `FakeHandoverClient`), que no hay mensajes `advisor`, que
     `env.rag.calls == [] and env.llm.calls == []` y que
     `env.repo.privacy_consents == []`.

### Decisión por test

| Test | Decisión | Acción |
|---|---|---|
| `test_accounts.py::test_issue_link_token_link_is_null_without_bot_username` | Ni regresión ni cambio de spec: fuga de `TELEGRAM_BOT_USERNAME` del entorno del shell | Test intacto; fixture autouse en `conftest.py` |
| `test_config.py::test_notice_and_phrase_are_compared_normalized` | Ni regresión ni cambio de spec: fuga de `PRIVACY_*` del entorno del shell | Test intacto; mismo fixture |
| `test_security.py::test_security_unauthorized_client_responder_reaches_no_other_client` | Expectativa antigua cambiada a propósito por R10/R11/R18 (sin consentimiento → aviso) | Atacante con consentimiento previo (sigue probando R13 `advisor_command_forbidden_reply`); nuevo `test_security_unconsented_client_responder_reaches_no_other_client` |

### Archivos tocados en la corrección

- `services/orchestrator/tests/conftest.py` (fixture `_clear_settings_env`, autouse)
- `services/orchestrator/tests/test_security.py` (consentimiento previo + test nuevo)
- Sin cambios en código de producción en esta corrección.

Trazabilidad adicional: R10, R11, R18 →
`services/orchestrator/tests/test_security.py::test_security_unconsented_client_responder_reaches_no_other_client`;
R13 → `services/orchestrator/tests/test_security.py::test_security_unauthorized_client_responder_reaches_no_other_client`.

## Resultado de `./init.sh` (tras la corrección)

`2143 passed, 1 skipped` — «Todos los tests pasan», «Entorno listo». Modo: nocturno.
