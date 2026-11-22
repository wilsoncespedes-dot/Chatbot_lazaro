# Impl #65 nucleo_sin_nombres_canal

Writer: Claude (sesión principal), autorizado por el dueño el 2026-11-21 porque la
cuota de OpenCode Go se agotó y el writer quedó colgado. Se siguió
`specs/nucleo_sin_nombres_canal/tasks.md` (T1–T22) sin cambiar el spec.

## Trazabilidad

| Req | Código | Test |
|---|---|---|
| R1, R5 | `contracts/lazaro_contracts/channel_registry.py` (`ChannelInfo.capabilities`, `CONSENT_MODES`, `ChannelRequestConfig`) | `contracts/tests/test_capacidades_canal_info.py` |
| R9 | `contracts/CONTRATOS.md` (ChannelInfo, claves de `config`, S17, nota del simulado) | `test_capacidades_canal_info.py::test_contract_documents_capabilities_and_consent_mode` |
| R2–R4 | gateway `registry.py` (`default_capabilities`), `adapters/channels/*.py`, `adapters/telegram.py::telegram_capabilities`, `channel_service.py::_default_capabilities` | `services/telegram_gateway/tests/test_canales_capacidades.py` |
| R6–R8 | gateway `domain.py` (`ChannelSeed.config`, semillas), `adapters/channel_repository.py` (siembra `semilla \|\| config`) | `test_canales_capacidades.py` |
| R10–R17 | `orchestrator/channels.py`, `orchestrator/adapters/channels.py` (`HttpChannelDirectory`, `FakeChannelDirectory`), `config.py::channel_directory_ttl_seconds` | `tests/test_directorio_canales.py` |
| R18 | `main.py::_text_pending` (`ServiceUnavailable` → `UpstreamError`) | `test_directorio_canales.py::test_post_messages_answers_upstream_error_when_directory_is_down` |
| R19–R21 | `panel.py::channel_window(policy, …)`, `domain.py` (7 llamadas y 5 comparaciones → `channel_policy`) | `tests/test_ventana_por_capacidades.py`, `test_panel_pure.py` |
| R22–R25 | `domain.py` (`consent_text_pending(message, settings, adapters)`, `_consent_prompt`, `_notify_consent_prompt`, pre-consentimiento, botón antiguo); `privacy.py` sin `TEXT_CONSENT_CHANNELS` | `tests/test_consentimiento_por_ajuste.py` |
| R26, R27 | `domain.py::inbox_channel_options`, `advisor_inbox`; `advisor_panel.py` (`channel_choices`); `advisor_routes.py` | `tests/test_nucleo_canal_nuevo.py::test_inbox_channel_filter_comes_from_directory` |
| R28–R30 | `main.py` (sin `ATTENDED_CHANNELS`; solo 422 por `direction`) | `test_nucleo_canal_nuevo.py`, `test_simulator_guard.py` |
| R31–R35 | `adapters/repository.py` (5 migraciones `canal_id` al final de `_MIGRATIONS`, INSERT de contactos/mensajes, `FakeRepository.contact_canal_ids`, `StoredMessage.canal_id`) | `tests/test_canal_id_migracion.py` |
| R36, R37 | `orchestrator/legacy.py` (`LEGACY_CHANNEL`, `legacy_from_normalized`, `legacy_chat_id`, `is_legacy`); literales sustituidos en `main.py`, `queue.py`, `domain.py`, `adapters/{repository,outbox,gateway}.py`, `advisor_panel.py` | `tests/test_nucleo_sin_nombres.py` |
| R38–R42 | flujo existente sin nombres de canal | `test_nucleo_canal_nuevo.py` |
| R43 | — | baterías completas en verde (ver abajo) |

## Decisiones dentro del spec

- `consent_mode` se valida solo en peticiones (`ChannelRequestConfig` en
  `ChannelCreateRequest`/`ChannelUpdateRequest`); `ChannelInfo` sigue aceptando
  cualquier valor guardado, que el orquestador trata como `texto` (S3).
- `default_capabilities(cls, config=None)`: el simulado devuelve las capacidades
  de su `config.capabilities` si son válidas (así un canal simulado puede
  declararse con ventana, S4); el resto ignora `config`.
- `canal_id` de mensajes en Postgres: `(SELECT channel FROM contacts WHERE id = %s)`,
  sin cambiar firmas de `add_message`.
- `legacy.is_legacy()` se añadió como ayuda junto a `legacy_chat_id`; los textos
  visibles «WhatsApp» de errores del panel se conservan (no son literales exactos).

## Tests existentes adaptados (T21)

- `contracts/tests/test_canal_simulado_contrato.py`: la nota temporal «Hasta #65 /
  ATTENDED_CHANNELS / 422» pasa a «Desde #65 / rejected».
- `services/orchestrator/tests/test_simulator_guard.py`: la guarda ya no existe;
  el mensaje simulado recibe 202.
- `services/orchestrator/tests/test_simulator_page.py`: la página ya no muestra la
  nota «Hasta #65».
- `services/orchestrator/tests/test_canal_abierto.py`: `test_post_messages_rejects_unattended_channel`
  → `test_post_messages_accepts_any_valid_channel` (202 y respuesta por ese canal).
- `services/orchestrator/tests/test_panel_pure.py`: `channel_window` recibe la política.
- `services/orchestrator/tests/fakes.py` y `conftest.py`: `channel_info()`,
  `default_channel_infos()` y fixture `autouse` que puebla `FakeChannelDirectory.default_infos`.

## Verificación

- `contracts` + `services/telegram_gateway/tests`: 1457 passed, 1 skipped.
- `services/orchestrator/tests`: todo en verde.
- `./init.sh` (2026-11-21): 4224 passed, 1 skipped; entorno listo.
- Sin revisión del `reviewer` (el dueño pidió no lanzar subagentes); la feature sigue `in_progress` hasta que el dueño decida cerrarla.

## Deuda declarada

- La lectura sigue usando `contacts.channel`; leer por `canal_id` queda para #66/#67 (S5).
