# Tasks — contrato_cierre_casos_huerfanos (feature #17)

> Solo se tocan `contracts/CONTRATOS.md` (una línea: excepción H1) y
> `contracts/tests/test_contratos_doc.py` (solo añadir). Ver `design.md` §1 y §2.
> Ningún test existente se edita (`design.md` §5): si alguno falla, se corrige la línea de
> `CONTRATOS.md`, nunca el test.
> Cada test nuevo va en un bloque nuevo al final de `contracts/tests/test_contratos_doc.py`
> (`# ── contrato_cierre_casos_huerfanos (feature #17) ──…`), usa
> `row = _assumption_row("S12")`, comprueba cada fragmento con
> `assert fragment in row, fragment` y lleva docstring con el prefijo
> `contrato_cierre_casos_huerfanos R<n>:`. Los fragmentos son literales de la línea
> «después» de H1 (`design.md` §1.1).

## Preparación

- [x] T1 — Antes de editar nada, copiar `contracts/` entero a una carpeta temporal fuera del repositorio (p. ej. `$SCRATCH/contracts_before`, excluyendo `__pycache__` y `.pytest_cache`). Es la referencia de T14 y T15 (no se usa `git diff` contra `HEAD`: `design.md` §4). Cubre: R12, R13, R14.

## Documento

- [x] T2 — En `contracts/CONTRATOS.md`, sustituir la línea `| S12 | …` (línea «antes» de H1, `design.md` §1.1) por la línea «después» de H1, copiada literal, en una sola línea y con fin de línea LF. Ninguna otra línea se edita, añade ni elimina. Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12.

## Tests nuevos (`contracts/tests/test_contratos_doc.py`)

- [x] T3 — `test_assumptions_s12_defines_orphan_case`: S12 contiene «Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o ya no está en `ADVISOR_CHAT_IDS`» (incluye el `advisor_id` nulo, decidido por el humano el 2026-10-31; `design.md` §1.1). Cubre: R1.
- [x] T4 — `test_assumptions_s12_orphan_close_by_any_registered_advisor`: S12 contiene «Un caso huérfano lo cierra cualquier asesor registrado» y «`POST /cases/{id}/close` lo pasa a `closed`». Cubre: R2.
- [x] T5 — `test_assumptions_s12_orphan_authorize_close_allowed`: S12 contiene «`authorize` con `action` = `close` responde `200` con `allowed` = `true`». Cubre: R3.
- [x] T6 — `test_assumptions_s12_orphan_close_is_not_reassignment`: S12 contiene «cerrarlo no es reasignarlo». Cubre: R4.
- [x] T7 — `test_assumptions_s12_assigned_close_rule_has_orphan_exception`: S12 contiene «un caso `assigned` solo lo cierra el asesor asignado, salvo un caso huérfano». Cubre: R5.
- [x] T8 — `test_assumptions_s12_orphan_reply_forbidden`: S12 contiene «Un caso huérfano no lo responde ni lo asigna ningún otro asesor» y «`POST /cases/{id}/reply` y `authorize` con `action` = `reply` responden `403` con `error` = `forbidden`». Cubre: R6.
- [x] T9 — `test_assumptions_s12_orphan_assign_forbidden`: S12 contiene «Un caso huérfano no lo responde ni lo asigna ningún otro asesor» y «`POST /cases/{id}/assign` responde `403` con `error` = `forbidden` sin modificar el caso». Cubre: R7.
- [x] T10 — `test_assumptions_s12_precedence_other_advisor_step_skips_orphan_close`: S12 contiene, contiguo, «→ `403` (caso asignado a otro asesor), escalón que no se aplica a `POST /cases/{id}/close` ni a `authorize` con `action` = `close` sobre un caso huérfano». Cubre: R8.
- [x] T11 — `test_assumptions_s12_precedence_orphan_close_allowed_after_first_steps`: S12 contiene «superados los tres primeros escalones, el cierre está permitido» y la cadena publicada por la #13 «`403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8)». Cubre: R9.
- [x] T12 — `test_assumptions_s12_documents_advisor_retirement_procedure`: S12 contiene «antes de quitar su chat_id de `ADVISOR_CHAT_IDS`, el asesor cierra sus casos». Cubre: R10.
- [x] T13 — `test_assumptions_s12_documents_orphan_count_at_startup`: S12 contiene «al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids». Cubre: R11.

## Verificación

- [x] T14 — Comprobación de diff de `CONTRATOS.md`: `git diff --no-index -U0 "$SCRATCH/contracts_before/CONTRATOS.md" contracts/CONTRATOS.md` muestra exactamente una línea eliminada, idéntica a la «antes» de H1, y una añadida, idéntica a la «después» de H1 (`design.md` §1.1), comparadas literalmente (sin diferencias de espacios ni de fin de línea). Cubre: R12.
- [x] T15 — Comprobación de archivos: `diff -rq --exclude=__pycache__ --exclude=.pytest_cache "$SCRATCH/contracts_before" contracts` solo lista `CONTRATOS.md` y `tests/test_contratos_doc.py`; y `git diff --no-index -U0 "$SCRATCH/contracts_before/tests/test_contratos_doc.py" contracts/tests/test_contratos_doc.py` no tiene ninguna línea eliminada (`^-[^-]`), solo añadidas. Cubre: R13, R14.
- [x] T16 — Ejecutar `python -m pytest contracts` y después la batería completa (`./init.sh` o `python -m pytest`): todo en verde, incluidos sin cambios los tests existentes de `design.md` §5. Cubre: R15.
- [x] T17 — Documentar en `progress/impl_contrato_cierre_casos_huerfanos.md` la trazabilidad de abajo, el resultado de T14 y T15 (líneas eliminadas/añadidas) y el recuento de la batería de T16. Cubre: R12, R13, R14, R15.

## Trazabilidad final

| R | Verificación |
|---|--------------|
| R1 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_defines_orphan_case` (T3; fragmento con «es nulo o ya no está») |
| R2 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_close_by_any_registered_advisor` (T4) |
| R3 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_authorize_close_allowed` (T5) |
| R4 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_close_is_not_reassignment` (T6) |
| R5 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_assigned_close_rule_has_orphan_exception` (T7) |
| R6 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_reply_forbidden` (T8) |
| R7 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_orphan_assign_forbidden` (T9) |
| R8 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_precedence_other_advisor_step_skips_orphan_close` (T10) |
| R9 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_precedence_orphan_close_allowed_after_first_steps` (T11) |
| R10 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_documents_advisor_retirement_procedure` (T12) |
| R11 | `contracts/tests/test_contratos_doc.py::test_assumptions_s12_documents_orphan_count_at_startup` (T13) |
| R12 | comprobación de diff de `CONTRATOS.md` (T14) |
| R13 | comprobación de archivos de `contracts/` (T15) |
| R14 | comprobación de diff de `test_contratos_doc.py`, solo líneas añadidas (T15) |
| R15 | batería completa en verde (T16), con los tests existentes de `design.md` §5 sin cambios |
