# Implementación — #64 `cola_entrada_outbox`

## Resumen

Se añadieron dos tablas en el Postgres del orquestador (`inbox` y `outbox`), dos
workers (`procesar_entrantes` y `enviar_salientes`) y el panel `/admin/envios`.
`POST /messages` deduplica e inserta en `inbox` en una sola transacción y responde
`202`; la aceptación de consentimiento vigente (#35) sigue procesándose dentro de
la petición. El dominio escribe la salida por `Adapters.outbound`
(`OutboxGatewayClient`) y el worker de salida es el único que llama al gateway.
Toda respuesta del bot o del asesor se guarda con su fila de `outbox` en la misma
transacción.

Archivos creados: `queue.py`, `workers.py`, `envios_routes.py`,
`adapters/outbox.py` y los tests nuevos indicados abajo.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_cola_entrada.py::test_post_messages_enqueues_and_returns_202`
- R2 → `.../test_cola_entrada.py::test_post_messages_does_not_run_flow_in_request`
- R3 → `.../test_cola_entrada.py::test_main_does_not_import_background_tasks`
- R4 → `.../test_cola_entrada.py::test_duplicate_returns_duplicate_without_row`
- R5 → `.../test_cola_entrada.py::test_dedup_and_insert_roll_back_together`
- R6 → `.../test_cola_entrada.py::test_consent_acceptance_runs_in_request`
- R7 → `.../test_cola_entrada.py::test_unconsented_message_enqueued_without_dedup_mark`
- R8 → `.../test_cola_entrada.py::test_inbox_row_stores_key_channel_kind_payload`
- R9 → `.../test_worker_entrantes.py::test_claim_sql_is_atomic_and_skips_locked`
- R10 → `.../test_worker_entrantes.py::test_order_by_conversation_and_done_clears_payload`
- R11 → `.../test_worker_entrantes.py::test_dispatches_legacy_and_channel`
- R12 → `.../test_worker_entrantes.py::test_order_by_conversation_and_done_clears_payload`
- R13 → `.../test_worker_entrantes.py::test_exception_retries_with_backoff`
- R14 → `.../test_worker_entrantes.py::test_failed_after_max_attempts_clears_payload`
- R15 → `.../test_worker_entrantes.py::test_expired_lease_is_reclaimed`
- R16 → `.../test_worker_entrantes.py::test_other_conversations_keep_flowing_while_one_retries`
- R17 → `.../test_outbox_encolado.py::test_bot_reply_and_message_share_a_transaction`
- R18 → `.../test_outbox_encolado.py::test_advisor_reply_is_enqueued` y `test_advisor_template_is_enqueued`
- R19 → `.../test_outbox_encolado.py::test_notice_without_message_is_enqueued`
- R20 → `.../test_outbox_encolado.py::test_outbox_failure_reverts_message` y `.../test_case_reply.py::test_reply_outbox_failure_returns_502_and_stores_nothing`
- R21 → `.../test_outbox_encolado.py::test_domain_does_not_call_gateway`
- R22 → `.../test_worker_salientes.py::test_delivers_and_marks_sent`
- R23 → `.../test_worker_salientes.py::test_backoff_is_exponential_with_jitter_and_cap` y `test_transient_failure_returns_pending`
- R24 → `.../test_worker_salientes.py::test_failed_after_max_attempts`
- R25 → `.../test_worker_salientes.py::test_channel_rejected_is_not_retried`
- R26 → `.../test_worker_salientes.py::test_order_by_destination`
- R27 → `.../test_worker_salientes.py::test_concurrent_workers_deliver_each_row_once`
- R28 → `.../test_worker_salientes.py::test_expired_sending_lease_is_redelivered`
- R29 → `.../test_envios_fallidos_panel.py::test_list_shows_failed_rows_most_recent_first`
- R30 → `.../test_envios_fallidos_panel.py::test_list_hides_text_and_full_destination`
- R31 → `.../test_envios_fallidos_panel.py::test_manual_retry_requires_csrf_and_requeues`
- R32 → `.../test_envios_fallidos_panel.py::test_manual_retry_requires_csrf_and_requeues` y `test_retry_not_found_and_not_failed`
- R33 → `.../test_envios_fallidos_panel.py::test_asesor_retry_is_forbidden_and_does_not_modify`
- R34 → `.../test_envios_fallidos_panel.py::test_retry_not_found_and_not_failed`
- R35 → `.../test_cola_despliegue.py::test_compose_defines_both_workers`
- R36 → `.../test_cola_despliegue.py::test_env_example_documents_queue_variables` y `test_settings_defaults`
- R37 → `.../test_cola_despliegue.py::test_invalid_queue_settings_name_the_variable`
- R38 → `.../test_cola_retencion.py::test_purge_deletes_old_queue_rows_and_reports_counts`
- R39 → `.../test_cola_retencion.py::test_delete_contact_content_removes_queues_by_key_contact_and_destination`
- R40 → `.../test_cola_despliegue.py::test_schema_creates_tables_and_indexes`
- R41 → `.../test_cola_despliegue.py::test_logs_do_not_contain_queue_personal_data`
- R42 → `contracts/tests/test_cola_doc.py`

## Tests existentes adaptados (T15)

- `tests/fakes.py`: helper `drain_queues(settings, adapters)` que ejecuta
  `run_inbox_once` y `run_outbox_once` hasta vaciar.
- `tests/conftest.py`: `Env.post`, `Env.present` y `Env.post_button` drenan la
  cola tras la petición para conservar la observación de `gateway`.
- Añadidas llamadas a `drain_queues` en:
  `test_multicanal_flow.py`, `test_multichannel_identity.py`,
  `test_canal_abierto.py`, `test_text_consent_telegram.py`,
  `test_case_reply.py`, `test_authorization.py`, `test_advisor_panel.py`
  (`_post`), `test_panel_reply.py` (`_post`), `test_chat_caso_asesor.py`,
  `test_panel_audit.py` (`_post`), `test_notes_isolation.py`,
  `test_saved_replies_advisor.py`, `test_panel_actions.py` (`_post`),
  `test_admin_templates.py`, `test_expiry_notices.py`, `test_messages.py`.
- `test_conversation_states.py`, `test_conversation_texts.py`,
  `test_admin_texts_versions.py`, `test_harness_flow.py` y
  `test_text_consent_telegram.py` envuelven `process_channel_message` para
  drenar la salida al invocarlo directamente.
- `test_identity_login.py`: el helper `_login` drena la cola tras el login
  para observar la bienvenida en `gateway` (R17).
- Cambios de semántica esperados por R17/R25:
  `test_messages.py::test_failed_send_keeps_message_and_pending_outbox`,
  `test_panel_reply.py::test_gateway_422_becomes_failed_outbox_row`,
  `test_case_reply.py::test_reply_outbox_failure_returns_502_and_stores_nothing`,
  `test_authorization.py::test_reply_allowed_persists_then_assigns_before_worker_delivery`,
  `test_expiry_notices.py` (entrega y reintento por outbox),
  `test_panel_suppression.py::test_notice_failure_is_visible_in_outbox`.
- Listados exactos actualizados por las tablas nuevas:
  `test_config.py` (rutas `/admin/envios`), `test_privacy_purge.py`
  (`deleted.inbox`/`deleted.outbox`).

## Notas

- La entrega es al menos una vez; la ventana de duplicado y el bloqueo por
  orden están documentados en `contracts/CONTRATOS.md`.
- `inbox`/`outbox` se vacían de contenido al llegar a estado terminal y se
  borran por retención (`purge_personal_data`) y por supresión
  (`delete_contact_content`).
- R42 documentado en la sección «Cola de entrada y outbox» del contrato.

## Fallo de init.sh (intento 1)

init.sh: 44 failed, 4114 passed. Causas identificadas:
1. `InboxRow` estaba definida dos veces en `services/orchestrator/orchestrator/domain.py`
   (~678 la del panel de bandeja y ~818 la nueva de la cola, que sombreaba a la
   primera) y rompía `test_panel_inbox.py`, `test_panel_live_*`,
   `test_panel_visual.py`, `test_tags.py`, `test_panel_reassign.py`,
   `test_memory_panel.py`, etc. (`TypeError: InboxRow.__init__() got an unexpected
   keyword argument 'case_id'`). Se renombró la de la cola a `InboundQueueRow`
   en domain.py, repository.py y queue.py; la del panel conserva su nombre.
2. `contracts/tests/test_cola_doc.py::test_documents_202_at_least_once_duplicate_window_and_order`:
   `contracts/CONTRATOS.md` debe contener literalmente `FOR UPDATE SKIP LOCKED`.
3. `test_identity_login.py` (IndexError en línea 84) y
   `test_text_consent_telegram.py::test_telegram_notice_registers_challenge_without_send_channel_blocks`:
   revisar tras corregir 1; adaptar a la semántica de outbox si persisten.
Ejecutar `python -m pytest services/orchestrator contracts` para verificar.

## Bloqueo original (resuelto)

Primera ejecución de init.sh: 44 fallos (ver sección anterior). Al delegar la
corrección, `scripts/run_opencode_writer.sh` falló con
`[WinError 2] El sistema no puede encontrar el archivo especificado`
(no encuentra el ejecutable de OpenCode desde esta sesión). No se editó código
de aplicación. Requiere que el leader/humano restablezca el acceso a `opencode`
en el PATH y relance la corrección.

Resuelto en la ronda 1: el escritor se relanzó y aplicó los cuatro cambios de
la sección siguiente. Queda pendiente que Claude ejecute `./init.sh` y registre
el resultado.

## Corrección (ronda 1)

Cambios aplicados sobre el fallo de `init.sh`:

1. Renombrada la entidad de la cola a `InboundQueueRow` en `domain.py`,
   `queue.py` y `adapters/repository.py` (protocolo, `FakeRepository` y
   `PostgresRepository`). La `InboxRow` del panel de bandeja conserva su nombre
   y su forma (`case_id`, `tags`, …), por lo que deja de haber sombreado.
2. `contracts/CONTRATOS.md`: la sección «Cola de entrada y outbox» contiene el
   literal `FOR UPDATE SKIP LOCKED` (antes estaba partido por un salto de línea).
3. `tests/test_identity_login.py`: el helper `_login` ejecuta `drain_queues`
   tras `login_client`, porque la bienvenida ahora sale por la cola de salida y
   no directamente por `gateway` (R17).
4. `tests/test_text_consent_telegram.py`: el caso del aviso sin
   `send_channel_blocks` pasa a verificar la semántica de outbox
   (`test_telegram_notice_registers_challenge_and_enqueues_notice`); el dominio
   ya no consulta las capacidades del gateway y la entrega la hace el worker.


## Fallo de init.sh (intento 2) - corrección a delegar (ronda 2)

Tras renombrar InboundQueueRow: 20 failed, 4140 passed. Fallos (pytest services/orchestrator):
- 14x IndexError (gateway.sent vacío): tests que observan el gateway sin drenar la cola; añadir
  `drain_queues` / adaptar a outbox en test_admin_texts_versions (closing_reply, topics_list),
  test_business_hours (3), test_canal_abierto (media_kinds unsupported, 3 telegram),
  test_harness_flow (r6, r21, r22, r23, r25, r32, r36), test_identity_admin (renewal, revoke).
- test_authorization::test_reply_allowed_persists_then_assigns_before_worker_delivery: `'assign' == 'send'` (orden esperado distinto).
- test_adapters::test_postgres_repository_uses_parameters_only: el DDL de outbox/inbox contiene
  literales con comillas simples (`DEFAULT 'pending'`); el test prohíbe `'` en SQL. Mover el default a parámetro o ajustar el DDL sin literal entre comillas (sin debilitar el test).
- test_consent_before_data::test_non_positive_sender_is_never_staff: assert 0 == 1 (gateway.sent vacío), mismo origen (falta drenar).
Verificar con `python -m pytest services/orchestrator -x -q` filtrando esos archivos. No tocar feature_list.json.

## Ronda 3 (intento 3)

La ronda 2 no cambió nada (los mismos 20 fallos). Prioriza: (a) test_adapters (quitar literales con comilla simple del DDL de inbox/outbox), (b) añadir drain_queues antes de leer gateway.sent en los tests listados (patrón ya usado en test_messages.py y fakes.drain_queues; en test_harness_flow/test_identity_admin/test_business_hours/test_consent_before_data/test_canal_abierto/test_admin_texts_versions), (c) test_authorization ajustar orden esperado. Ejecuta cada archivo con pytest para confirmar antes de terminar.

## Ronda 3 (aplicada)

Cambios de esta ronda, uno por causa del intento 2:

1. **test_adapters** — `_SCHEMA` de `inbox` y `outbox` ya no usa `DEFAULT 'pending'`
   (único literal con comillas simples del DDL). `status` queda `NOT NULL` y ambos
   INSERT (`enqueue_inbound`, `_insert_outbox_cursor`) siguen pasándolo explícito.
2. **Drain de la outbox** antes de leer `gateway.sent` en los tests que invocan el
   dominio directamente:
   - `test_business_hours.py`: `drain_queues` tras cada `_handover`.
   - `test_harness_flow.py`: `drain_queues` tras `execute_tool` en R6, R21, R22,
     R23, R25, R32 y R36.
   - `test_identity_admin.py`: `drain_queues` tras `renew_credential` y `revoke_credential`.
   - `test_admin_texts_versions.py`: tras `close_case` y tras `login_client`.
   - `test_consent_before_data.py`: al sustituir el repositorio también se
     reconstruye `adapters.outbound` sobre el `RecordingRepository`, de modo que
     el aviso encolado y el drenado usen el mismo repositorio.
3. **test_canal_abierto** — la respuesta no textual ya se entrega por la outbox con
   bloques del contrato también en Telegram; la prueba comprueba una única entrega
   (`channel_sent`) en lugar de exigir el envío histórico.
4. **test_authorization** — el wrapper de orden registra `send_channel_blocks`
   (el camino real del worker de salida) en vez de `send`, por lo que el orden
   observado es `authorize → persist → assign → send`.

Pendiente para Claude: ejecutar `./init.sh` y registrar el resultado en este
informe (T24 no se marca hasta esa verificación).


## Resultado de init.sh (final)

`bash ./init.sh`: 4161 passed, 1 skipped, exit 0 (tras 3 rondas de corrección vía OpenCode: 44 -> 20 -> 0 fallos). Trazabilidad R1..R42 -> test intacta (ver sección «Trazabilidad»). Nota: el writer solo funciona en Windows con `opencode.exe` real en el PATH (node_modules/opencode-ai/bin), no con el shim `opencode`.
