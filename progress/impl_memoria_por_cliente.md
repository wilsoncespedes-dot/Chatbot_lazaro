# Implementación — #40 memoria_por_cliente

## Resumen

Todo el cambio vive en `services/orchestrator`, más `.env.example`,
`render.yaml` y una línea de `docs/architecture.md`. No se tocaron contratos,
otros servicios ni dependencias.

- `orchestrator/memory.py` (nuevo, puro): ventana de sesión, filtro de datos
  sensibles, depuración de resumen/memoria, prompt del resumidor y parser.
- `orchestrator/domain.py`: contexto `<memoria>`/`<historial>` para el RAG,
  resumen al cerrar sesión y al escalar, `advisor_client_memory` y
  `execute_suppression`.
- `orchestrator/adapters/repository.py`: tablas `client_memory` y
  `conversation_summaries`, `profile_id` en `case_links`, columnas de ejecución
  en `suppression_requests`, métodos en Protocol/Fake/Postgres y purga de
  resúmenes.
- `orchestrator/config.py`: variables `MEMORY_*` y
  `SUPPRESSION_EXECUTOR_ROLES` con validación.
- `orchestrator/advisor_routes.py` / `advisor_panel.py`:
  `GET /asesor/cases/{case_id}/memoria`, plantilla escapada y enlace desde la
  lista de casos.

`MEMORY_ENABLED=false` sigue siendo el default; con la feature apagada el
prompt del RAG es byte a byte el anterior.

## T0 — Referencias

No existe `referencias/` en el repositorio, así que no se copió código de
terceros ni se modificó `THIRD_PARTY_NOTICES.md`. Prompt, filtro y esquema son
propios.

## Pruebas existentes actualizadas

- `tests/test_config.py::test_only_health_and_messages_routes_exposed`: añade
  la ruta nueva del panel.
- `tests/test_privacy_purge.py`: los recuentos esperados incluyen
  `conversation_summaries` y el orden del SQL de purga incorpora su borrado.
- `tests/test_consent_before_data.py`: el espía `link_case` acepta el parámetro
  opcional `profile_id`; no cambia ninguna aserción.

Ninguna prueba previa se eliminó ni se debilitó.

## Trazabilidad R → test

| R | Test |
|---|---|
| R1 | `tests/test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory` |
| R2 | `tests/test_memory_flow.py::test_r2_r4_r5_escalation_replaces_summary_without_touching_memory`, `::test_r2_failed_handover_does_not_summarize`, `::test_r2_without_session_does_not_summarize` |
| R3 | `tests/test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory` |
| R4 | `tests/test_memory_flow.py::test_r2_r4_r5_escalation_replaces_summary_without_touching_memory` |
| R5 | `tests/test_memory_flow.py::test_r2_r4_r5_escalation_replaces_summary_without_touching_memory` |
| R6 | `tests/test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory` |
| R7 | `tests/test_memory_flow.py::test_r7_memory_disabled_does_not_call_llm_or_write_tables` |
| R8 | `tests/test_memory_flow.py::test_r8_empty_window_does_not_call_the_summarizer` |
| R9 | `tests/test_memory.py::test_r9_build_summary_prompt_labels_data_and_neutralizes_closing_tags`, `tests/test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory` |
| R10 | `tests/test_memory.py::test_r10_r42_session_window_is_inclusive_and_idle_is_exclusive`, `tests/test_memory_flow.py::test_r49_two_clients_in_the_same_chat_keep_summaries_and_prompts_isolated` |
| R11 | `tests/test_memory.py::test_r11_parse_summary_answer_accepts_the_exact_shape`, `::test_r11_invalid_summary_shapes_are_rejected`, `tests/test_memory_flow.py::test_r11_r12_invalid_summary_leaves_tables_untouched` |
| R12 | `tests/test_memory_flow.py::test_r11_r12_invalid_summary_leaves_tables_untouched`, `::test_r12_llm_unavailable_leaves_tables_and_reports` |
| R13 | `tests/test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory` |
| R14 | `tests/test_memory_flow.py::test_r14_r48_memory_follows_the_client_to_a_new_session_and_channel`, `::test_r14_r48_idle_session_closed_on_login_also_keeps_memory` |
| R15 | `tests/test_memory.py::test_r15_r16_sensitive_detection_covers_keywords_digits_and_email`, `::test_r15_r16_five_or_fewer_digits_are_not_sensitive` |
| R16 | `tests/test_memory.py::test_r15_r16_sensitive_detection_covers_keywords_digits_and_email`, `::test_r15_r16_five_or_fewer_digits_are_not_sensitive` |
| R17 | `tests/test_memory.py::test_r17_clean_memory_items_trims_dedupes_truncates_and_caps` |
| R18 | `tests/test_memory.py::test_r18_clean_summary_drops_sensitive_sentences_and_truncates` |
| R19 | `tests/test_memory_flow.py::test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory` |
| R20 | `tests/test_memory.py::test_r20_summary_prompt_forbids_sensitive_data_and_other_people` |
| R21 | `tests/test_memory_flow.py::test_r21_r22_rag_prompt_includes_memory_and_previous_messages` |
| R22 | `tests/test_memory_flow.py::test_r21_r22_rag_prompt_includes_memory_and_previous_messages`, `::test_r22_zero_context_messages_omits_history_but_keeps_memory` |
| R23 | `tests/test_memory_flow.py::test_r23_without_session_prompt_has_no_memory_blocks` |
| R24 | `tests/test_memory_flow.py::test_r24_memory_of_another_client_is_never_included`, `::test_r49_two_clients_in_the_same_chat_keep_summaries_and_prompts_isolated` |
| R25 | `tests/test_memory_flow.py::test_r25_router_and_sql_prompts_do_not_receive_memory` |
| R26 | `tests/test_memory_flow.py::test_r26_disabled_memory_keeps_the_old_prompt_byte_for_byte` |
| R27 | `tests/test_memory_panel.py::test_r27_memory_route_requires_a_session`, `::test_r27_unlinked_profile_is_403_without_authorizing`, `::test_r27_invalid_case_id_is_422`, `::test_r27_authorize_is_called_before_reading_memory` |
| R28 | `tests/test_memory_panel.py::test_r28_r29_r55_r56_denials_do_not_read_memory`, `::test_r28_forbidden_records_the_event` |
| R29 | `tests/test_memory_panel.py::test_r28_r29_r55_r56_denials_do_not_read_memory` |
| R30 | `tests/test_memory_panel.py::test_r30_r32_r33_r34_page_shows_only_the_case_client_and_escapes`, `::test_cases_page_links_to_each_case_memory` |
| R31 | `tests/test_memory_flow.py::test_r31_handover_link_stores_the_active_profile_or_none` |
| R32 | `tests/test_memory_panel.py::test_r32_case_without_authenticated_client_shows_only_the_notice` |
| R33 | `tests/test_memory_panel.py::test_r30_r32_r33_r34_page_shows_only_the_case_client_and_escapes` |
| R34 | `tests/test_memory_panel.py::test_r30_r32_r33_r34_page_shows_only_the_case_client_and_escapes` |
| R35 | `tests/test_memory_suppression.py::test_r36_asesor_role_can_execute_when_configured`, `::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted` |
| R36 | `tests/test_memory_suppression.py::test_r36_forbidden_actor_cannot_delete_anything`, `::test_r36_asesor_role_can_execute_when_configured` |
| R37 | `tests/test_memory_suppression.py::test_r37_unknown_request_is_404` |
| R38 | `tests/test_memory_suppression.py::test_r38_request_not_pending_is_409` |
| R39 | `tests/test_memory_suppression.py::test_r39_active_session_is_closed_without_summarizing` |
| R40 | `tests/test_memory_suppression.py::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted` |
| R41 | `tests/test_memory_suppression.py::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted` |
| R42 | `tests/test_memory_suppression.py::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted` |
| R43 | `tests/test_memory_suppression.py::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted` |
| R44 | `tests/test_memory_suppression.py::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted`, `::test_r44_postgres_suppression_is_parameterized_and_atomic` |
| R45 | `tests/test_memory_suppression.py::test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted` |
| R46 | `tests/test_memory_suppression.py::test_r46_ai_tools_never_delete_memory_or_summaries` |
| R47 | `tests/test_memory_suppression.py::test_r47_r53_purge_deletes_old_summaries_and_never_memory`, `::test_r47_r53_postgres_purge_touches_summaries_not_client_memory` |
| R48 | `tests/test_memory_flow.py::test_r14_r48_memory_follows_the_client_to_a_new_session_and_channel`, `::test_r14_r48_idle_session_closed_on_login_also_keeps_memory` |
| R49 | `tests/test_memory_flow.py::test_r49_two_clients_in_the_same_chat_keep_summaries_and_prompts_isolated`, `::test_r24_memory_of_another_client_is_never_included` |
| R50 | `tests/test_memory_suppression.py::test_r50_after_suppression_the_prompt_and_panel_do_not_show_old_memory` |
| R51 | Pendiente de la ejecución de `./init.sh` que hace Claude al cerrar la sesión. |
| R52 | `tests/test_memory_config.py::test_r52_memory_defaults_are_safe_and_off`, `::test_r52_env_example_and_render_declare_the_new_variables` |
| R53 | `tests/test_memory_suppression.py::test_r47_r53_purge_deletes_old_summaries_and_never_memory`, `::test_r47_r53_postgres_purge_touches_summaries_not_client_memory` |
| R54 | `tests/test_memory_config.py::test_r54_numeric_memory_variables_out_of_range_fail_at_start`, `::test_r54_suppression_roles_must_be_admin_or_asesor`, `::test_r54_suppression_roles_accept_admin_and_asesor`, `::test_r54_empty_sensitive_keywords_fail` |
| R55 | `tests/test_memory_panel.py::test_r28_r29_r55_r56_denials_do_not_read_memory`, `::test_r32_case_without_authenticated_client_shows_only_the_notice` |
| R56 | `tests/test_memory_panel.py::test_r28_r29_r55_r56_denials_do_not_read_memory` |

## Notas

- R55/R56 se prueban junto con las denegaciones de autorización en el panel.
- R51 queda a la espera de la verificación de `./init.sh` que ejecuta Claude
  (`progress/current.md` es propiedad del leader).

## Verificación — intento 1 (`./init.sh`, Claude)

La primera ejecución de OpenCode se cortó por límite de tiempo con T0–T15
marcadas; T16 pendiente. `./init.sh`: 2 failed, 2661 passed, 1 skipped.

Fallos a corregir (sin debilitar pruebas previas):

1. `tests/test_memory.py::test_r9_build_summary_prompt_labels_data_and_neutralizes_closing_tags`:
   `assert "</historial>" not in user` falla porque el propio envoltorio legítimo
   `...</mensaje></historial>` contiene la etiqueta. La aserción del test es
   incorrecta: debe comprobar que el contenido del cliente no inyecta cierres
   (p. ej. que `</historial>` aparece exactamente una vez y al final), no su
   ausencia total. Corregir el test nuevo (no `memory.py`, que ya neutraliza).
2. `tests/test_repository_schema.py::test_migrations_add_button_evidence_without_rewriting_history`
   (prueba previa de #37): `assert "DELETE" not in migrations.upper()` falla
   porque la migración nueva añade la columna `deleted_counts` a
   `suppression_requests`. No modificar esa prueba previa: renombrar la columna
   nueva (p. ej. `removed_counts` o `execution_counts`) en repository.py
   (Protocol/Fake/Postgres), tests y docs/spec donde aparezca, de modo que ninguna
   migración contenga la subcadena `DELETE`.

Después completar T16 (marcar `[x]` en tasks.md si docs y `.env.example` ya están).

## Verificación — intento 2 (corrección de los 2 fallos)

- Fallo 1 corregido en el propio test nuevo
  `tests/test_memory.py::test_r9_build_summary_prompt_labels_data_and_neutralizes_closing_tags`:
  ahora comprueba que el contenido del cliente no inyecta cierres
  (`</historial>` aparece una sola vez y al final; `</item>` una sola vez) y que
  las etiquetas del texto quedan neutralizadas (`[/historial`, `[/item`). No se
  tocó `memory.py`.
- Fallo 2 corregido renombrando la columna nueva de `suppression_requests` de
  `deleted_counts` a `removed_counts` en `repository.py` (dataclass, Fake,
  Postgres, migración, SELECT y UPDATE), en
  `tests/test_memory_suppression.py` y en `specs/memoria_por_cliente/design.md`.
  Así ninguna migración contiene la subcadena `DELETE` y la prueba previa de
  #37 sigue intacta.
- T16 marcada `[x]`: `docs/architecture.md` §4 y `.env.example` ya contienen lo
  previsto; la ejecución de `./init.sh` queda a cargo de Claude.

## Verificación — intento 2 (`./init.sh`, Claude)

Tras la corrección de OpenCode: `./init.sh` verde — 2663 passed, 1 skipped,
0 failed; "Entorno listo". R51 queda cubierto por esta ejecución. La tabla de
trazabilidad R → test está completa (R1–R56). `feature_list.json` sigue en
`in_progress` (no marcado `done`; pendiente de revisión).
