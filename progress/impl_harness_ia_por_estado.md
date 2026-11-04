# Implementación #39 `harness_ia_por_estado`

## Resumen

- `orchestrator/states.py`: máquina de estados extraída para romper el ciclo de
  importación; `domain.py` la reexporta.
- `orchestrator/harness.py`: `ToolName`, `TOOL_NAMES`, `TOOL_MATRIX`,
  `authorize_tool`, `default_tool`, router (`build_router_prompt`,
  `parse_router_answer`, `RouterInvalid`), `args_sha256` y `matches_any`.
- `orchestrator/domain.py`: `execute_tool`, ejecutores `_tool_*`, guardrails,
  `_resolve_and_run`, supresión, datos propios del cliente, escalamiento y
  sesión pasan por la matriz; `_auto_handover` usa `escalar_a_asesor`.
- `orchestrator/adapters/client_data.py`: `PostgresClientDataQuery` (READ ONLY,
  `set_config` parametrizado, catálogo, rol y sonda RLS), `UnavailableClientData`
  y `FakeClientData`.
- `orchestrator/adapters/db_query.py`: `verify_view_catalog` compartida.
- `orchestrator/adapters/repository.py`: tablas `tool_calls` y
  `suppression_requests`, métodos en Protocol/Fake/Postgres y purga de
  `tool_calls`; la purga no toca las solicitudes de supresión.
- `config.py`, `.env.example` y `render.yaml`: variables nuevas, rangos y
  validaciones R35/R59/R63.
- `main.py`: construye `PostgresClientDataQuery` si `CLIENT_DATA_ENABLED`.
- `docs/consulta_bd.md` y `docs/architecture.md`: operación de RLS y matriz.
- Tests nuevos: `test_harness_matrix.py`, `test_harness_flow.py`,
  `test_client_data.py`, `test_harness_config.py`, `test_harness_eval.py` y
  `tests/data/harness_eval_cases.json`; se ajustaron las expectativas de purga.

T0: `referencias/` no existe en este repositorio, así que no hay piezas de
terceros que revisar ni que anotar en `THIRD_PARTY_NOTICES.md`.

## Trazabilidad

- R1 → `tests/test_harness_matrix.py::test_r1_r3_matrix_decision`, `test_r1_r2_matrix_is_complete_immutable_and_has_six_tools`
- R2 → `tests/test_harness_matrix.py::test_r1_r2_matrix_is_complete_immutable_and_has_six_tools`
- R3 → `tests/test_harness_matrix.py::test_r1_r3_matrix_decision`, `test_r3_unknown_tool_is_denied_in_every_state`
- R4 → `tests/test_harness_flow.py::test_r4_state_is_reread_from_the_repository_before_executing`
- R5 → `tests/test_harness_flow.py::test_r5_denied_tool_calls_no_adapter`
- R6 → `tests/test_harness_flow.py::test_r6_denied_router_tool_gets_the_fixed_reply`
- R7 → `tests/test_harness_flow.py::test_r7_r8_tool_call_row_has_hashes_and_not_message_text`
- R8 → `tests/test_harness_matrix.py::test_r8_args_sha256_is_canonical_and_hides_values`; `tests/test_harness_flow.py::test_r7_r8_tool_call_row_has_hashes_and_not_message_text`
- R9 → `tests/test_privacy_purge.py::test_r9_r42_purge_deletes_old_tool_calls_and_keeps_suppressions`, `test_postgres_purge_deletes_tool_calls_but_not_suppression_requests`
- R10 → `tests/test_harness_flow.py::test_r10_r18_r19_invalid_router_output_is_audited_and_falls_back`
- R11 → `tests/test_harness_flow.py::test_r11_r12_too_long_input_gets_fixed_reply_and_event`
- R12 → `tests/test_harness_flow.py::test_r11_r12_too_long_input_gets_fixed_reply_and_event`
- R13 → `tests/test_harness_flow.py::test_r13_r14_injection_is_logged_and_router_is_skipped`; `tests/test_harness_matrix.py::test_r11_r13_matches_any_normalizes_text`
- R14 → `tests/test_harness_flow.py::test_r13_r14_injection_is_logged_and_router_is_skipped`
- R15 → `tests/test_harness_matrix.py::test_r15_router_prompt_neutralizes_closing_tags`
- R16 → `tests/test_harness_flow.py::test_r16_valid_router_decision_executes_with_router_origin`
- R17 → `tests/test_harness_matrix.py::test_r17_router_prompt_lists_only_the_state_tools`, `test_r17_router_prompt_has_no_identity_data`
- R18 → `tests/test_harness_matrix.py::test_r18_parser_accepts_only_exact_schemas`, `test_r18_parser_rejects_everything_else`
- R19 → `tests/test_harness_matrix.py::test_r19_default_tool_only_for_active`; `tests/test_harness_flow.py::test_r10_r18_r19_invalid_router_output_is_audited_and_falls_back`, `test_r19_invalid_router_in_no_access_returns_suspended_reply`
- R20 → `tests/test_harness_flow.py::test_r20_suppression_keyword_wins_over_advisor_keyword`, `test_r20_router_disabled_uses_one_llm_call_for_rag`
- R21 → `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
- R22 → `tests/test_harness_flow.py::test_r22_client_data_without_session_does_not_call_any_adapter`
- R23 → `tests/test_harness_flow.py::test_r23_client_data_disabled_does_not_call_llm_or_adapter`
- R24 → `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
- R25 → `tests/test_harness_flow.py::test_r25_sql_outside_allowlist_is_rejected_without_running`
- R26 → `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
- R27 → `tests/test_client_data.py::test_r27_r28_order_and_cliente_id_only_as_parameter`, `test_query_error_always_rolls_back_and_closes`
- R28 → `tests/test_client_data.py::test_r27_r28_order_and_cliente_id_only_as_parameter`
- R29 → `tests/test_client_data.py::test_r29_r30_r31_first_use_checks_run_before_the_query`, `test_r29_invalid_catalog_fails_closed_without_querying`
- R30 → `tests/test_client_data.py::test_r30_superuser_or_bypassrls_fails_closed`
- R31 → `tests/test_client_data.py::test_r31_rls_probe_returning_a_row_fails_closed`
- R32 → `tests/test_harness_flow.py::test_r32_unavailable_adapter_returns_unavailable`, `test_r32_llm_failure_returns_unavailable`
- R33 → `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
- R34 → `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
- R35 → `tests/test_harness_config.py::test_r35_valid_client_data_config_starts`, `test_r35_empty_dsn_fails`, `test_r35_dsn_cannot_equal_database_url`, `test_r35_dsn_cannot_equal_db_query_dsn`, `test_r35_invalid_allowlist_schema_or_rls_setting_fails`
- R36 → `tests/test_harness_flow.py::test_r36_r38_r39_suppression_creates_row_links_case_and_replies`
- R37 → `tests/test_harness_flow.py::test_r37_second_request_reuses_the_pending_id`
- R38 → `tests/test_harness_flow.py::test_r36_r38_r39_suppression_creates_row_links_case_and_replies`
- R39 → `tests/test_harness_flow.py::test_r36_r38_r39_suppression_creates_row_links_case_and_replies`; `tests/test_harness_config.py::test_suppression_reply_requires_request_id_placeholder`
- R40 → `tests/test_harness_flow.py::test_r40_without_session_suppression_escalates_with_suppression_motive`
- R41 → `tests/test_harness_flow.py::test_r41_tools_never_delete_repository_rows`
- R42 → `tests/test_privacy_purge.py::test_r9_r42_purge_deletes_old_tool_calls_and_keeps_suppressions`, `test_postgres_purge_deletes_tool_calls_but_not_suppression_requests`
- R43 → `tests/test_harness_flow.py::test_r43_suppression_keywords_are_configurable_in_both_states`
- R44 → `tests/test_harness_flow.py::test_r44_r45_rag_uses_original_text_and_validates_citations`
- R45 → `tests/test_harness_flow.py::test_r44_r45_rag_uses_original_text_and_validates_citations`
- R46 → `tests/test_harness_flow.py::test_r46_advisor_keyword_escalates_with_user_request`
- R47 → `tests/test_harness_flow.py::test_r47_frustration_escalates_when_enabled`, `test_r47_frustration_disabled_keeps_the_rag_flow`
- R48 → `tests/test_harness_flow.py::test_r48_r50_repeated_failure_escalates_with_the_original_reason`, `test_r48_invalid_answer_streak_keeps_invalid_answer_reason`
- R49 → `tests/test_harness_flow.py::test_r46_advisor_keyword_escalates_with_user_request`, `test_r47_frustration_escalates_when_enabled`
- R50 → `tests/test_harness_flow.py::test_r46_advisor_keyword_escalates_with_user_request`, `test_r48_r50_repeated_failure_escalates_with_the_original_reason`
- R51 → `tests/test_harness_flow.py::test_r51_escalation_in_no_access_moves_to_with_advisor`
- R52 → `tests/test_harness_flow.py::test_r52_awaiting_login_text_invokes_the_link_tool`
- R53 → `tests/test_harness_flow.py::test_r53_router_logout_closes_the_session_with_a_new_link`
- R54 → `tests/test_harness_flow.py::test_r54_r61_without_consent_no_tool_rows_or_adapters`, `test_r54_r61_without_consent_on_a_normalized_channel`
- R55 → `tests/test_harness_flow.py::test_r55_router_is_never_called_in_non_eligible_states`
- R56 → `tests/test_harness_eval.py::test_r56_r62_attack_cases`, `test_r56_at_least_two_cases_per_category`
- R57 → `tests/test_client_data.py::test_fake_client_data_only_returns_rows_for_the_requested_client`; `tests/test_harness_eval.py::test_r56_r62_attack_cases` (casos `datos_texto_de_otro_cliente`, `sql_where_de_otro_cliente` y `router_args_con_cliente_ajeno`)
- R58 → `./init.sh` (lo ejecuta Claude al cerrar la sesión)
- R59 → `tests/test_harness_config.py::test_r59_defaults_are_safe`, `test_r59_env_example_declares_every_new_variable`
- R60 → `tests/test_harness_flow.py::test_r60_invalid_sources_are_rejected_with_the_fixed_reply`
- R61 → `tests/test_harness_flow.py::test_r54_r61_without_consent_no_tool_rows_or_adapters`, `test_r54_r61_without_consent_on_a_normalized_channel`
- R62 → `tests/test_harness_eval.py::test_r56_r62_attack_cases`
- R63 → `tests/test_harness_config.py::test_r63_numeric_variables_out_of_range_fail_at_start`

## Notas para la revisión

- T21 queda pendiente de la ejecución de `./init.sh` por Claude (el implementer
  no ejecuta shell); el mapa de trazabilidad ya está completo.

- No se añadieron rutas HTTP ni dependencias nuevas.
- Con `HARNESS_ROUTER_ENABLED=false` y `CLIENT_DATA_ENABLED=false` el flujo
  conserva las rutas por palabra clave y la herramienta por defecto de #37.
- `tool_calls` guarda solo el SHA-256 de los args y, en datos de cliente,
  `views`, número de filas y `sql_sha256`; nunca texto, SQL ni filas.
- La purga añade `deleted["tool_calls"]`; se actualizaron las expectativas
  existentes de ese diccionario.

## Fallo de `./init.sh` (intento de corrección 1)

- `pytest` aborta en colección: `services/orchestrator/tests/test_harness_flow.py:20`
  hace `from orchestrator.privacy import LinkBlock` y falla con
  `ImportError: cannot import name 'LinkBlock' from 'orchestrator.privacy'`.
  Importar `LinkBlock` desde su módulo real (p. ej. `lazaro_contracts`) y volver a
  ejecutar la suite completa del orquestador hasta que pase.
- Además (pytest con `--continue-on-collection-errors`):
  - `tests/test_harness_eval.py::test_r56_r62_attack_cases[datos_texto_de_otro_cliente|sql_where_de_otro_cliente|router_args_con_cliente_ajeno|sin_consentimiento_supresion|sin_consentimiento_inyeccion]`
    fallan en `test_harness_eval.py:65` con `AttributeError: 'Profile' object has no attribute 'profile_id'`
    (usar el atributo real del modelo `Profile`).
  - `tests/test_client_forward.py::test_not_assigned_follows_current_flow[keyword]`
    (test existente, línea 100): el flujo de palabra clave de asesor ahora emite un
    evento extra `('escalation', 'user_request')` antes de `('handover', 'user_request')`.
    Decidir según R46/R49 del spec: o el test existente compara eventos de forma que
    admita el nuevo evento de auditoría, o la ruta debe emitir los mismos eventos en
    ambas ramas comparadas. No romper la intención original del test (#36).

## Corrección 1 (aplicada)

- `tests/test_harness_flow.py` importa `LinkBlock` desde `lazaro_contracts`
  (su módulo real), no desde `orchestrator.privacy`.
- `tests/test_harness_flow.py` y `tests/test_harness_eval.py` usan `Profile.id`
  (`profile.id`) en lugar de `profile.profile_id`; `create_client_credential`
  devuelve el `Profile` de dominio con `id`.
- `domain._route_consented_text`, rama `with_advisor` con palabra clave de
  asesor: emite `escalation:user_request` antes de `_handover`, igual que la
  ruta por herramienta (R49). Así el re-traspaso conserva el mismo rastro de
  auditoría y el test de #16 `test_not_assigned_follows_current_flow[keyword]`
  compara ramas equivalentes sin debilitar ninguna aserción.

## Fallo de `./init.sh` (intento de corrección 2)

`./init.sh`: 2 failed, 2571 passed, 1 skipped. Fallan:

- `tests/test_harness_flow.py::test_r44_r45_rag_uses_original_text_and_validates_citations`
  (línea 315, `IndexError` en `env.llm.calls[1]`).
- `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
  (línea 401, `len(env.llm.calls) == 0`).

Causa probable: ambos tests sustituyen `env.adapters.llm = ScriptedLLM(...)` pero
luego afirman sobre `env.llm`, que sigue siendo el `FakeLLM` original del fixture
(sin llamadas). Afirmar sobre el `ScriptedLLM` instalado (guardarlo en una variable
o usar `env.adapters.llm`). Verificar además que en el test R44 el router de
verdad se invoca (`HARNESS_ROUTER_ENABLED=true`) y que la segunda llamada es la de RAG.

Nota: el intento 2 de OpenCode quedó colgado ~30 min sin salida ni cambios y se
detuvo; se relanza con el mismo contexto (intento 3, último).

## Corrección 2 (aplicada)

- `tests/test_harness_flow.py::test_r44_r45_rag_uses_original_text_and_validates_citations`
  guarda el `ScriptedLLM` instalado en `env.adapters.llm` en una variable y
  afirma sobre sus `calls` (2 llamadas: router y RAG), no sobre el `FakeLLM`
  original del fixture.
- `tests/test_harness_flow.py::test_r21_r24_r26_r33_r34_client_data_uses_session_id_and_never_returns_rows_to_llm`
  hace lo mismo: afirma sobre el `ScriptedLLM` de SQL instalado (una única
  llamada y sin filas "Ana" en el prompt).
- `tests/test_harness_eval.py` afirma `llm_called` sobre
  `env.adapters.llm.calls`, el adaptador realmente instalado, en lugar del
  `FakeLLM` del fixture (misma intención de R62, sin debilitar ninguna
  aserción).
- `T21` sigue pendiente de que Claude ejecute `./init.sh` y confirme la suite
  completa verde.

## Resultado de `./init.sh` (tras intento de corrección 3)

- `./init.sh` verde: 2573 passed, 1 skipped, 2 warnings; "Entorno listo".
- T0: `referencias/` no existe en el repositorio; no se reutilizó código de terceros.
- Trazabilidad `R1–R63 → test` presente en este informe.
- `feature_list.json`: #39 sigue `in_progress` (no marcada `done`); pendiente reviewer.
