# Tasks — agrupacion_mensajes (#30)

Tests en `services/telegram_gateway/tests/`; cada docstring indica su `R<n>`.

- [x] T1 — `config.py`: campos `message_grouping_*` y `message_grouping_accept_phrase` con defaults y validador. Cubre: R1, R2.
- [x] T2 — `.env.example`, `render.yaml` y `docs/despliegue.md`: variables nuevas; mapear `MESSAGE_GROUPING_ACCEPT_PHRASE` desde el orquestador. Cubre: R3.
- [x] T3 — `domain.py`: `BufferedMessage`, `ClaimedGroup`, `is_immediate`, `compute_due`, `must_flush_before`, `build_group_request`; `Adapters.buffer` opcional. Cubre: R5, R6, R7, R9, R14.
- [x] T4 — `adapters/message_buffer.py`: `MessageBuffer`, `FakeMessageBuffer` (lock, reloj, TTL, `fail`) y `RedisMessageBuffer` con scripts Lua. Cubre: R8, R12, R18, R19, R23, R24, R29.
- [x] T5 — `grouping.py`: `enqueue_text`, `flush_chat`, `flush_due` con reintentos/descarte y logs sin texto; `flush_due` descarta y registra grupos reclamados con intentos agotados. Cubre: R4, R9, R10, R13, R17, R21, R22, R23, R25, R28.
- [x] T6 — `main.py`: delegar la rama de texto en `grouping` cuando hay buffer y está activo; lifespan del worker; `build_default_adapters` crea `RedisMessageBuffer` si está activo. Cubre: R4, R15, R16, R26, R27.
- [x] T7 — `test_grouping.py` configuración: defaults, valores inválidos fallan, `.env.example` lista variables. Cubre: R1, R2, R3.
- [x] T8 — Ventana: dos textos a 1 s → un envío tras vencer; mensaje a 2,1 s del anterior → grupo aparte; ráfaga continua se corta en `MAX_WAIT`; nada se envía antes del vencimiento. Cubre: R4, R5.
- [x] T9 — Orden y forma: textos llegados desordenados se unen por `update_id` ascendente con `"\n"`; menor `update_id`, `received_at` del último. Cubre: R6, R7.
- [x] T10 — Aislamiento y límites: chats A/B intercalados → dos grupos sin mezcla; otro usuario, mensaje 11 o > 4096 caracteres unidos fuerzan envío previo; texto único > 4096 no queda en buffer. Cubre: R8, R9, R10.
- [x] T11 — Deduplicación: `update_id` repetido no entra al buffer; `append` repetido con dedup caído guarda una copia. Cubre: R11, R12.
- [x] T12 — Inmediatos: `/responder`, `/cerrar`, `/start x` y la frase normalizada intentan enviar el buffer antes; si hay grupo en vuelo, el inmediato se envía individualmente de inmediato y se registra `grouping_inflight_race` con su `update_id`, sin texto personal en logs. Cubre: R13, R14, R20, R28.
- [x] T13 — Compatibilidad: update sin texto → `NON_TEXT_REPLY` y buffer intacto; desactivado o sin buffer → envío directo (tests de #3 siguen verdes). Cubre: R15, R16.
- [x] T14 — Fallos: buffer `fail=True` → envío individual y log con `update_id`; orquestador falla → `release` conserva intentos y mismos mensajes; al agotarse `MAX_ATTEMPTS` o con `ValidationError` → descarte con log; `caplog` no contiene textos ni frase. Cubre: R17, R21, R22, R28.
- [x] T15 — Concurrencia y límites en vuelo: 8 hilos reclaman el mismo grupo → un envío y no se reclama otro antes del `ack`; con grupo del chat X en vuelo, mensaje entrante que excede `MAX_MESSAGES` o 4096 caracteres se envía individualmente y registra `grouping_inflight_race` con `update_id`, sin incluir texto en `caplog`. Cubre: R18–R20, R28.
- [x] T16 — Reinicio y caducidad: grupo reclamado sin `ack` se reenvía al vencer el lease con un `FakeMessageBuffer` y apps nuevas, con cada reclamo sumando intento hasta `MAX_ATTEMPTS`; al expirar el lease tras agotar intentos, no hay nuevo envío y se registra descarte; buffer/grupo expiran tras `BUFFER_TTL_SECONDS` simulados; claves Redis creadas con TTL (stub de cliente que captura argumentos de los scripts). Cubre: R23, R24.
- [x] T17 — Worker y fake: excepción en `flush_due` se registra y el bucle sigue; `TestClient` verifica arranque (R26) y parada (R27). En `test_message_buffer.py` comprobar Protocol, append idempotente, no doble claim en vuelo, `release`/`ack`, vencimiento de lease y TTL simulados y que `fail=True` lanza `ConnectionError`. Cubre: R25–R29.
- [x] T18 — Test opcional `@pytest.mark.integration` de `RedisMessageBuffer` contra Redis real (excluido por defecto). Cubre: R18, R23.
- [x] T19 — Ejecutar `./init.sh` y documentar trazabilidad en `progress/impl_agrupacion_mensajes.md`. Cubre: R1–R29. `./init.sh`: 2041 passed, 1 skipped.
