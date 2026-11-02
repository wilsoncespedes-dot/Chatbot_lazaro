# Tasks — agrupacion_mensajes (#30)

Tests en `services/telegram_gateway/tests/`; cada docstring indica su `R<n>`.

- [ ] T1 — `config.py`: campos `message_grouping_*` y `privacy_accept_phrase` con defaults y validador. Cubre: R1, R2.
- [ ] T2 — `.env.example` y `render.yaml` (gateway): variables nuevas y `PRIVACY_ACCEPT_PHRASE`. Cubre: R3.
- [ ] T3 — `domain.py`: `BufferedMessage`, `ClaimedGroup`, `is_immediate`, `compute_due`, `must_flush_before`, `build_group_request`; `Adapters.buffer` opcional. Cubre: R5, R6, R7, R9, R14.
- [ ] T4 — `adapters/message_buffer.py`: `MessageBuffer`, `FakeMessageBuffer` (lock, reloj, TTL, `fail`) y `RedisMessageBuffer` con scripts Lua. Cubre: R8, R12, R18, R19, R22, R23, R27.
- [ ] T5 — `grouping.py`: `enqueue_text`, `flush_chat`, `flush_due` con reintentos/descarte y logs sin texto; `GroupingWorker`. Cubre: R4, R9, R10, R13, R17, R20, R21, R22, R24, R26.
- [ ] T6 — `main.py`: delegar la rama de texto en `grouping` cuando hay buffer y está activo; lifespan del worker; `build_default_adapters` crea `RedisMessageBuffer` si está activo. Cubre: R4, R15, R16, R25.
- [ ] T7 — `test_grouping.py` configuración: defaults, valores inválidos fallan, `.env.example` lista variables. Cubre: R1, R2, R3.
- [ ] T8 — Ventana: dos textos a 1 s → un envío tras vencer; mensaje a 2,1 s del anterior → grupo aparte; ráfaga continua se corta en `MAX_WAIT`; nada se envía antes del vencimiento. Cubre: R4, R5.
- [ ] T9 — Orden y forma: textos llegados desordenados se unen por `update_id` ascendente con `"\n"`; menor `update_id`, `received_at` del último. Cubre: R6, R7.
- [ ] T10 — Aislamiento y límites: chats A/B intercalados → dos grupos sin mezcla; otro usuario, mensaje 11 o > 4096 caracteres unidos fuerzan envío previo; texto único > 4096 no queda en buffer. Cubre: R8, R9, R10.
- [ ] T11 — Deduplicación: `update_id` repetido no entra al buffer; `append` repetido con dedup caído guarda una copia. Cubre: R11, R12.
- [ ] T12 — Inmediatos: `/responder`, `/cerrar`, `/start x` y la frase de aceptación (con mayúsculas/espacios) envían antes el buffer y luego el comando, sin concatenar; sin buffer previo solo el comando. Cubre: R13, R14.
- [ ] T13 — Compatibilidad: update sin texto → `NON_TEXT_REPLY` y buffer intacto; desactivado o sin buffer → envío directo (tests de #3 siguen verdes). Cubre: R15, R16.
- [ ] T14 — Fallos: buffer `fail=True` → envío individual y log con `update_id`; orquestador falla → `release` con intentos+1 y mismos mensajes; al llegar a `MAX_ATTEMPTS` o con `ValidationError` → descarte con log; `caplog` no contiene textos ni frase. Cubre: R17, R20, R21, R26.
- [ ] T15 — Concurrencia: 8 hilos llaman `flush_due`/`flush_chat` sobre el mismo `FakeMessageBuffer` → un solo envío; con grupo en vuelo no se reclama otro del mismo chat hasta `ack`. Cubre: R18, R19.
- [ ] T16 — Reinicio y caducidad: grupo reclamado sin `ack` se reenvía al vencer el lease con un `FakeMessageBuffer` y app nuevos; buffer/grupo expiran tras `BUFFER_TTL_SECONDS` simulados; claves Redis creadas con TTL (stub de cliente que captura argumentos de los scripts). Cubre: R22, R23.
- [ ] T17 — Worker: excepción en `flush_due` se registra y el bucle sigue; `TestClient` como contexto arranca y para el worker. Cubre: R24, R25.
- [ ] T18 — Test opcional `@pytest.mark.integration` de `RedisMessageBuffer` contra Redis real (excluido por defecto). Cubre: R18, R23.
- [ ] T19 — Ejecutar `./init.sh` y documentar trazabilidad en `progress/impl_agrupacion_mensajes.md`. Cubre: R1–R27.
