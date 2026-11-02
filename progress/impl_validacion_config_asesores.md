# Implementación — validacion_config_asesores (#10)

Estado: código y tests escritos por OpenCode; `./init.sh` verde; T1-T22 marcadas `[x]`
(T20 la marca el implementer Claude tras ejecutar `./init.sh`). Pendiente de reviewer.
No se ha marcado `done`.

## Archivos tocados

- `services/handover/handover/config.py` — `parse_advisor_chat_ids`, validador de
  `advisor_chat_ids`, `hide_input_in_errors=True` y `advisor_ids` reimplementada.
- `services/handover/handover/main.py` — `LOG_FORMAT`, `configure_logging()`, log de
  `advisors_configured` / `no_advisors_configured` en `create_app`.
- `services/handover/tests/test_config.py` — cambio del test de R23 y tests nuevos R1-R8.
- `services/handover/tests/test_startup.py` — nuevo; R9-R15.
- `.env.example` — comentario encima de `ADVISOR_CHAT_IDS=` (valor sigue vacío).
- `specs/validacion_config_asesores/tasks.md` — tasks completadas marcadas `[x]`.

Sin dependencias nuevas, sin cambios en `contracts/`, en otros servicios, en
`docker-compose.yml` ni en `domain.py`.

## Trazabilidad R<n> → test

- R1 → `services/handover/tests/test_config.py::test_advisor_ids_strips_surrounding_spaces`
  (también `::test_advisor_ids_discards_blank_entries`)
- R2 → `services/handover/tests/test_config.py::test_advisor_ids_discards_blank_entries` y
  `::test_advisor_ids_only_commas_is_empty`
- R3 → `services/handover/tests/test_config.py::test_advisor_ids_rejects_non_numeric_entry`
- R4 → `services/handover/tests/test_config.py::test_non_numeric_error_reports_position_and_value`
- R5 → `services/handover/tests/test_config.py::test_advisor_ids_rejects_duplicate`
- R6 → `services/handover/tests/test_config.py::test_duplicate_error_reports_positions`
- R7 → `services/handover/tests/test_config.py::test_advisor_ids_accepts_negative_ids`
- R8 → `services/handover/tests/test_config.py::test_non_numeric_error_reports_position_and_value`
  y `::test_config_error_does_not_echo_valid_ids`
- R9 → `services/handover/tests/test_startup.py::test_create_app_fails_with_invalid_advisor_ids`
- R10 → `services/handover/tests/test_startup.py::test_startup_log_reports_advisor_count`
- R11 → `services/handover/tests/test_startup.py::test_startup_warns_when_no_advisors`
- R12 → `services/handover/tests/test_startup.py::test_create_app_starts_with_empty_advisor_list`
- R13 → `services/handover/tests/test_startup.py::test_startup_log_does_not_contain_advisor_ids`
  y `::test_import_main_logs_advisor_count_to_stderr`
- R14 → `services/handover/tests/test_startup.py::test_only_commas_config_still_returns_no_advisors`
- R15 → `services/handover/tests/test_startup.py::test_import_main_logs_advisor_count_to_stderr`

## Cambio sobre R23 de la #7 (diff de `test_config.py`)

Solo cambia el test citado; el resto de aserciones del archivo queda intacto. El test
`test_advisor_ids_discards_blank_and_non_numeric` (citado para R23 en
`progress/impl_traspaso_asesor.md`) pasa a ser `test_advisor_ids_discards_blank_entries`.

```diff
-def test_advisor_ids_discards_blank_and_non_numeric(clean_env):
-    """R23: ADVISOR_CHAT_IDS se separa por comas; vacíos y no numéricos se descartan."""
-    clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,abc,222,,-1003, 4x ")
-    assert Settings().advisor_ids == [111, 222, -1003]
+def test_advisor_ids_discards_blank_entries(clean_env):
+    """R2 (#10); R23 (#7), modificado por R2 (#10): las entradas vacías se descartan."""
+    clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,222,,-1003, ")
+    assert Settings().advisor_ids == [111, 222, -1003]
+
+
+@pytest.mark.parametrize(
+    "value",
+    [" 111, ,abc,222,,-1003, 4x ", "111,1.5", "111,+5", "111,1_000"],
+)
+def test_advisor_ids_rejects_non_numeric_entry(clean_env, value):
+    """R3: una entrada no vacía que no es un entero (solo `-?[0-9]+`) lanza ValidationError."""
+    clean_env.setenv("ADVISOR_CHAT_IDS", value)
+    with pytest.raises(ValidationError):
+        Settings()
+
+
+# ... tests nuevos de R1, R2, R4-R8 (ver trazabilidad) ...
```

Las aserciones existentes `test_advisor_ids_empty_by_default`,
`test_timeout_defaults_to_300`, `test_settings_read_from_env` y
`test_timeout_below_one_is_rejected` no se tocan. No se ha cambiado ningún otro archivo
de tests de handover.

## Verificación del implementer Claude (2026-10-31)

### Modelo usado por OpenCode (evidencia)

- Comando: `bash scripts/run_opencode_writer.sh validacion_config_asesores`, con
  `OPENCODE_WRITER_MODEL` sin fijar (por defecto `deepseek/deepseek-flash`). OpenCode 1.19.0.
- Salida del comando: `[harness] Delegando escritura de validacion_config_asesores a
  OpenCode con deepseek/deepseek-flash.` y cabecera de sesión `> implementer · deepseek-flash`.
  Terminó con `done -> progress/impl_validacion_config_asesores.md`, exit 0.
- `opencode session list`: sesión `ses_e6b7803bbffeWCb9hkD5h8DRuQ` «Implementar
  validacion_config_asesores».
- `opencode export ses_e6b7803bbffeWCb9hkD5h8DRuQ`: todos los mensajes registran
  `"providerID": "deepseek"` (32) y `"modelID": "deepseek-flash"` (31); ningún otro
  proveedor ni modelo aparece. Resultado: **deepseek/deepseek-flash, verificado**.

### `./init.sh`

- Verde: `766 passed, 1 warning in 7.32s` (antes de la feature: 742 passed; +24 casos
  nuevos, contando parametrizaciones). Aviso único preexistente (`StarletteDeprecationWarning`).
- T22 (subproceso) pasa en Windows: el `env=` se construye desde `os.environ` (quitando
  las variables de `Settings`), como pedía la nota del spec review.

### Tests existentes

- `git status` en `services/handover`: solo cambian `handover/config.py`,
  `handover/main.py`, `tests/test_config.py` y el nuevo `tests/test_startup.py`; ningún
  otro archivo de tests modificado.
- Líneas eliminadas en `tests/test_config.py` (`git diff`): solo la definición, docstring y
  entrada de `test_advisor_ids_discards_blank_and_non_numeric` (cambio autorizado, R23 de
  la #7 → R2 de la #10). La aserción `== [111, 222, -1003]` se conserva; la entrada
  original con `abc` y `4x` se sigue probando en `test_advisor_ids_rejects_non_numeric_entry`.
- Fuera de `services/handover` OpenCode solo tocó `.env.example` (comentario de T19),
  `specs/validacion_config_asesores/tasks.md` y este informe. No tocó `contracts/`,
  `feature_list.json` ni `specs/traspaso_asesor/`.
