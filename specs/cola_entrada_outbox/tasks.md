# Tasks — #64 `cola_entrada_outbox`

Rutas relativas a `services/orchestrator/` salvo que se indique otra. Tests en
`services/orchestrator/tests/`.

- [x] T1 — `config.py`: 8 variables de §5 con rango y error que nombra la variable; `.env.example` con comentarios. Cubre: R36, R37.
- [x] T2 — `domain.py`/`queue.py`: entidades `InboundEntry`, `InboxRow`, `OutboxEntry`, `OutboxRow`, `FailedSend`, `DedupKey`; funciones puras `conversation_key`, `destination_key`, `mask_destination`, `compute_backoff`. Cubre: R8, R23, R30.
- [x] T3 — `adapters/repository.py`: esquema `inbox`/`outbox` con índices en `_SCHEMA`. Cubre: R40.
- [x] T4 — Protocolo `Repository` y `PostgresRepository`: `enqueue_inbound` (marca + insert en una transacción), `claim/finish/retry/fail_inbound` con el SQL de §4. Cubre: R1, R4, R5, R7, R9, R10, R12, R13, R14, R15.
- [x] T5 — `PostgresRepository`: `enqueue_outbound`, `add_message_with_outbox`, `claim/finish/retry/fail_outbound`, `list_failed_outbound` (sin `blocks`), `requeue_outbound`. Cubre: R17, R18, R20, R22, R26, R27, R28, R30, R31.
- [x] T6 — `FakeRepository`: mismas operaciones con `threading.Lock` y semántica idéntica (cabeza por clave, concesión vencida, atomicidad de `add_message_with_outbox` con fallo inyectable). Cubre: R5, R10, R20, R26, R27.
- [x] T7 — `adapters/outbox.py`: `OutboxGatewayClient`; `Adapters.outbound` con `__post_init__`. Cubre: R19, R21.
- [x] T8 — `domain.py`: sustituir `adapters.gateway.send*` por `adapters.outbound`; `_send` y envíos de asesor con `add_message_with_outbox`; retirar la rama inalcanzable `except ChannelRejected` de `advisor_send_template`. Cubre: R17, R18, R19, R21.
- [x] T9 — `queue.py`: `process_inbound`, `run_inbox_once` y `run_outbox_once` con backoff, tope de intentos y no reintento de `ChannelRejected`; logs sin datos personales. Cubre: R11, R12, R13, R14, R16, R22, R23, R24, R25, R41.
- [x] T10 — `workers.py`: `main(argv)` con modos `procesar_entrantes`/`enviar_salientes`, `--una-vez`, bucle con `WORKER_POLL_SECONDS`, captura de excepciones del bucle. Cubre: R35.
- [x] T11 — `main.py`: `POST /messages` encola con deduplicación transaccional, conserva la excepción de consentimiento, elimina `BackgroundTasks`, `_process` y `_process_channel`. Cubre: R1, R2, R3, R4, R5, R6, R7.
- [x] T12 — `envios_routes.py` y registro en `main.py`: `GET /admin/envios`, `POST /admin/envios/{id}/reintentar` con rol, CSRF y auditoría `outbox_retry`; enlace en la barra del panel. Cubre: R29, R30, R31, R32, R33, R34.
- [x] T13 — `purge_personal_data` y `delete_contact_content` (Postgres y Fake): borrar `inbox`/`outbox` y reportar `inbox`/`outbox` en `deleted`. Cubre: R38, R39.
- [x] T14 — `docker-compose.yml`: servicios `procesar_entrantes` y `enviar_salientes`. Cubre: R35.
- [x] T15 — `tests/fakes.py`/`conftest.py`: helper `drain_queues`; adaptar los tests existentes que leen `gateway.sent` tras `POST /messages` o esperan `ChannelRejected` síncrono, y listarlos en `progress/impl_cola_entrada_outbox.md`. Cubre: R2, R17, R25.
- [x] T16 — `test_cola_entrada.py`: `test_post_messages_enqueues_and_returns_202` (R1, R2), `test_post_messages_does_not_run_flow_in_request` (R2), `test_main_does_not_import_background_tasks` (AST, R3), `test_duplicate_returns_duplicate_without_row` (R4), `test_dedup_and_insert_roll_back_together` (R5), `test_consent_acceptance_runs_in_request` (R6), `test_unconsented_message_enqueued_without_dedup_mark` (R7), `test_inbox_row_stores_key_channel_kind_payload` (R8).
- [x] T17 — `test_worker_entrantes.py`: SQL con `FOR UPDATE SKIP LOCKED` y atómico (R9), orden por conversación (R10), despacho legacy/channel (R11), éxito → `done` y carga vacía (R12), reintento con backoff (R13), `failed` con motivo y carga vacía (R14), concesión vencida reclamada (R15), otras conversaciones siguen (R16).
- [x] T18 — `test_outbox_encolado.py`: respuesta del bot y mensaje en una transacción (R17), asesor/plantilla (R18), avisos sin mensaje (R19), fallo de outbox revierte el mensaje (R20), ninguna llamada a `gateway` fuera del worker (R21).
- [x] T19 — `test_worker_salientes.py`: entrega y `sent` con bloques vacíos (R22), backoff exponencial con jitter y tope (R23), `failed` al agotar intentos (R24), `ChannelRejected` sin reintento (R25), orden por destino (R26), concurrencia con hilos sin doble envío (R27), concesión vencida reenvía (R28).
- [x] T20 — `test_envios_fallidos_panel.py`: listado, orden y roles (R29, R33), sin texto ni destino completo (R30), reintento manual con CSRF (R31), auditoría `outbox_retry` en `ok`/`not_found`/`not_failed`/`forbidden` (R32), `404`/`409` sin cambios (R34).
- [x] T21 — `test_cola_retencion.py`: purga por corte con conteos `inbox`/`outbox` (R38) y supresión por contacto, conversación y destino (R39).
- [x] T22 — `test_cola_despliegue.py`: servicios de compose (R35), variables y defaults en `.env.example` y `Settings` (R36), rangos inválidos (R37), tablas e índices en el esquema (R40), logs/`last_error` sin datos personales con `caplog` (R41).
- [x] T23 — `contracts/CONTRATOS.md` y `contracts/tests/test_cola_doc.py`: sección «Cola de entrada y outbox» con `202`, al menos una vez, ventana de duplicado, bloqueo por orden y variables. Cubre: R42.
- [ ] T24 — Ejecutar `./init.sh`, completar `progress/impl_cola_entrada_outbox.md` con la trazabilidad R→test y los tests adaptados de T15. Cubre: R1–R42.
