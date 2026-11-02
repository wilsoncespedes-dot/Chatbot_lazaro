# Implementación — #25 clasificador_consultas

Implementado el spec aprobado (`specs/clasificador_consultas/`). Alcance:
orchestrator únicamente (clasificador puro, panel `/admin/categories`,
persistencia y evento `query_classified`). Sin rutas de contrato nuevas, sin
cambios en RAG, handover ni gateway, sin dependencias nuevas y sin código
externo copiado.

## Resumen

- `orchestrator/classifier.py`: `Category`, `Classification`, `UNCLASSIFIED`,
  `normalize_text`, `parse_keywords`, `validate_category_fields`,
  `parse_threshold` y `classify` (determinista, sin LLM ni embeddings).
- `orchestrator/domain.py`: `CategoryCodeTaken`, `CategoryNotFound`,
  `classifier_threshold`, `_classify_query` (evento `query_classified` antes
  de `rag.search`), CRUD de categorías y umbral.
- `orchestrator/adapters/repository.py`: tablas `query_categories` y
  `app_settings`; métodos en Protocol, `FakeRepository` y
  `PostgresRepository` con SQL parametrizado.
- `orchestrator/admin.py` + `admin_routes.py`: vista y 4 rutas de
  `/admin/categories` (sesión → CSRF → validación → dominio; `threshold`
  registrada antes de `{id}`), escapado con `html.escape` y cabeceras de #21.
- `orchestrator/config.py` + `.env.example`: `CLASSIFIER_DEFAULT_THRESHOLD`
  (0.6, rango 0–1).
- Se ajustaron dos aserciones de tests previos afectadas por el nuevo evento
  (`test_messages.py`) y el conjunto de rutas de `test_config.py`; ninguna
  aserción se eliminó ni se debilitó.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_admin_categorias.py::test_categories_page_lists_active_and_inactive_with_threshold`, `::test_categories_page_uses_default_threshold_without_stored_value`
- R2 → `services/orchestrator/tests/test_admin_categorias.py::test_create_category_redirects_and_stores_active`
- R3 → `services/orchestrator/tests/test_admin_categorias.py::test_update_category_keeps_code_and_active`
- R4 → `services/orchestrator/tests/test_admin_categorias.py::test_toggle_category_active`
- R5 → `services/orchestrator/tests/test_admin_categorias.py::test_create_with_invalid_fields_returns_422_without_changes`, `::test_update_with_invalid_fields_returns_422_without_changes`, `::test_toggle_with_invalid_active_returns_422_without_changes`; `services/orchestrator/tests/test_classifier.py::test_parse_keywords_rejects_invalid_values`, `::test_validate_category_fields_rejects_invalid_codes`, `::test_validate_category_fields_rejects_invalid_names`
- R6 → `services/orchestrator/tests/test_admin_categorias.py::test_duplicate_code_returns_409`
- R7 → `services/orchestrator/tests/test_admin_categorias.py::test_update_unknown_category_returns_404`, `::test_toggle_unknown_category_returns_404`
- R8 → `services/orchestrator/tests/test_admin_categorias.py::test_threshold_is_saved_and_shown`
- R9 → `services/orchestrator/tests/test_admin_categorias.py::test_invalid_threshold_returns_422_without_changes`; `services/orchestrator/tests/test_classifier.py::test_parse_threshold_rejects_invalid_values`, `::test_parse_threshold_accepts_finite_decimals_in_range`
- R10 → `services/orchestrator/tests/test_admin_categorias.py::test_categories_without_session_redirect_before_changes`
- R11 → `services/orchestrator/tests/test_admin_categorias.py::test_categories_posts_require_csrf`
- R12 → `services/orchestrator/tests/test_admin_categorias.py::test_category_values_are_escaped_and_headers_are_secure`, `::test_error_pages_keep_security_headers`
- R13 → `services/orchestrator/tests/test_classifier.py::test_scores_are_hits_over_total_and_sum_to_one`
- R14 → `services/orchestrator/tests/test_classifier.py::test_inactive_categories_are_not_counted_or_scored`
- R15 → `services/orchestrator/tests/test_classifier.py::test_best_score_at_or_above_threshold_is_classified`, `::test_best_score_above_threshold_is_classified`
- R16 → `services/orchestrator/tests/test_classifier.py::test_best_score_below_threshold_is_unclassified`
- R17 → `services/orchestrator/tests/test_classifier.py::test_no_active_categories_returns_unclassified_zero`, `::test_no_keyword_hit_returns_unclassified_zero`
- R18 → `services/orchestrator/tests/test_classifier.py::test_tie_is_unclassified_with_tied_score`
- R19 → `services/orchestrator/tests/test_classifier.py::test_keyword_matches_only_a_full_phrase`, `::test_keyword_matches_ignoring_accents_and_case`, `::test_instruction_in_text_does_not_choose_a_category`
- R20 → `services/orchestrator/tests/test_classifier.py::test_regex_metacharacters_are_literal_and_never_raise`
- R21 → `services/orchestrator/tests/test_classifier.py::test_repeated_keyword_counts_once_per_message`
- R22 → `services/orchestrator/tests/test_messages_classification.py::test_query_classified_is_saved_before_rag_search`
- R23 → `services/orchestrator/tests/test_messages_classification.py::test_classification_does_not_change_rag_arguments_or_client_reply`
- R24 → `services/orchestrator/tests/test_messages_classification.py::test_start_token_is_not_classified`, `::test_advisor_command_is_not_classified`, `::test_message_forwarded_to_case_is_not_classified`, `::test_handover_keyword_is_not_classified`
- R25 → `services/orchestrator/tests/test_messages_classification.py::test_repository_failure_logs_and_continues_to_rag`
- R26 → `services/orchestrator/tests/test_messages_classification.py::test_default_threshold_classifies`, `::test_configured_default_threshold_is_used`, `::test_stored_threshold_overrides_the_default`; `services/orchestrator/tests/test_classifier.py::test_default_classifier_threshold_is_configurable_and_validated`
- R27 → `services/orchestrator/tests/test_admin_categorias.py::test_schema_creates_category_and_settings_tables`, `::test_postgres_category_queries_use_parameters_only`

## Verificación

Pendiente de que Claude ejecute `./init.sh` al cerrar la sesión e incorpore el
resultado aquí.
## Verificación

`./init.sh` completó con exit 0: 1658 tests pasan (incluye las pruebas de R1–R27).
