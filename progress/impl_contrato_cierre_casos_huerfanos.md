# Implementación — contrato_cierre_casos_huerfanos (feature #17)

## Resumen

Implementada la feature de contrato dentro del alcance de `design.md` §1 y §2:

- `contracts/CONTRATOS.md`: sustituida la fila `S12` por la línea «después» de
  H1 (`design.md` §1.1). Las tres inserciones (caso huérfano y cierre,
  prohibición de responder/asignar, salvedad en la precedencia y procedimiento
  de retirada) se aplicaron sobre la línea existente. No se editó, añadió ni
  eliminó ninguna otra línea del documento.
- `contracts/tests/test_contratos_doc.py`: añadido al final el bloque
  `# ── contrato_cierre_casos_huerfanos (feature #17) ──…` con los 11 tests
  T3-T13. Ninguna línea existente se tocó, eliminó ni debilitó; los tests
  reutilizan el helper existente `_assumption_row("S12")`.

No se ha tocado `feature_list.json`, `progress/current.md`, `progress/history.md`,
`services/`, `eval/`, `scripts/`, `docker-compose.yml` ni el harness. La feature
no se marca `done`.

## Trazabilidad

- R1 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_defines_orphan_case`
- R2 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_close_by_any_registered_advisor`
- R3 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_authorize_close_allowed`
- R4 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_close_is_not_reassignment`
- R5 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_assigned_close_rule_has_orphan_exception`
- R6 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_reply_forbidden`
- R7 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_assign_forbidden`
- R8 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_precedence_other_advisor_step_skips_orphan_close`
- R9 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_precedence_orphan_close_allowed_after_first_steps`
- R10 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_documents_advisor_retirement_procedure`
- R11 → `contracts/tests/test_contratos_doc.py::test_assumptions_s12_documents_orphan_count_at_startup`
- R12 → comprobación de diff de `CONTRATOS.md` (T14, puente Claude)
- R13 → comprobación de archivos de `contracts/` (T15, puente Claude)
- R14 → comprobación de diff de `test_contratos_doc.py`, solo líneas añadidas (T15, puente Claude)
- R15 → batería completa en verde (T16, puente Claude)

## Tasks

- Completadas por el escritor: T2-T13 (marcadas `[x]`).
- Pendientes del puente Claude: T1 (snapshot), T14-T16 (verificación) y T17
  (añadir a este informe el diff y el recuento de la batería).

## Verificación (puente Claude, 2026-10-31, modo nocturno)

- T1: snapshot de `contracts/` copiado al scratchpad de la sesión Claude
  (`.../scratchpad/contracts_before`) antes de invocar a OpenCode.
- T14: `git diff --no-index -U0 contracts_before/CONTRATOS.md contracts/CONTRATOS.md`
  → 1 línea eliminada y 1 añadida, ambas `| S12 | …`. Comparación byte a byte
  (`cmp`): la eliminada es idéntica a la línea 35 de `design.md` (H1 «antes») y la
  añadida idéntica a la línea 41 (H1 «después»). Sin CR en el archivo (LF).
- T15: `diff -rq --exclude=__pycache__ --exclude=.pytest_cache` solo lista
  `CONTRATOS.md` y `tests/test_contratos_doc.py`. Diff del test: 0 líneas
  eliminadas, 81 añadidas.
- T16: `bash ./init.sh` → `777 passed, 1 warning` (antes 766; +11 tests nuevos),
  "Entorno listo". Ningún test existente eliminado ni editado.
- Modelo verificado: `opencode export ses_e6b2ee440ffeC1wVLCfiAo9qVC` (sesión
  "Implementar feature SDD contrato_cierre_casos_huerfanos") → únicamente
  `"providerID": "deepseek"` (17 apariciones) y `"modelID": "deepseek-flash"`
  (16 apariciones); ningún otro proveedor ni modelo. `OPENCODE_WRITER_MODEL` no
  fijado (lanzado con `env -u OPENCODE_WRITER_MODEL`).
- `feature_list.json` no se ha tocado; la feature sigue `in_progress` (no `done`).

Estado de las tasks: T1-T17 completadas.
