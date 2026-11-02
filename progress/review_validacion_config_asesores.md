# Review — feature #10 validacion_config_asesores

**Veredicto:** APPROVED

Revisado el 2026-10-31 (modo supervisado). Alcance: `services/handover/handover/config.py`,
`services/handover/handover/main.py`, `services/handover/tests/test_config.py`,
`services/handover/tests/test_startup.py` (nuevo) y el comentario de `.env.example`. Los cambios
en `contracts/` (#13) y en el arnés no se juzgan aquí.

## Ejecución

- `.venv/Scripts/python -m pytest services/handover` → `101 passed, 1 warning` (warning
  preexistente `StarletteDeprecationWarning`).
- `test_config.py` + `test_startup.py` → `30 passed`.
- `./init.sh` → `766 passed`, «Entorno listo», exit 0, modo supervisado.

## Trazabilidad requirements ↔ tests

Todos los tests existen, llevan su `R<n>` en el docstring y pasan.

- R1: [x] `test_config.py::test_advisor_ids_strips_surrounding_spaces` (también `test_advisor_ids_discards_blank_entries`)
- R2: [x] `test_config.py::test_advisor_ids_discards_blank_entries`, `::test_advisor_ids_only_commas_is_empty` (`",,,"`, `" , , "`, `""`)
- R3: [x] `test_config.py::test_advisor_ids_rejects_non_numeric_entry` (cadena original, `1.5`, `+5`, `1_000`)
- R4: [x] `test_config.py::test_non_numeric_error_reports_position_and_value` (`la entrada 3 ('abc')`)
- R5: [x] `test_config.py::test_advisor_ids_rejects_duplicate` (`111,222,111`, `7,007`)
- R6: [x] `test_config.py::test_duplicate_error_reports_positions` (`la entrada 4 repite el id de la entrada 1`)
- R7: [x] `test_config.py::test_advisor_ids_accepts_negative_ids` (incluye `-7,7` no duplicado)
- R8: [x] `test_config.py::test_config_error_does_not_echo_valid_ids`, `::test_non_numeric_error_reports_position_and_value`
- R9: [x] `test_startup.py::test_create_app_fails_with_invalid_advisor_ids` (`111,abc`, `111,111`)
- R10: [x] `test_startup.py::test_startup_log_reports_advisor_count`
- R11: [x] `test_startup.py::test_startup_warns_when_no_advisors` (`""`, `" , ,"`)
- R12: [x] `test_startup.py::test_create_app_starts_with_empty_advisor_list`
- R13: [x] `test_startup.py::test_startup_log_does_not_contain_advisor_ids`, `::test_import_main_logs_advisor_count_to_stderr`
- R14: [x] `test_startup.py::test_only_commas_config_still_returns_no_advisors` (`gateway.sent == []`)
- R15: [x] `test_startup.py::test_import_main_logs_advisor_count_to_stderr` (subproceso, sin red)

## Tasks completas

- T1-T22: [x] todas marcadas en `specs/validacion_config_asesores/tasks.md` y verificadas contra el código:
  - T1/T2: `config.py:17-37` (`parse_advisor_chat_ids`, un solo recorrido, `enumerate(start=1)`,
    `fullmatch(r"-?[0-9]+")` equivalente a `^-?[0-9]+$`, mensajes literales del design);
    `config.py:41` `hide_input_in_errors=True`; `config.py:51-55` validador `after`;
    `config.py:57-60` `advisor_ids` con misma firma y docstring actualizado.
  - T12: `main.py:66-69`, justo tras `settings = settings or Settings()` y antes de `FastAPI`.
  - T21: `main.py:35-45` `LOG_FORMAT` y `configure_logging()` idénticos al design; llamada en
    `main.py:133`, antes de `app = create_app()`, no dentro de `create_app`.
  - T19: `.env.example:35`, comentario encima de `ADVISOR_CHAT_IDS=`; valor sigue vacío.
  - T20: informe `progress/impl_validacion_config_asesores.md` con mapa R1-R15, diff y nota de renombrado.

## Tests existentes (no eliminados ni debilitados)

`git diff services/handover/tests/`: solo cambia `test_config.py`. Las únicas líneas eliminadas
son la definición, docstring y entrada de `test_advisor_ids_discards_blank_and_non_numeric`
(cambio autorizado): el nuevo `test_advisor_ids_discards_blank_entries` conserva literalmente
`== [111, 222, -1003]` y la entrada original con `abc`/`4x` pasa a esperar error en
`test_advisor_ids_rejects_non_numeric_entry`. `test_advisor_ids_empty_by_default`,
`test_timeout_defaults_to_300`, `test_settings_read_from_env` y
`test_timeout_below_one_is_rejected` intactos. Ningún otro archivo de tests de handover modificado.

## Seguridad

- [x] Log de arranque sin ids: `main.py:67` solo registra `count=%d`; `main.py:69` sin argumentos.
- [x] Errores sin el valor completo de `ADVISOR_CHAT_IDS` (S5, R8): comprobado a mano,
  `Settings(advisor_chat_ids='987654321,abc')` produce
  `Value error, ADVISOR_CHAT_IDS: la entrada 2 ('abc') no es un entero [type=value_error]`, sin `input_value`.
- [x] Duplicado sin el id (S4): `'5,987654321,5'` produce `la entrada 3 repite el id de la entrada 1`.
- [x] Ningún secreto en el diff (búsqueda de token/secret/key/password: solo el campo existente `service_token: str = ""`).
- [x] `configure_logging()` acotado al logger `handover`: no toca la raíz ni otros loggers, no
  cambia `propagate`, handler solo si ni `handover` ni la raíz tienen handlers.

## Evidencia del writer

- [x] El informe (sección «Modelo usado por OpenCode») cita la salida de
  `scripts/run_opencode_writer.sh` («con deepseek/deepseek-flash», cabecera `implementer · deepseek-flash`)
  y el `opencode export` de la sesión `ses_e6b7803bbffeWCb9hkD5h8DRuQ` con solo
  `"providerID": "deepseek"` y `"modelID": "deepseek-flash"`.

## Checkpoints

- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] una sola feature `in_progress` (#10); features `done` con tests verdes (766 passed).
- C3: [x] solo `services/handover`; sin imports entre servicios; sin dependencias nuevas; sin
  GPL/AGPL; sin secretos; ninguna variable nueva (solo comentario en `.env.example`); sin
  `print()`, `eval`/`exec`, SQL concatenado ni TODOs.
- C4: [x] tests con `FakeCaseRepository`/`FakeGatewayClient`; el subproceso de R15 no abre red
  (`build_default_adapters` no conecta al construir); todos verdes.
- C5: [x] (para el alcance de la feature) sin archivos sospechosos nuevos en `services/handover`;
  el cierre de `progress/history.md` y el estado `done` corresponden al leader/humano.
- C6: [x] `specs/validacion_config_asesores/` con los 3 archivos; EARS; design con «Supuestos a
  confirmar» y sin dependencias nuevas; T1-T22 `[x]`; cada R1-R15 con test.

## Cambios requeridos

Ninguno.

Observaciones no bloqueantes:
1. `services/handover/tests/test_startup.py:42-46` (`test_create_app_fails_with_invalid_advisor_ids`)
   solo fija `ADVISOR_CHAT_IDS`; si el entorno del desarrollador tuviera `HANDOVER_TIMEOUT_SECONDS`
   inválido, también lanzaría `ValidationError` por otra causa. No afecta al resultado actual.
2. Pendiente del leader al cerrar: añadir en `specs/traspaso_asesor/requirements.md` la nota de
   R23 modificado por la #10 (design.md, «Cambio sobre R23 de la #7»).
