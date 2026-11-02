# Review — feature 17 (`contrato_cierre_casos_huerfanos`)

**Veredicto:** APPROVED

Revisado en modo nocturno el 2026-10-31. Para aislar la #17 de los cambios sin commit de la
#13 y la #10 se ha comparado contra la copia previa de T1
(`.../scratchpad/contracts_before/`, sesión `ef6e2694-…`), que ya contiene la #13: su fila S12
es byte a byte la línea «antes» de H1 (`design.md:35`) y su `test_contratos_doc.py` tiene los
tests de la #13 (619 líneas).

## Trazabilidad requirements ↔ tests
- R1: [x] `contracts/tests/test_contratos_doc.py:625` `test_assumptions_s12_defines_orphan_case` (fragmento con «es nulo o ya no está»)
- R2: [x] `:635` `test_assumptions_s12_orphan_close_by_any_registered_advisor`
- R3: [x] `:645` `test_assumptions_s12_orphan_authorize_close_allowed`
- R4: [x] `:652` `test_assumptions_s12_orphan_close_is_not_reassignment`
- R5: [x] `:659` `test_assumptions_s12_assigned_close_rule_has_orphan_exception`
- R6: [x] `:666` `test_assumptions_s12_orphan_reply_forbidden`
- R7: [x] `:679` `test_assumptions_s12_orphan_assign_forbidden`
- R8: [x] `:689` `test_assumptions_s12_precedence_other_advisor_step_skips_orphan_close` (fragmento contiguo)
- R9: [x] `:700` `test_assumptions_s12_precedence_orphan_close_allowed_after_first_steps`
- R10: [x] `:713` `test_assumptions_s12_documents_advisor_retirement_procedure`
- R11: [x] `:720` `test_assumptions_s12_documents_orphan_count_at_startup`
- R12: [x] comprobado por el revisor (T14): `git diff --no-index -U0 contracts_before/CONTRATOS.md contracts/CONTRATOS.md` → exactamente 1 línea `-` y 1 línea `+`, ambas `| S12 |`. `cmp`: la eliminada = `design.md:35` (H1 antes), la nueva (`contracts/CONTRATOS.md:436`) = `design.md:41` (H1 después). 0 CR en el archivo (LF). Una sola fila `| S12 |`.
- R13: [x] comprobado por el revisor (T15): `diff -rq --exclude=__pycache__ --exclude=.pytest_cache contracts_before contracts` solo lista `CONTRATOS.md` y `tests/test_contratos_doc.py`.
- R14: [x] comprobado por el revisor: diff de `test_contratos_doc.py` con un único hunk `@@ -619,0 +620,105 @@` y 0 líneas eliminadas (`^-[^-]`). Solo se añade el bloque `# ── contrato_cierre_casos_huerfanos (feature #17) ──` al final.
- R15: [x] `.venv/Scripts/python -m pytest contracts` → 385 passed; `python -m pytest` (repo) → 777 passed, 1 warning; `./init.sh` → exit 0, «Entorno listo».

## Tasks completas
- T1-T17: [x] (todas marcadas en `specs/contrato_cierre_casos_huerfanos/tasks.md`; T1/T14-T17 hechas por el puente Claude, documentadas en `progress/impl_contrato_cierre_casos_huerfanos.md`).

## Contenido de la #13 intacto
- Los 14 tests de S12 de la #13 (`design.md` §5) siguen en el archivo sin cambios (diff sin borrados) y pasan: `-k "s12 or orphan"` → 25 passed (14 existentes + 11 nuevos).
- Los demás archivos de `contracts/` modificados por la #13 (`lazaro_contracts/*.py`, `tests/test_examples.py`, `test_models.py`, `test_packaging.py`, `examples/case_authorize_*.json`) son idénticos a la copia previa (no salen en `diff -rq`).
- Ninguna aserción eliminada ni debilitada.

## Otras comprobaciones
- Sin dependencias nuevas: ningún `requirements*.txt` cambiado por la #17 (`contracts/requirements.txt` igual a la copia previa).
- Sin código externo copiado: solo una línea de Markdown y tests con el helper existente `_assumption_row`.
- Sin secretos en los archivos tocados.
- Writer: `opencode export ses_e6b2ee440ffeC1wVLCfiAo9qVC` (título «Implementar feature SDD contrato_cierre_casos_huerfanos») → solo `"providerID": "deepseek"` (17) y `"modelID": "deepseek-flash"` (16).
- Estilo: docstrings con prefijo `contrato_cierre_casos_huerfanos R<n>:`, `assert fragment in row, fragment`, como pide `tasks.md`.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] una sola feature `in_progress` (#17); tests de las `done` en verde.
- C3: [x] la #17 no toca servicios ni dependencias; sin secretos ni código copiado.
- C4: [x] 777 tests verdes; tests de contrato sin red ni BD.
- C5: [x] aplica al cierre de sesión del leader (no evaluable por la #17).
- C6: [x] spec completo, R1-R15 cubiertos, tasks en `[x]`.

## Observaciones menores (no bloquean)
1. `progress/impl_contrato_cierre_casos_huerfanos.md:539` dice «81 añadidas» para el diff de `test_contratos_doc.py`; el diff real tiene 105 líneas añadidas (hunk `+620,105`, 11 tests). El resto del informe es correcto.

## Cambios requeridos
Ninguno.
