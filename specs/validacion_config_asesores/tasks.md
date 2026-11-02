# Tasks — validacion_config_asesores

Solo `services/handover/` y un comentario en `.env.example`. Sin dependencias nuevas. Cada test
lleva en su docstring el `R<n>` de este spec que cubre (`"""R3: ..."""`).

Se ejecutan en el orden en que aparecen. T21-T22 (añadidas tras el spec review) van después de
T18 y antes de T19; se numeran al final para no cambiar los números ya citados.

## Configuración (`handover/config.py`)

- [x] T1 — Añadir `parse_advisor_chat_ids(raw: str) -> list[int]` en `services/handover/handover/config.py`: recorrido único con posición desde 1, `strip()`, vacías ignoradas, `^-?[0-9]+$`, duplicados por valor, mensajes exactos del design. Cubre: R1, R2, R3, R4, R5, R6, R7.
- [x] T2 — En `Settings`: `hide_input_in_errors=True` en `model_config`, `@field_validator("advisor_chat_ids")` que llama a `parse_advisor_chat_ids`, y `advisor_ids` reimplementada sobre esa función (misma firma; docstring actualizado). Cubre: R3, R5, R8.

## Cambio del test de R23 de la #7 (`tests/test_config.py`)

- [x] T3 — Sustituir `test_advisor_ids_discards_blank_and_non_numeric` por `test_advisor_ids_discards_blank_entries`: entrada `" 111, ,222,,-1003, "` y la misma aserción `== [111, 222, -1003]` (solo se quitan `abc` y `4x` de la entrada); docstring «R2 (#10); R23 (#7), modificado por R2 (#10)». No tocar ninguna otra aserción del archivo. Cubre: R2.
- [x] T4 — Añadir `test_advisor_ids_rejects_non_numeric_entry`, parametrizado con la cadena original `" 111, ,abc,222,,-1003, 4x "` y con `"111,1.5"`, `"111,+5"`, `"111,1_000"`: `pytest.raises(ValidationError)`. Cubre: R3.
- [x] T5 — Añadir `test_non_numeric_error_reports_position_and_value`: con `" 111, ,abc,222,,-1003, 4x "` el mensaje (`str(excinfo.value)`) contiene `la entrada 3 ('abc')` y no contiene `111` ni `-1003` (ni `222`). Cubre: R4, R8.

## Tests nuevos de configuración (`tests/test_config.py`)

- [x] T6 — `test_advisor_ids_strips_surrounding_spaces`: `"  111 ,\t222  "` → `[111, 222]`. Cubre: R1.
- [x] T7 — `test_advisor_ids_only_commas_is_empty`, parametrizado con `",,,"`, `" , , "` y `""`: `advisor_ids == []` sin error. Cubre: R2.
- [x] T8 — `test_advisor_ids_rejects_duplicate`, parametrizado con `"111,222,111"` y `"7,007"`: `pytest.raises(ValidationError)`. Cubre: R5.
- [x] T9 — `test_duplicate_error_reports_positions`: con `"111,222,,111"` el mensaje contiene `la entrada 4 repite el id de la entrada 1`. Cubre: R6.
- [x] T10 — `test_advisor_ids_accepts_negative_ids`: `"-1001234567890,-5,42"` → `[-1001234567890, -5, 42]` (y `"-7,7"` no es duplicado). Cubre: R7.
- [x] T11 — `test_config_error_does_not_echo_valid_ids`: con `"987654321,abc"` y con `"987654321,123123,987654321"` (entradas válidas que no se solapan con la inválida), `"987654321"` y `"123123"` no aparecen en `str(excinfo.value)`. Cubre: R8.

## Arranque (`handover/main.py` y `tests/test_startup.py`)

- [x] T12 — En `create_app` de `services/handover/handover/main.py`, tras resolver `settings`, registrar `advisors_configured count=%d` (INFO) y, si la cuenta es 0, `no_advisors_configured` (WARNING). Sin ids en el log. Cubre: R10, R11, R12, R13.
- [x] T13 — Crear `services/handover/tests/test_startup.py` con `test_create_app_fails_with_invalid_advisor_ids`, parametrizado (`"111,abc"`, `"111,111"`): con `monkeypatch.setenv("ADVISOR_CHAT_IDS", ...)`, `create_app()` lanza `ValidationError`. Cubre: R9.
- [x] T14 — `test_startup_log_reports_advisor_count`: `create_app(Settings(advisor_chat_ids="111,222,333"), fakes)` con `caplog` a INFO deja un registro INFO con `advisors_configured` y `count=3`, y ninguno `no_advisors_configured`. Cubre: R10.
- [x] T15 — `test_startup_warns_when_no_advisors`, parametrizado con `""` y `" , ,"`: hay un registro WARNING `no_advisors_configured` y `advisors_configured count=0`. Cubre: R11.
- [x] T16 — `test_create_app_starts_with_empty_advisor_list`: con `advisor_chat_ids=""` `create_app` devuelve una `FastAPI` y `GET /health` responde `200`. Cubre: R12.
- [x] T17 — `test_startup_log_does_not_contain_advisor_ids`: con `advisor_chat_ids="987654321,-1001234567890"` y `caplog` a DEBUG, hay registros y ninguno contiene `987654321` ni `1001234567890`. Cubre: R13.
- [x] T18 — `test_only_commas_config_still_returns_no_advisors`: `make_env`-equivalente con `Settings(advisor_chat_ids=", ,")`, `POST /handover` responde `200` `{"status": "no_advisors", ...}` y `FakeGatewayClient` no registra envíos. Cubre: R14.
- [x] T21 — En `services/handover/handover/main.py`: añadir `LOG_FORMAT` y `configure_logging()` tal como en design.md «Logging del servicio» (logger `handover` a `INFO`; `StreamHandler` a stderr solo si ni `handover` ni la raíz tienen handlers; `propagate` sin tocar) y llamarla a nivel de módulo justo antes de `app = create_app()`. No llamarla dentro de `create_app`. Cubre: R15.
- [x] T22 — En `tests/test_startup.py`, `test_import_main_logs_advisor_count_to_stderr`: `subprocess.run([sys.executable, "-c", "import handover.main"], env=..., capture_output=True, text=True, timeout=...)` con `ADVISOR_CHAT_IDS="987654321,-1001234567890"` y `PYTHONPATH=os.pathsep.join(sys.path)`; afirma `returncode == 0`, `advisors_configured count=2` en `stderr` y que `987654321` y `1001234567890` no aparecen en `stderr`. Sin red. Cubre: R15, R13.

## Documentación y cierre

- [x] T19 — Añadir en `.env.example`, encima de `ADVISOR_CHAT_IDS=`, el comentario del design (formato, sin repetir, negativos válidos, no arranca si hay error). El valor sigue vacío. Cubre: R3, R5, R7.
- [x] T20 — Ejecutar `./init.sh` (todo verde: los tests existentes de handover pasan sin cambios salvo T3) y escribir `progress/impl_validacion_config_asesores.md` con el mapa R1-R15 → test, el diff de `test_config.py` que muestre que solo cambia lo descrito en design.md «Cambio sobre R23 de la #7», y la nota de que `test_advisor_ids_discards_blank_and_non_numeric` (citado para R23 en `progress/impl_traspaso_asesor.md`) pasa a ser `test_advisor_ids_discards_blank_entries`. Cubre: R1-R15.
