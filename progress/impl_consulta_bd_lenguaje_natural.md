# Implementación — consulta_bd_lenguaje_natural (#26)

Servicio: orchestrator. `DB_QUERY_ENABLED=false` por defecto: sin LLM ni
conexión de lectura hasta activarlo. No se tocó `contracts/`, otros servicios
ni `docker-compose.yml`.

## Archivos

- `services/orchestrator/orchestrator/config.py`: campos `db_query_*`,
  `db_query_allowlist_map` y validación R8/R9 en `model_validator`.
- `services/orchestrator/orchestrator/db_query.py` (nuevo): parser del comando,
  prompt, `parse_sql_answer`, `validate_sql` por allowlist de tokens,
  `format_rows`, excepciones y dataclasses.
- `services/orchestrator/orchestrator/adapters/db_query.py` (nuevo):
  `DbQueryClient`, `PostgresReadOnlyQuery`, `UnavailableDbQuery`, `FakeDbQuery`.
- `services/orchestrator/orchestrator/domain.py`: `Adapters.db_query`,
  `handle_db_query` y enganche antes de `parse_advisor_command`.
- `services/orchestrator/orchestrator/adapters/repository.py`:
  `get_profile_by_telegram_user_id`, `add_db_query_audit`, tabla
  `db_query_audit` (Fake y Postgres).
- `services/orchestrator/orchestrator/main.py`: `PostgresReadOnlyQuery` solo con
  el flag encendido; `UnavailableDbQuery` en caso contrario.
- `services/orchestrator/tests/{conftest,fakes}.py` y fixtures de panel: nuevo
  `FakeDbQuery` inyectado en `Adapters`.
- `services/orchestrator/tests/test_db_query.py` (nuevo): R1-R36.
- `.env.example`: variables nuevas con comentario del supuesto S1.
- `docs/consulta_bd.md` (nuevo): rol de lectura, esquema/vistas, regla de
  columnas exactas, habilitación y reinicio tras cambiar vistas.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_db_query.py::test_consultar_runs_query_without_storing_message_rag_or_handover` y `::test_parse_db_query_command_only_accepts_exact_first_token`
- R2 → `::test_consultar_without_question_returns_help` y `::test_consultar_too_long_returns_help`
- R3 → `::test_disabled_flag_returns_fixed_text_without_llm_or_database`
- R4 → `::test_linked_advisor_is_authorized` y `::test_non_positive_sender_is_forbidden`
- R5 → `::test_non_advisor_profile_is_forbidden` y `::test_sender_without_profile_is_forbidden`
- R6 → `::test_group_chat_is_forbidden`
- R7 → `::test_authorization_precedes_question_validation`
- R8 → `::test_enabled_without_read_only_dsn_is_rejected` y `::test_read_only_dsn_must_differ_from_application_dsn`
- R9 → `::test_invalid_allowlist_is_rejected`
- R10 → `::test_prompt_contains_only_allowlisted_schema_and_neutralized_question`
- R11 → `::test_prompt_contains_only_allowlisted_schema_and_neutralized_question`
- R12 → `::test_invalid_llm_answer_is_rejected_without_database` y `::test_parse_sql_answer_accepts_valid_json`
- R13 → `::test_unsafe_sql_is_rejected_without_database` y `::test_safe_sql_is_accepted`
- R14 → `::test_unsafe_sql_is_rejected_without_database`
- R15 → `::test_unsafe_sql_is_rejected_without_database`
- R16 → `::test_unsafe_sql_is_rejected_without_database` y `::test_safe_sql_is_accepted`
- R17 → `::test_unsafe_sql_is_rejected_without_database`
- R18 → `::test_adapter_uses_read_only_transaction_timeout_limit_and_rollback` y `::test_adapter_rolls_back_after_execution_error`
- R19 → `::test_adapter_truncates_to_max_rows_and_requests_one_more` y `::test_format_rows_caps_length_and_keeps_truncated_note` y `::test_truncated_query_reply_is_capped`
- R20 → `::test_adapter_requires_exact_columns_without_leaking_names` y `::test_adapter_rejects_non_view_object_without_running_sql` y `::test_adapter_memoizes_successful_catalog_check` y `::test_adapter_rechecks_catalog_after_a_failure`
- R21 → `::test_ok_query_writes_audit_with_expected_fields` y `::test_audit_is_written_for_every_outcome`
- R22 → `::test_audit_and_logs_never_store_question_sql_rows_or_dsn`
- R23 → `::test_audit_failure_returns_unavailable_without_sending_rows`
- R24 → `::test_database_error_returns_fixed_text_without_internal_details`
- R25 → `::test_unsafe_sql_is_rejected_without_database`
- R26 → `::test_format_rows_caps_length_and_keeps_truncated_note` y `::test_truncated_query_reply_is_capped`
- R27 → `::test_unsafe_sql_is_rejected_without_database`
- R28 → `::test_unsafe_sql_is_rejected_without_database`
- R29 → `::test_unsafe_sql_is_rejected_without_database`
- R30 → `::test_non_advisor_profile_is_forbidden` y `::test_sender_without_profile_is_forbidden` y `::test_group_chat_is_forbidden`
- R31 → `::test_consultar_runs_query_without_storing_message_rag_or_handover`
- R32 → `::test_audit_failure_returns_unavailable_without_sending_rows`
- R33 → `::test_duplicate_update_runs_query_only_once`
- R34 → `::test_unsafe_sql_is_rejected_without_database`
- R35 → `::test_unsafe_sql_is_rejected_without_database`
- R36 → `::test_unsafe_sql_is_rejected_without_database`

## Notas

- T19 no requirió cambios: `test_repository_lock.py` cuenta con `len(_SCHEMA)`,
  así que la tabla nueva se contempla sin debilitar ninguna aserción.
- El validador es conservador (allowlist estricta); rechaza construcciones
  seguras que el spec no enumera, como `IN (...)` o paréntesis tras `WHERE`,
  porque R14 exige que toda palabra seguida de `(` sea una función permitida.
- La comprobación de catálogo se memoriza tras el primer éxito; reiniciar tras
  cambiar una vista (documentado en `docs/consulta_bd.md`).

### Correcciones de `./init.sh` — primer intento

`./init.sh` falló: 5 failed, 1753 passed.
1. `services/orchestrator/tests/test_db_query.py::test_safe_sql_is_accepted[SELECT col * 2 FROM consultas.v_x]`: `validate_sql` rechaza la multiplicación que T15 declara segura.
2. `test_adapter_uses_read_only_transaction_timeout_limit_and_rollback`, `test_adapter_memoizes_successful_catalog_check`, `test_adapter_rechecks_catalog_after_a_failure` y `test_adapter_truncates_to_max_rows_and_requests_one_more`: `_verify_catalog` espera el resultado nuevo de `pg_attribute`/metadatos exactos, pero `_FakeCursor` solo entrega la forma anterior/orden incorrecto; 4 fallos.
Corregir implementación y fake/tests para alinearlos con la spec final; no debilitar las comprobaciones de columnas ni los tests de seguridad. Después volveré a ejecutar `./init.sh`.

### Correcciones aplicadas

1. `db_query.py::_is_star_allowed`: un operando sin calificar solo contaba si su
   nombre coincidía con una clave del mapa de vistas (`token.value in columns`
   era siempre falso para columnas), así que `col * 2` se rechazaba. Ahora un
   token palabra es operando si es una columna allowlisted de alguna vista
   referenciada; las columnas calificadas siguen validándose contra su
   cualificador. `SELECT *`, `vista.*` y `alias.*` siguen rechazados.
2. `tests/test_db_query.py::_FakeConn`: el catálogo falso solo devolvía datos de
   `consultas.v_x` aunque `ALLOWLIST` declara `v_x` y `v_y`; R20 exige verificar
   **todos** los objetos de la allowlist, por lo que `_verify_catalog` fallaba
   siempre con `v_y` ausente (4 tests del adaptador). El fake devuelve ahora las
   dos vistas y los dos pares de columnas.
3. Tests del adaptador reforzados, sin debilitar aserciones:
   `test_adapter_rejects_non_view_object_without_running_sql` fija `v_y` como
   vista válida para aislar el `relkind='r'` de `v_x`; los parámetros de
   `test_adapter_requires_exact_columns_without_leaking_names` y la segunda
   llamada de `test_adapter_rechecks_catalog_after_a_failure` incluyen las
   columnas correctas de `v_y`, de modo que el fallo comprobado es la columna de
   más/menos de `v_x` y el éxito posterior es real.

Pendiente: Claude ejecutará `./init.sh` para confirmar todo en verde.

## Verificación final del implementador

`./init.sh` pasó con exit 0: 1758 tests (2026-11-01).

### Hardening solicitado por Claude reviewer (no bloqueante)

Claude APPROVED #26, pero señaló que `PostgresReadOnlyQuery.run()` no cierra su conexión tras `ROLLBACK`, lo que puede dejar conexiones abiertas bajo carga. También recomendó que el tokenizador acepte solo whitespace ASCII para evitar discrepancias con PostgreSQL. Corregir ambos con pruebas, preservando todos los rechazos del parser y cleanup de rollback. Luego `./init.sh` y revisión dirigida de Claude.

### Hardening aplicado

1. **Cierre de conexión (`adapters/db_query.py`).** El `finally` ejecuta
   `ROLLBACK` y después `connection.close()`; si el cierre falla se registra
   `db_query_close_failed` y no se oculta el resultado ni la excepción original
   (igual que `db_query_rollback_failed`). La conexión se cierra también en los
   caminos de error de ejecución y de catálogo. El log es una etiqueta fija, sin
   mensaje de la excepción.
2. **Separadores ASCII (`db_query.py`).** `_tokenize` solo omite
   `_ASCII_WHITESPACE` (`" \t\r\n\f\v"`). Cualquier otro espacio Unicode
   (U+00A0, U+202F, U+3000, U+2028…) cae en `invalid_token`, de modo que el
   tokenizador y PostgreSQL no discrepan sobre qué separa tokens. Los
   separadores ASCII (tabulador, salto de línea, CRLF) siguen funcionando y el
   comportamiento del resto del parser no cambia.

Tests nuevos/actualizados (todos en `services/orchestrator/tests/test_db_query.py`):

- R13 → `::test_validate_sql_rejects_non_ascii_whitespace` (4 separadores × 4
  posiciones), `::test_validate_sql_accepts_ascii_whitespace` y
  `::test_unicode_whitespace_sql_is_rejected_without_database` (respuesta
  `DB_QUERY_REJECTED_REPLY` sin llamar a `FakeDbQuery`).
- R18 → `::test_adapter_uses_read_only_transaction_timeout_limit_and_rollback`
  (ahora comprueba `close()` después del `ROLLBACK`),
  `::test_adapter_rolls_back_and_closes_after_execution_error`,
  `::test_adapter_rejects_non_view_object_without_running_sql` (cierre también
  tras fallo de catálogo) y
  `::test_adapter_close_failure_does_not_replace_query_result` (fallo de cierre
  registrado sin texto de la excepción y sin perder las filas).

Ningún rechazo del parser, aserción de seguridad ni cleanup de rollback se
eliminó o debilitó. La observación 3 del review (falsos negativos conservadores
como `IN (...)`) se mantiene sin cambios: ya está documentada abajo.


### Hardening posterior al veredicto

`./init.sh` volvió a pasar con 1777 tests. Se cerró la conexión de lectura después del ROLLBACK (éxito/error) y el parser ahora admite solo separadores ASCII; hay regresiones para ambos casos.
