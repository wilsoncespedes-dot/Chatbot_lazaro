# Spec review — contrato_asignar_caso (feature #9)

**Veredicto:** SPEC_APPROVED

## Cobertura del acceptance
- [x] A1 (sección en `CONTRATOS.md`, expone handover, llama orchestrator, modelos, tablas, errores 401/422/404/409/500) → R1-R10.
- [x] A2 (`CaseAssignRequest {advisor_id: Identifier}`, `CaseAssignResponse {status: "assigned", case_id: Identifier}` sobre `ContractModel`, exportados y en `__all__`) → R15, R18, R22.
- [x] A3 (dos ejemplos válidos) → R23, R24, R25.
- [x] A4 (tests de ruta como las existentes + rechazo sin `advisor_id` y con `status` != `assigned`) → R16 (T10, T18), R19 (T20), y T7/T9 para la sección y los ejemplos.
- [x] A5 (S11 en la tabla de supuestos) → R14 (y R11 en la sección de la ruta).
- [x] A6 (cambio aditivo, tests previos verdes) → R26, R27.

## Contrato frente a la fuente de verdad
- [x] Coincide con `specs/traspaso_asesor/design.md` líneas 15-19: expone handover, llama orchestrator, `CaseAssignRequest {advisor_id: Identifier}`, `200` `CaseAssignResponse {status: "assigned", case_id: Identifier}`, errores `401 unauthorized`, `422 validation_error`, `404 not_found`, `409 case_closed`, `500 internal_error`, S11, ejemplos y test de rechazo sin `advisor_id`.
- [x] Coincide con R11-R14 de `specs/traspaso_asesor/requirements.md`: `200` con `{"status": "assigned", "case_id"}` (R11), ya `assigned` → `200` sin cambiar el asesor (R12 → S11), `closed` → `409 case_closed` (R13 → S11), inexistente → `404 not_found` (R14 → R8/R13 de esta feature).
- [x] Nada inventado: ningún campo, código ni estado extra. La alternativa `already_assigned` se descarta explícitamente (design §6).

## Paso `timed_out` → `assigned`
- [x] No se fija en el contrato: design §1 «Fuera de alcance» lo deja como CONFIRMABLE de la #7 y T4 prohíbe mencionar `timed_out` en `CONTRATOS.md`. El único uso de `timed_out` es en T20 como valor de `status` de respuesta que debe rechazarse, lo que es coherente con `Literal["assigned"]` y no fija ninguna transición.

## Carácter aditivo
- [x] Ningún modelo, ruta, ejemplo ni test existente se elimina ni se debilita; en los tests solo se añaden entradas (`ROUTES`, `OWN_ERRORS`, `SUCCESS_CODES`, `expected`, `EXAMPLES`, `MODEL_NAMES`, `BASE_EXAMPLES`, `IDENTIFIER_FIELDS`).
- [x] Las dos ediciones de texto existente son aceptables:
  - Docstring de módulo de `contracts/lazaro_contracts/cases.py` (línea 1): ningún test la lee; es documentación pura.
  - Celda «Dónde» de la fila `404 not_found` de `## Reglas comunes` (`contracts/CONTRATOS.md` línea 42): ningún test depende de esa celda. `test_common_rules_document_error_shape_and_codes` usa la regex `^\| (\d{3})\s+\| \`([a-z_]+)\`` que solo captura HTTP y código; no hay otro consumidor de `CONTRATOS.md` en `services/`, `eval/` ni `scripts/`. Mantenerla sin `/cases/{id}/assign` dejaría la tabla falsa, así que el cambio es necesario.
- [x] Compatibilidades verificadas: `test_assumptions_mention_s1_to_s10` sigue verde con S11; `test_every_model_has_a_required_field_case_except_check_timeouts_request` sigue verde (ambos modelos tienen obligatorios); la fila nueva `| 409  | \`case_closed\` ...` encaja con la regex de R10 de la #1; `NESTED_ONLY` de `test_examples.py` no cambia.

## EARS estricto
- [x] Un solo `DEBE` / `NO DEBE` por requirement, sin verbos blandos.
- [x] R1, R15, R18, R22-R26: ubicuo; R16, R17, R19, R20, R21: no deseado; R27: evento.
- [x] R2-R14 usan «En la sección …, `CONTRATOS.md` DEBE …», la misma forma ubicua con sujeto concreto que R2-R15 de `specs/contratos_servicios/requirements.md` (feature #1, ya aprobada). Se acepta por precedente.
- Nota menor (no bloquea): R25 usa «DEBEN» (plural) y habla de archivos de test como requisito; es verificable (T9) y no añade comportamiento.

## Verificable
- [x] Cada R1-R27 tiene test nombrado en `tasks.md`: R1-R8 por los parametrizados ampliados (T7), R9-R14 por T13-T17 y T8, R15-R21 por T10, T18-T20, R22 por T11, R23-R25 por T9, R26-R27 por la batería previa y la comprobación de diff (T21, T22).

## Sin invenciones
- [x] R10 (frase de `{id}`) y R12/R13 (tabla común) se deducen de «mismo formato que las demás rutas» y de mantener veraz la tabla de errores comunes; no añaden comportamiento.

## Diseño
- [x] Solo toca `contracts/` (principio 2 de `docs/architecture.md`); no toca `services/`.
- [x] Sin dependencias nuevas (`pydantic>=2.12,<3` ya fijado) ni variables de entorno.
- [x] Firmas nuevas explícitas (design §3), sin excepciones nuevas en el contrato.
- [x] 4 alternativas descartadas con motivo (design §6).
- [x] «Supuestos a confirmar» presente (S11; S6 reutilizado); ninguna duda de `docs/proyecto.md` §12 afectada.

## Tasks
- [x] T1-T22 en `[ ]`, en orden (modelos → ejemplos → documento → tests ampliados → tests nuevos → verificación), cada una con sus `R<n>`.
- [x] Entre todas cubren R1-R27.

## Nada peligroso
- [x] No borra datos del usuario, no usa la red, no toca archivos fuera del repo.
