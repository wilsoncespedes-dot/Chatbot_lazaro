# Implementación — id_cliente_y_bienvenida_canales (#73)

## Resumen

Feature implementada en `services/orchestrator`, sin cambios de contrato ni de otros
servicios.

- ID público `XXXX-XXXX` generado con `secrets` (`client_id.py`), guardado en
  `profiles.public_id` con índice único y backfill idempotente al arrancar.
- Mensaje solo-ID tras el login y comando de ID con sesión activa; el chat nunca
  resuelve un ID escrito por el usuario.
- ID y botón «Copiar» en ficha del caso, bandeja de casos/conversaciones,
  encabezado de conversación y lista de Clientes del admin, con script propio
  `/panel/copiar.js`.
- Búsqueda por ID en `/asesor/clientes?q=` y `/admin/clientes?q=`, tolerante a
  mayúsculas, espacios y guiones, con «ID no válido»/«Sin resultados» y sin
  secretos.
- Bienvenida de primer contacto con los canales activos y públicos, con enlace
  https opcional, tope de 10, orden alfabético y exclusión de simulados salvo
  ajuste.
- Formulario de canales con `public` y `contact_url` validados.
- `docs/especificacion.md` documenta el login configurable como posibilidad no
  implementada.

T20 queda pendiente de la ejecución de `./init.sh` por Claude; el resto de tasks
está marcado `[x]`.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_id_cliente.py::test_generate_public_id_format_and_alphabet`
- R2 → `services/orchestrator/tests/test_id_cliente.py::test_generate_public_id_uses_secrets_and_takes_no_arguments`
- R3 → `services/orchestrator/tests/test_id_cliente.py::test_create_client_stores_public_id_and_schema_has_unique_index`
- R3 → `services/orchestrator/tests/test_id_cliente.py::test_repository_rejects_a_repeated_public_id`
- R4 → `services/orchestrator/tests/test_id_cliente.py::test_create_client_retries_when_public_id_is_taken`
- R5 → `services/orchestrator/tests/test_id_cliente.py::test_create_client_raises_after_five_collisions`
- R6 → `services/orchestrator/tests/test_id_cliente.py::test_renew_revoke_and_close_session_keep_the_same_public_id`
- R7 → `services/orchestrator/tests/test_id_cliente.py::test_ensure_public_ids_backfills_without_changing_existing_ids`
- R8 → `services/orchestrator/tests/test_id_cliente.py::test_suppression_removes_the_public_id`
- R9 → `services/orchestrator/tests/test_id_cliente_chat.py::test_login_sends_the_public_id_as_its_own_message`
- R9 → `services/orchestrator/tests/test_id_cliente_chat.py::test_login_without_access_still_sends_the_public_id`
- R10 → `services/orchestrator/tests/test_id_cliente_chat.py::test_client_id_command_answers_with_intro_and_id`
- R11 → `services/orchestrator/tests/test_id_cliente_chat.py::test_client_id_command_requires_exact_equality`
- R12 → `services/orchestrator/tests/test_id_cliente_chat.py::test_client_id_command_without_session_follows_normal_flow`
- R13 → `services/orchestrator/tests/test_id_cliente_chat.py::test_writing_another_client_id_does_not_identify_or_query`
- R14 → `services/orchestrator/tests/test_id_cliente_chat.py::test_writing_another_client_id_does_not_identify_or_query`
- R15 → `services/orchestrator/tests/test_id_cliente_panel.py::test_case_detail_shows_id_with_copy_button`
- R16 → `services/orchestrator/tests/test_id_cliente_panel.py::test_case_inbox_shows_id_and_copy_button`
- R16 → `services/orchestrator/tests/test_id_cliente_panel.py::test_conversation_inbox_shows_id_and_copy_button`
- R17 → `services/orchestrator/tests/test_id_cliente_panel.py::test_conversation_header_and_admin_clients_show_id`
- R18 → `services/orchestrator/tests/test_id_cliente_panel.py::test_copy_script_is_same_origin_without_inline_handlers`
- R19 → `services/orchestrator/tests/test_id_cliente_panel.py::test_advisor_searches_by_normalized_id`
- R20 → `services/orchestrator/tests/test_id_cliente_panel.py::test_admin_filters_by_normalized_id`
- R21 → `services/orchestrator/tests/test_id_cliente.py::test_normalize_public_id_is_tolerant_but_rejects_ambiguous_characters`
- R21 → `services/orchestrator/tests/test_id_cliente_panel.py::test_advisor_searches_by_normalized_id`
- R21 → `services/orchestrator/tests/test_id_cliente_panel.py::test_admin_filters_by_normalized_id`
- R22 → `services/orchestrator/tests/test_id_cliente_panel.py::test_invalid_id_and_no_results_return_200_messages`
- R23 → `services/orchestrator/tests/test_id_cliente_panel.py::test_invalid_id_and_no_results_return_200_messages`
- R24 → `services/orchestrator/tests/test_id_cliente_panel.py::test_search_requires_a_panel_session`
- R25 → `services/orchestrator/tests/test_id_cliente_panel.py::test_search_never_shows_password_hash_or_unmasked_external_id`
- R26 → `services/orchestrator/tests/test_bienvenida_canales.py::test_first_contact_appends_public_channels_to_the_greeting`
- R27 → `services/orchestrator/tests/test_bienvenida_canales.py::test_block_lists_only_active_public_channels_with_name_icon_and_link`
- R28 → `services/orchestrator/tests/test_bienvenida_canales.py::test_block_lists_only_active_public_channels_with_name_icon_and_link`
- R29 → `services/orchestrator/tests/test_bienvenida_canales.py::test_block_excludes_simulated_channels_by_default_and_includes_on_demand`
- R30 → `services/orchestrator/tests/test_bienvenida_canales.py::test_block_excludes_simulated_channels_by_default_and_includes_on_demand`
- R31 → `services/orchestrator/tests/test_bienvenida_canales.py::test_empty_block_returns_empty_string`
- R32 → `services/orchestrator/tests/test_bienvenida_canales.py::test_first_contact_without_directory_sends_greeting_without_list`
- R33 → `services/orchestrator/tests/test_bienvenida_canales.py::test_block_is_alphabetical_and_capped_at_ten_channels`
- R34 → `services/orchestrator/tests/test_bienvenida_canales.py::test_channel_form_saves_public_flag_and_contact_url`
- R34 → `services/orchestrator/tests/test_bienvenida_canales.py::test_channel_form_clears_public_flag_and_rejects_invalid_contact_url`
- R35 → `services/orchestrator/tests/test_bienvenida_canales.py::test_channel_form_clears_public_flag_and_rejects_invalid_contact_url`
- R36 → `services/orchestrator/tests/test_bienvenida_canales.py::test_stored_contact_url_that_is_not_https_is_rendered_without_link`
- R37 → `services/orchestrator/tests/test_docs_login_configurable.py::test_spec_documents_configurable_login_as_possibility`

## Corrección del fallo de init.sh (intento 1)

`test_first_contact_without_directory_sends_greeting_without_list` recibía 502
porque la compuerta HTTP `_text_pending` (`consent_text_pending`) consultaba el
directorio para cualquier texto antes de encolar, y el worker también lo
consultaba al armar el aviso. R32 exige enviar el saludo sin la lista cuando el
directorio no responde.

Cambios:

- `consent_text_pending` primero comprueba si el texto es la frase de
  aceptación/rechazo y solo entonces consulta el directorio. Un saludo normal ya
  no falla cerrado; una posible decisión de consentimiento sigue respondiendo
  `upstream_error` y sin encolar (no se arriesga la evidencia).
- Nuevo `_pre_consent_policy` en `domain.py`: si el directorio no está
  disponible usa `default_policy` para que el aviso de primer contacto salga sin
  la lista (R32), usado por `_notify_consent_prompt` y `_handle_pre_consent_text`.
- `test_post_messages_answers_upstream_error_when_directory_is_down` (#65) usa
  ahora la frase de aceptación como texto: conserva la garantía de fallar
  cerrado cuando el mensaje podría ser la decisión de consentimiento, sin
  contradecir R32 para el primer contacto.


## Resultado de init.sh (tras corrección)
4618 passed, 1 skipped. Entorno listo. Trazabilidad R<n> -> test según tabla del informe (test_bienvenida_canales.py y demás).
