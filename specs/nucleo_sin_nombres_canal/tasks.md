# Tasks — #65 `nucleo_sin_nombres_canal`

Orden: contrato → gateway → orquestador (directorio, política, ventana,
consentimiento, entrada, migración, barrido) → flujo completo → docs.

- [x] T1 — Añadir `CONSENT_MODES`, `DEFAULT_CONSENT_MODE`, `ChannelInfo.capabilities` y la validación de `consent_mode` en `contracts/lazaro_contracts/channel_registry.py`; exportar en `__init__.py`. Cubre: R1, R5.
- [x] T2 — Documentar `capabilities` y `config.consent_mode` en `contracts/CONTRATOS.md` y retirar el texto temporal de la guarda de `POST /messages`. Cubre: R9, R28.
- [x] T3 — Test `contracts/tests/test_capacidades_canal_info.py` (campo opcional, `consent_mode` inválido, documentación). Cubre: R1, R5, R9.
- [x] T4 — Añadir `default_capabilities` a `ChannelFactory` y a los cuatro adaptadores de `telegram_gateway/adapters/channels/`; usarlo en `ChannelService._info`. Cubre: R2, R3, R4.
- [x] T5 — Añadir `ChannelSeed.config`, semillas con `consent_mode` y la siembra idempotente en `PostgresChannelRepository` y `FakeChannelRepository`. Cubre: R6, R7, R8.
- [x] T6 — Test `services/telegram_gateway/tests/test_canales_capacidades.py` (capacidades de whatsapp/telegram, tipo desconocido, siembra nueva, relleno y no sobrescritura). Cubre: R2, R3, R4, R6, R7, R8.
- [x] T7 — Crear `orchestrator/channels.py` (`ChannelPolicy`, `policy_from_info`, `default_policy`) y `orchestrator/legacy.py` (`LEGACY_CHANNEL`, `legacy_from_normalized`, `legacy_chat_id`). Cubre: R11, R12, R13, R14, R36.
- [x] T8 — Crear `adapters/channels.py` (`ChannelDirectory`, `HttpChannelDirectory` con TTL y copia obsoleta, `FakeChannelDirectory` sin nombres de canal y con `default_infos` vacío) y `channel_directory_ttl_seconds` en `config.py`/`.env.example`; añadir `default_channel_infos()` en `tests/fakes.py` y el fixture `autouse` en `tests/conftest.py` que puebla `FakeChannelDirectory.default_infos`. Cubre: R10, R15, R16, R17.
- [x] T9 — Añadir `Adapters.channels`, `channel_policy()` y cablear `HttpChannelDirectory` en `build_default_adapters`; convertir `ServiceUnavailable` del directorio en `UpstreamError` en `POST /messages`. Cubre: R10, R18.
- [x] T10 — Test `test_directorio_canales.py` (HTTP con token, derivación de política, caché, copia obsoleta, sin copia, id ausente, `upstream_error`). Cubre: R10–R18.
- [x] T11 — Reescribir `channel_window` en `panel.py` para recibir `ChannelPolicy` y sustituir todas las comparaciones de ventana/plantilla de `domain.py` (avisos, respuesta de asesor, caducidad, casos vencidos). Cubre: R19, R20, R21.
- [x] T12 — Test `test_ventana_por_capacidades.py` (canal con ventana abierta/cerrada/sin mensaje, canal sin ventana, plantilla y `window_closed`, canal nuevo con ventana). Cubre: R19, R20, R21.
- [x] T13 — Sustituir `TEXT_CONSENT_CHANNELS` por `policy.consent_mode` en el aviso, el desafío y `consent_text_pending(message, settings, adapters)`; retirar la constante de `privacy.py`. Cubre: R22, R23, R24, R25.
- [x] T14 — Test `test_consentimiento_por_ajuste.py` (modo `texto`, modo `boton`, frase en canal `boton`, canal ausente = `texto`). Cubre: R22, R23, R24, R25.
- [x] T15 — Retirar `ATTENDED_CHANNELS` e `INBOX_CHANNELS`; validar el filtro de bandeja y generar sus opciones desde `list_policies()` en `domain.py`/`advisor_panel.py`. Cubre: R26, R27, R28, R29, R30.
- [x] T16 — Mover `_legacy_from_normalized` y `legacy_from_normalized` a `legacy.py` (sin duplicar) y sustituir los literales de `main.py`, `queue.py`, `outbox.py`, `gateway.py`, `domain.py` y `repository.py` por `LEGACY_CHANNEL`/`legacy_chat_id`. Cubre: R36, R37, R38.
- [x] T17 — Añadir columna `canal_id` en `contacts` y `messages`, la migración idempotente y su escritura en los `INSERT` de Postgres y del repositorio falso. Cubre: R31, R32, R33, R34, R35.
- [x] T18 — Test `test_canal_id_migracion.py` (alta de contacto y mensaje con `canal_id`, backfill con SQL en conexión falsa, segunda ejecución sin cambios, conservación de filas de `telegram` y `whatsapp`). Cubre: R31–R35.
- [x] T19 — Test `test_nucleo_sin_nombres.py` (barrido AST de literales y de importadores de `LEGACY_CHANNEL`). Cubre: R36, R37.
- [x] T20 — Test `test_nucleo_canal_nuevo.py`: flujo completo con `simulado` (consentimiento, login, bot, escalamiento, respuesta del asesor por el mismo canal y destino), aceptación en `POST /messages`, rechazo de `direction` saliente y regresión del flujo histórico de Telegram. Cubre: R28, R29, R30, R38, R39, R40, R41, R42.
- [x] T21 — Adaptar solo los tests existentes que importan lo retirado o asertan el rechazo temporal; listarlos en `progress/impl_nucleo_sin_nombres_canal.md` junto al mapa de trazabilidad. Cubre: R28, R43.
- [x] T22 — Ejecutar `./init.sh` y la batería de `services/orchestrator`, `services/telegram_gateway` y `contracts`; dejar todo en verde. Cubre: R43.
