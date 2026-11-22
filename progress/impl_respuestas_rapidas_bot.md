# Implementación — #71 respuestas_rapidas_bot

## Resumen

- Nuevo dominio puro `quick_replies.py` con disparadores normalizados, prioridad,
  validación de imagen por firma binaria y construcción/degradación de bloques.
- Tablas `quick_replies` y `quick_reply_images`, con CRUD en `FakeRepository` y
  `PostgresRepository`; no se siembra contenido de negocio.
- Panel `/admin/respuestas-rapidas` (solo admin, CSRF, auditoría y formulario
  multipart sin JS) y media público `GET /media/respuestas/{id}`.
- Enganche en `_resolve_and_run` solo en estado `active`, después de guardarraíles,
  supresión, traspaso, frustración e intención de compra, y antes del router/RAG.
- `ChannelPolicy.supports_images` decide la imagen; sin soporte se degrada a
  enlace o texto. `QUICK_REPLY_IMAGE_MAX_BYTES` queda documentado en `.env.example`.
- Nota de la ruta pública de media añadida a `contracts/CONTRATOS.md`.

## Decisiones de implementación

- Los bloques se guardan como JSON serializable dentro de `QuickReply.blocks`
  (texto, imagen, opciones, enlace) para conservar el orden fijo y la imagen
  subida por `image_id`, sin fijar el dominio público en la base.
- Las opciones aceptan hasta 10 etiquetas de 20 caracteres; con 4–10 se emite
  `ListBlock` y con 1–3 `OptionsBlock`, respetando los límites del contrato.
- `image_id` se genera con `uuid.uuid4().hex` (32 hex) para la ruta de media.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_quick_replies_admin.py::test_admin_creates_and_lists_quick_replies`; `services/orchestrator/tests/test_quick_replies_schema.py::test_schema_declares_quick_replies_and_images_idempotently`
- R2 → `services/orchestrator/tests/test_quick_replies_admin.py::test_admin_creates_and_lists_quick_replies`
- R3 → `services/orchestrator/tests/test_quick_replies_admin.py::test_admin_updates_blocks_and_toggles_active`
- R4 → `services/orchestrator/tests/test_quick_replies_admin.py::test_admin_updates_blocks_and_toggles_active`
- R5 → `services/orchestrator/tests/test_quick_replies_admin.py::test_quick_reply_requires_at_least_one_trigger_and_one_block`
- R6 → `services/orchestrator/tests/test_quick_replies_admin.py::test_trigger_length_and_count_are_validated`; `services/orchestrator/tests/test_quick_replies_pure.py::test_parse_triggers_rejects_empty_short_long_and_too_many`
- R7 → `services/orchestrator/tests/test_quick_replies_admin.py::test_link_must_start_with_https`
- R8 → `services/orchestrator/tests/test_quick_replies_admin.py::test_priority_must_be_an_integer_between_zero_and_1000`
- R9 → `services/orchestrator/tests/test_quick_replies_admin.py::test_non_admin_cannot_read_or_modify_quick_replies`
- R10 → `services/orchestrator/tests/test_quick_replies_admin.py::test_quick_reply_routes_require_session`
- R11 → `services/orchestrator/tests/test_quick_replies_admin.py::test_csrf_is_required_for_every_write`
- R12 → `services/orchestrator/tests/test_quick_replies_admin.py::test_audit_records_success_and_validation_results`
- R13 → `services/orchestrator/tests/test_quick_replies_pure.py::test_pick_reply_normalizes_case_accents_and_punctuation`; `...::test_pick_reply_requires_whole_words`
- R14 → `services/orchestrator/tests/test_quick_replies_pure.py::test_pick_reply_uses_priority_then_oldest_then_id`
- R15 → `services/orchestrator/tests/test_quick_replies_pure.py::test_pick_reply_ignores_inactive_replies`
- R16 → `services/orchestrator/tests/test_quick_replies_pure.py::test_pick_reply_returns_none_without_match`; `services/orchestrator/tests/test_quick_replies_flow.py::test_no_match_keeps_the_normal_rag_flow`
- R17 → `services/orchestrator/tests/test_quick_replies_flow.py::test_active_conversation_answers_without_llm_or_rag`; `...::test_suppression_handover_and_frustration_win_over_quick_reply`
- R18 → `services/orchestrator/tests/test_quick_replies_flow.py::test_non_active_states_never_evaluate_quick_replies`
- R19 → `services/orchestrator/tests/test_quick_replies_flow.py::test_active_conversation_answers_without_llm_or_rag`
- R20 → `services/orchestrator/tests/test_quick_replies_flow.py::test_active_conversation_answers_without_llm_or_rag`
- R21 → `services/orchestrator/tests/test_quick_replies_flow.py::test_active_conversation_answers_without_llm_or_rag`
- R22 → `services/orchestrator/tests/test_quick_replies_flow.py::test_purchase_intent_still_creates_case_after_quick_reply`
- R23 → `services/orchestrator/tests/test_quick_replies_flow.py::test_repository_read_failure_continues_with_normal_flow`; `...::test_send_failure_continues_with_normal_flow`
- R24 → `services/orchestrator/tests/test_quick_replies_pure.py::test_validate_image_accepts_png_jpeg_and_webp_by_signature`; `services/orchestrator/tests/test_quick_replies_admin.py::test_uploaded_image_is_served_publicly_with_nosniff`
- R25 → `services/orchestrator/tests/test_quick_replies_pure.py::test_validate_image_rejects_empty_or_foreign_content`; `...::test_validate_image_rejects_too_large`; `services/orchestrator/tests/test_quick_replies_admin.py::test_invalid_uploaded_images_are_rejected`
- R26 → `services/orchestrator/tests/test_quick_replies_admin.py::test_uploaded_image_is_served_publicly_with_nosniff`; `contracts/tests/test_respuestas_rapidas_doc.py::test_media_de_respuestas_rapidas_es_publica_y_del_mismo_origen`
- R27 → `services/orchestrator/tests/test_quick_replies_admin.py::test_missing_or_invalid_image_id_returns_404`
- R28 → `services/orchestrator/tests/test_quick_replies_admin.py::test_external_image_url_must_be_https`
- R29 → `services/orchestrator/tests/test_quick_replies_admin.py::test_uploading_file_and_url_at_once_is_rejected`
- R30 → `services/orchestrator/tests/test_quick_replies_admin.py::test_upload_requires_https_public_base_url`
- R31 → `services/orchestrator/tests/test_quick_replies_admin.py::test_editing_other_fields_keeps_the_uploaded_image`; `...::test_replacing_or_removing_image_deletes_the_previous_file`
- R32 → `services/orchestrator/tests/test_quick_replies_flow.py::test_channel_with_images_receives_image_block`; `services/orchestrator/tests/test_quick_replies_pure.py::test_build_blocks_sends_image_when_channel_supports_it`
- R33 → `services/orchestrator/tests/test_quick_replies_flow.py::test_directory_without_images_degrades_to_link`; `...::test_unknown_channel_degrades_to_link`
- R34 → `services/orchestrator/tests/test_quick_replies_pure.py::test_build_blocks_uses_text_when_reply_already_has_a_link`
- R35 → `services/orchestrator/tests/test_quick_replies_pure.py::test_build_blocks_omits_uploaded_image_without_absolute_url`
- R36 → `services/orchestrator/tests/test_quick_replies_schema.py::test_no_business_content_is_seeded_in_schema_or_migrations`; `...::test_fake_repository_starts_without_quick_replies`

## Verificación

- T16 queda pendiente de que Claude ejecute `./init.sh`; este implementer no
  ejecuta comandos de shell. El mapa de arriba es el que usa la verificación.

## Intento 1 de init.sh: FALLA

1 failed, 4555 passed. `services/orchestrator/tests/test_quick_replies_flow.py::test_purchase_intent_still_creates_case_after_quick_reply`
(línea ~198): `[request] = env.handover.requests` -> ValueError, no hay solicitudes de handover.
Corregir el test o el código para que el aviso/caso de intención de compra siga funcionando tras una respuesta rápida, sin romper el resto.

## Corrección del fallo (intento 2)

Causa: el test no persistía el estado `active`. `env_factory` usa
`identity_login_required=False`, así que `_route_consented_text` fija `ACTIVE` en
una variable local cuando `get_conversation_state` devuelve `None`, pero no lo
guarda. `_create_case_after_intent` (#70) exige `get_conversation_state` en
`ACTIVE`/`NO_ACCESS`, por lo que no abría el caso. El flujo normal de #70 ya
parte de un estado persistido (`_prepare` en `test_purchase_intent_flow.py`).

Corrección: el test prepara el contacto y su estado `ACTIVE` en el repositorio
antes de publicar, igual que las pruebas de #70. No se cambia código de
aplicación ni el resto de la suite. El test sigue verificando R22: evento
`purchase_intent`, evento `quick_reply` y caso `user_request` creado tras la
respuesta rápida.

## Resultado final de init.sh (tras 1 corrección)

4556 passed, 1 skipped. `init.sh` verde. Trazabilidad R1..R36 -> test en la sección anterior.
