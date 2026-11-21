# Review (código) — feature #60 `contrato_canal_abierto`

**Veredicto:** APPROVED

Ciclo de corrección 1: es una revisión dirigida a los dos hallazgos del ciclo anterior y a
comprobar que no se rompió nada alrededor.

Base `02427e8`; el trabajo sigue sin commitear en el árbol. Ejecutado con `.venv` (Python 3.14.7,
pydantic 2.14.2):
`python -m pytest contracts services/telegram_gateway services/orchestrator` → **3000 passed,
1 skipped**, exit 0. El `./init.sh` del implementer da 3729 passed, 1 skipped.

## Hallazgos del ciclo anterior

1. **R17: `contracts/lazaro_contracts/channels.py`. Resuelto.**
   - `JsonValue` se importa de `pydantic` (l.12); `JsonValue = Any` ya no existe.
   - `_check_metadata` usa `json.dumps(..., allow_nan=False)` (l.124-126).
   - Repetí la sonda del ciclo anterior. Todos estos casos dan `ValidationError`: tuplas
     anidadas de profundidad 9, clave int anidada, `set`/`bytes`/objeto, `NaN`/`±Infinity` (en
     Python y como literal JSON), profundidad 6, y 5 000 y 200 000 niveles en Python. Este último
     da `recursion_loop`, ya no `RecursionError`.
   - Profundidad 5 y 4096 bytes siguen aceptándose.
   - Tests nuevos en `contracts/tests/test_canal_abierto.py`:
     - `test_metadata_rejects_non_json_python_values` (l.352-362)
     - `test_metadata_rejects_deeply_nested_python_dict` (l.365-371, 100 000 niveles)
     - `test_metadata_rejects_non_json_numbers` (l.374-378)
2. **R43/R44: `services/orchestrator/tests/test_canal_abierto.py`. Resuelto.**
   - `_consent` (l.55-62) registra el consentimiento de la identidad antes del POST en los dos
     tests (l.71 y l.80).
   - Prueba de mutación en una copia en scratch: con la guarda movida detrás de `mark_new()`,
     los 3 casos fallan en `processed_messages == set()`:
     - `{('canal-externo','m-1')}`
     - `{('instagram','m-1')}`
     - `{('whatsapp','out-1')}`

     Con el código real pasan, así que el test ya comprueba «sin registrar la clave del
     mensaje».

## Sin regresiones

- El código fuera de `channels.py` no cambió respecto al ciclo anterior: gateway, orquestador,
  `__init__.py`, `common.py` y `CONTRATOS.md`.
- R25/R26 siguen en verde: serialización con las claves históricas y round trip.
- R47: `git diff --name-status 02427e8 -- services/*/tests contracts/tests contracts/examples`
  está vacío. Solo aparecen los 4 archivos de test nuevos (`??`).
- `progress/impl_contrato_canal_abierto.md` tiene la trazabilidad de R17 y R18 actualizada y la
  desviación retirada.

## Trazabilidad requirements ↔ tests

- R1–R16, R18–R42, R45–R48: [x] sin cambios respecto al ciclo anterior (ver
  `progress/impl_contrato_canal_abierto.md`).
- R17: [x] cubierto por:
  - `test_metadata_depth_limit`
  - `test_metadata_rejects_non_json_python_values`
  - `test_metadata_rejects_deeply_nested_python_dict`
  - `test_metadata_rejects_non_json_numbers`
- R43: [x] `test_post_messages_rejects_unattended_channel` (con consentimiento; mutación eliminada)
- R44: [x] `test_post_messages_rejects_outbound_direction` (con consentimiento; mutación eliminada)

## Tasks completas

- T1–T17: [x]

## Checkpoints

- C1: [x] (suites afectadas en verde verificadas por el reviewer; `./init.sh` verde según el implementer)
- C2: [x]
- C3: [x]
- C4: [x]
- C5: n/a hasta el cierre (`progress/history.md` lo actualiza el leader)
- C6: [x]

## Observaciones no bloqueantes

- `services/orchestrator/tests/test_canal_abierto.py`: las líneas 51-52 de
  `_assert_nothing_happened` repiten la comprobación de la línea 45.
- `contracts/tests/test_canal_abierto.py:376`: el docstring dice R17, pero NaN/Infinity
  encajan mejor en R15/R18.
