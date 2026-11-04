# Review — feature #40 memoria_por_cliente

**Veredicto:** APPROVED

`./init.sh` (revisor, 2026-11-04): exit 0 — 2663 passed, 1 skipped, 0 failed; "Entorno listo".

## Trazabilidad requirements ↔ tests
Todos los tests citados en `progress/impl_memoria_por_cliente.md` existen en
`services/orchestrator/tests/test_memory*.py` (comprobado por nombre) y pasan.
- R1, R3, R6, R9, R13, R19: [x] `test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory`
- R2, R4, R5: [x] `test_memory_flow.py::test_r2_r4_r5_escalation_replaces_summary_without_touching_memory`, `test_r2_failed_handover_does_not_summarize`, `test_r2_without_session_does_not_summarize`
- R7: [x] `test_r7_memory_disabled_does_not_call_llm_or_write_tables`
- R8: [x] `test_r8_empty_window_does_not_call_the_summarizer`
- R10: [x] `test_memory.py::test_r10_r42_session_window_is_inclusive_and_idle_is_exclusive`, `test_r49_two_clients_in_the_same_chat_keep_summaries_and_prompts_isolated`
- R11, R12: [x] `test_r11_parse_summary_answer_accepts_the_exact_shape`, `test_r11_invalid_summary_shapes_are_rejected`, `test_r11_r12_invalid_summary_leaves_tables_untouched`, `test_r12_llm_unavailable_leaves_tables_and_reports`
- R14, R48: [x] `test_r14_r48_memory_follows_the_client_to_a_new_session_and_channel`, `test_r14_r48_idle_session_closed_on_login_also_keeps_memory`
- R15, R16: [x] `test_r15_r16_sensitive_detection_covers_keywords_digits_and_email`, `test_r15_r16_five_or_fewer_digits_are_not_sensitive`
- R17: [x] `test_r17_clean_memory_items_trims_dedupes_truncates_and_caps`
- R18: [x] `test_r18_clean_summary_drops_sensitive_sentences_and_truncates`
- R20: [x] `test_r20_summary_prompt_forbids_sensitive_data_and_other_people`
- R21, R22: [x] `test_r21_r22_rag_prompt_includes_memory_and_previous_messages`, `test_r22_zero_context_messages_omits_history_but_keeps_memory`
- R23: [x] `test_r23_without_session_prompt_has_no_memory_blocks`
- R24, R49: [x] `test_r24_memory_of_another_client_is_never_included`, `test_r49_...isolated`
- R25: [x] `test_r25_router_and_sql_prompts_do_not_receive_memory`
- R26: [x] `test_r26_disabled_memory_keeps_the_old_prompt_byte_for_byte`
- R27–R30, R32–R34, R55, R56: [x] `test_memory_panel.py` (`test_r27_*`, `test_r28_r29_r55_r56_denials_do_not_read_memory`, `test_r28_forbidden_records_the_event`, `test_r30_r32_r33_r34_page_shows_only_the_case_client_and_escapes`, `test_r32_case_without_authenticated_client_shows_only_the_notice`)
- R31: [x] `test_r31_handover_link_stores_the_active_profile_or_none`
- R35–R46: [x] `test_memory_suppression.py` (`test_r36_*`, `test_r37_unknown_request_is_404`, `test_r38_request_not_pending_is_409`, `test_r39_active_session_is_closed_without_summarizing`, `test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted`, `test_r44_postgres_suppression_is_parameterized_and_atomic`, `test_r46_ai_tools_never_delete_memory_or_summaries`)
- R47, R53: [x] `test_r47_r53_purge_deletes_old_summaries_and_never_memory`, `test_r47_r53_postgres_purge_touches_summaries_not_client_memory`
- R50: [x] `test_r50_after_suppression_the_prompt_and_panel_do_not_show_old_memory`
- R51: [x] `./init.sh` verde (esta revisión)
- R52: [x] `test_memory_config.py::test_r52_memory_defaults_are_safe_and_off`, `test_r52_env_example_and_render_declare_the_new_variables`
- R54: [x] `test_r54_numeric_memory_variables_out_of_range_fail_at_start`, `test_r54_suppression_roles_must_be_admin_or_asesor`, `test_r54_suppression_roles_accept_admin_and_asesor`, `test_r54_empty_sensitive_keywords_fail`

## Tasks completas
- T0–T16: [x] (todas `[x]` en `specs/memoria_por_cliente/tasks.md`; T0 documentado: no existe `referencias/`)

## Revisión de código (puntos verificados)
- `domain.py:1030` `_memory_context`: solo usa `get_active_session_by_contact` → `profile_id` de la sesión; sin sesión o `MEMORY_ENABLED=false` devuelve `None` (R21–R24, R26).
- `domain.py:1073` `_summarize_session`: filtra sensibles antes del prompt, memoria solo con `trigger == "session_end"`, fallos → `memory_failed` sin escrituras, excepción genérica atrapada para no romper cierre/escalamiento (R11–R13, R15).
- `domain.py:2696` `advisor_client_memory`: `authorize` antes de cualquier lectura; `profile_id` del vínculo del caso (R27–R33).
- `domain.py:2747` `execute_suppression`: rol → existencia → `pending`; cierre con `"suppression"` y `notify=False`; auditoría (R35–R45).
- `repository.py:3145` Postgres: SQL parametrizado, `FOR UPDATE`, borrados y `UPDATE` en una transacción con rollback (R44, C3 sin SQL concatenado).
- Sin `print`/`eval`/`exec`/TODO en `memory.py`. Variables nuevas en `.env.example` (líneas 129–139).
- Pruebas previas ajustadas (`test_config`, `test_privacy_purge`, `test_consent_before_data`) solo amplían firmas/recuentos; ninguna aserción debilitada. La prueba de #37 sin `DELETE` en migraciones se respetó renombrando a `removed_counts`.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] una sola feature `in_progress` (#40, `feature_list.json:813`); `progress/current.md` describe la sesión.
- C3: [x] cambios solo en orchestrator; sin imports entre servicios; sin contratos nuevos; sin dependencias nuevas; sin código de terceros; sin secretos; SQL parametrizado.
- C4: [x] tests con fakes (`FakeRepository`, `ScriptedLLM`, `FakeHandover`, conexión falsa para Postgres); todos verdes.
- C5: [x] sin archivos temporales sospechosos; estado `in_progress` correcto a la espera de cierre por el leader (entrada de `progress/history.md` la añade el leader al cerrar).
- C6: [x] `specs/memoria_por_cliente/` completo; EARS aprobado en specreview; tasks `[x]`; cada R con test.

## Cambios requeridos
Ninguno.
