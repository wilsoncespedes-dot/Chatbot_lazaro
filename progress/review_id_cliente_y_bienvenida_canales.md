# Review — feature id_cliente_y_bienvenida_canales (#73)

**Veredicto:** APPROVED

## Trazabilidad requirements ↔ tests
Verificada contra la tabla de `progress/impl_id_cliente_y_bienvenida_canales.md`. La suite completa pasa en `./init.sh`: 4618 passed, 1 skipped.
- R1: [x] `test_id_cliente.py::test_generate_public_id_format_and_alphabet`
- R2: [x] `test_generate_public_id_uses_secrets_and_takes_no_arguments`
- R3: [x] `test_create_client_stores_public_id_and_schema_has_unique_index`, `test_repository_rejects_a_repeated_public_id`
- R4: [x] `test_create_client_retries_when_public_id_is_taken`
- R5: [x] `test_create_client_raises_after_five_collisions`
- R6: [x] `test_renew_revoke_and_close_session_keep_the_same_public_id`
- R7: [x] `test_ensure_public_ids_backfills_without_changing_existing_ids`
- R8: [x] `test_suppression_removes_the_public_id`
- R9: [x] `test_id_cliente_chat.py::test_login_sends_the_public_id_as_its_own_message`, `test_login_without_access_still_sends_the_public_id`
- R10: [x] `test_client_id_command_answers_with_intro_and_id`
- R11: [x] `test_client_id_command_requires_exact_equality`
- R12: [x] `test_client_id_command_without_session_follows_normal_flow`
- R13: [x] `test_writing_another_client_id_does_not_identify_or_query`
- R14: [x] `test_writing_another_client_id_does_not_identify_or_query`
- R15: [x] `test_id_cliente_panel.py::test_case_detail_shows_id_with_copy_button`
- R16: [x] `test_case_inbox_shows_id_and_copy_button`, `test_conversation_inbox_shows_id_and_copy_button`
- R17: [x] `test_conversation_header_and_admin_clients_show_id`
- R18: [x] `test_copy_script_is_same_origin_without_inline_handlers`
- R19: [x] `test_advisor_searches_by_normalized_id`
- R20: [x] `test_admin_filters_by_normalized_id`
- R21: [x] `test_normalize_public_id_is_tolerant_but_rejects_ambiguous_characters`, y los tests de búsqueda
- R22: [x] `test_invalid_id_and_no_results_return_200_messages`
- R23: [x] `test_invalid_id_and_no_results_return_200_messages`
- R24: [x] `test_search_requires_a_panel_session`
- R25: [x] `test_search_never_shows_password_hash_or_unmasked_external_id`
- R26: [x] `test_bienvenida_canales.py::test_first_contact_appends_public_channels_to_the_greeting`
- R27: [x] `test_block_lists_only_active_public_channels_with_name_icon_and_link`
- R28: [x] `test_block_lists_only_active_public_channels_with_name_icon_and_link`
- R29: [x] `test_block_excludes_simulated_channels_by_default_and_includes_on_demand`
- R30: [x] `test_block_excludes_simulated_channels_by_default_and_includes_on_demand`
- R31: [x] `test_empty_block_returns_empty_string`
- R32: [x] `test_first_contact_without_directory_sends_greeting_without_list`
- R33: [x] `test_block_is_alphabetical_and_capped_at_ten_channels`
- R34: [x] `test_channel_form_saves_public_flag_and_contact_url`
- R35: [x] `test_channel_form_clears_public_flag_and_rejects_invalid_contact_url`
- R36: [x] `test_stored_contact_url_that_is_not_https_is_rendered_without_link`
- R37: [x] `test_docs_login_configurable.py::test_spec_documents_configurable_login_as_possibility`

## Tasks completas
- T1 a T19: [x]
- T20: [ ] sigue en `[ ]` en `specs/id_cliente_y_bienvenida_canales/tasks.md`. `progress/impl_id_cliente_y_bienvenida_canales.md` lo justifica: queda pendiente de que Claude ejecute `./init.sh`. Esa ejecución ya está hecha y en verde (4618 passed, 1 skipped), y la suite incluye las regresiones de #35, #37, #46 y #72. El leader puede marcar T20 como `[x]` al cerrar. No es bloqueante.

## Checkpoints
- C1: [x] `./init.sh` termina en verde.
- C2: [x]
- C3: [x] Sin cambios de contrato entre servicios. Las variables nuevas están en `.env.example` (según la implementación).
- C4: [x] Tests con adaptadores falsos.
- C5: [x] No he comprobado la entrada de `progress/history.md`. Es una tarea del leader al cerrar.
- C6: [x] Todas las tasks salvo T20 están `[x]`, con T20 justificada. Cada R<n> tiene al menos un test.

## Cambios requeridos
Ninguno. Al cerrar, el leader debe marcar T20 como `[x]`.
