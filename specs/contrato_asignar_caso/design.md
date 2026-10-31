# Design — contrato_asignar_caso (feature #9)

> Cómo se construye lo pedido en `requirements.md`. Fuente de verdad del contrato:
> `specs/traspaso_asesor/design.md` §«Precondición de contrato» y R11-R14 de
> `specs/traspaso_asesor/requirements.md`. Estilo y estructura: los de la feature
> #1 (`specs/contratos_servicios/`). Apoyado en `docs/architecture.md` §3
> (principios 1 y 2) y `docs/conventions.md`.

## 1. Alcance

- Solo se tocan archivos bajo `contracts/`. No se toca `services/`, `eval/`,
  `scripts/`, `docker-compose.yml`, `.github/` ni `requirements*.txt`.
- **Aditivo** (R26, R27): se añaden un modelo de request, un modelo de response,
  dos ejemplos, una sección de ruta, una fila de error común, una fila de
  supuesto y tests. Ningún modelo, ejemplo, ruta o test existente cambia de
  comportamiento ni se elimina. Los tests existentes solo se amplían (entradas
  nuevas en sus dicts/listas parametrizadas o elementos nuevos en sus conjuntos
  esperados).
- Única edición de texto ya existente, de documentación sin efecto en
  comportamiento: la docstring de módulo de `cases.py` (añade
  `/cases/{id}/assign` a la lista de rutas).
- La fila `404 | not_found` existente de la tabla de errores de
  `## Reglas comunes` NO se modifica: la edición de su celda «Dónde» (antiguo
  R13) fue retirada por decisión humana en la aprobación del spec. En esa tabla
  el cambio es estrictamente aditivo (solo la fila nueva `409 | case_closed`, R12).
- Sin dependencias nuevas. Sin variables de entorno nuevas (el contrato no tiene
  configuración; S11 es comportamiento, no un valor configurable).

### Fuera de alcance

- **Implementar la ruta** en handover o llamarla desde el orquestador: es la #7.
- **La transición `timed_out` → `assigned`.** Es un supuesto CONFIRMABLE de la #7
  (`specs/traspaso_asesor/design.md`, tabla de supuestos; R11 de su
  requirements), no del contrato. `CONTRATOS.md` NO la menciona: la sección de la
  ruta y S11 solo fijan los casos `assigned` (200 sin cambio) y `closed`
  (409). Qué estados internos acepta handover para pasar a `assigned` es
  decisión del servicio.
- Cualquier cambio en `POST /cases/{id}/reply`, `POST /cases/{id}/close` o en los
  demás modelos.

## 2. Archivos

| Acción | Ruta | Cambio |
|--------|------|--------|
| modificar | `contracts/lazaro_contracts/cases.py` | añadir `CaseAssignRequest` y `CaseAssignResponse` después de `CaseCloseResponse`; ampliar la docstring de módulo |
| modificar | `contracts/lazaro_contracts/__init__.py` | importar los dos modelos desde `.cases` y añadirlos a `__all__` (tras `"CaseCloseResponse"`) |
| crear | `contracts/examples/case_assign_request.json` | `{"advisor_id": "222222222"}` |
| crear | `contracts/examples/case_assign_response.json` | `{"status": "assigned", "case_id": "6f1c2a3e-0000-4000-8000-000000000001"}` |
| modificar | `contracts/CONTRATOS.md` | sección `### POST /cases/{id}/assign` (al final de `## Rutas`, tras `### POST /cases/check-timeouts`); fila nueva `409 case_closed` en `## Reglas comunes` (la fila `404` no se toca); fila `S11` en `## Supuestos a confirmar` |
| modificar | `contracts/tests/test_contratos_doc.py` | ampliar `ROUTES`, `OWN_ERRORS`, `SUCCESS_CODES` y el conjunto `expected` de `test_common_rules_document_error_shape_and_codes`; tests nuevos (ver `tasks.md`) |
| modificar | `contracts/tests/test_examples.py` | ampliar imports, `EXAMPLES` y `MODEL_NAMES` |
| modificar | `contracts/tests/test_models.py` | ampliar imports, `BASE_EXAMPLES` e `IDENTIFIER_FIELDS`; tests nuevos (ver `tasks.md`) |
| modificar | `contracts/tests/test_packaging.py` | ampliar `MODEL_NAMES` |

Los ejemplos reutilizan los valores ficticios de `case_close_request.json` y
`case_close_response.json` (mismo asesor `222222222`, mismo `case_id`).

## 3. Firmas nuevas

Estilo de `docs/conventions.md` y de los modelos vecinos (docstring de una línea).

```python
# contracts/lazaro_contracts/cases.py  (tras CaseCloseResponse)

class CaseAssignRequest(ContractModel):
    """Asignación de un caso a un asesor (la pide el orquestador, S11)."""

    # S6: en la versión mínima, el chat_id del asesor en decimal.
    advisor_id: Identifier


class CaseAssignResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/assign (idempotente si ya estaba assigned, S11)."""

    status: Literal["assigned"]
    case_id: Identifier
```

`ContractModel` ya tiene `extra="forbid"` (R21) e `Identifier` ya limita a 1–64
caracteres (R17, R20): no hace falta código adicional de validación.

No se añaden excepciones: el contrato solo declara códigos de error. El código
`case_closed` (409) es nuevo en el documento; su excepción en el servicio
(`CaseClosed`) la define la #7.

## 4. Sección nueva en `CONTRATOS.md`

Misma forma que `### POST /cases/{id}/close` (los tests de R1–R9 parsean esa
estructura):

```markdown
### POST /cases/{id}/assign

- **Expone:** handover
- **Llama:** orchestrator (al reenviar la respuesta de un asesor con `POST /cases/{id}/reply`)
- **Modelos:** `CaseAssignRequest` → `CaseAssignResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Asignar un caso ya
`assigned` responde igual, `200` con `status` = `assigned`, sin cambiar el asesor
asignado; asignar un caso `closed` responde `409` con `error` = `case_closed`
(S11).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor al que se asigna el caso (S6) |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `assigned` | sí | siempre `assigned` |
| `case_id` | identificador | sí | caso asignado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAssignRequest` |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado (S11) |
| 500 | internal_error | error inesperado |
```

`## Reglas comunes` → tabla de errores:

- fila nueva tras la 404: `| 409  | `case_closed`        | `/cases/{id}/assign` | el caso está cerrado (S11) |` (R12).
- la fila 404 existente no se modifica (R13 retirado por decisión humana).

`## Supuestos a confirmar` → fila nueva tras S10 (R14):

`| S11 | Asignar con `POST /cases/{id}/assign` un caso ya `assigned` responde `200` con `status` = `assigned` sin cambiar el asesor asignado; asignar un caso `closed` responde `409` con `error` = `case_closed` | — |`

La redacción exacta puede variar mientras los tests de `tasks.md` encuentren los
fragmentos que buscan (`` `POST /cases/{id}/assign` ``, `` `assigned` ``,
`` `200` ``, `` `closed` ``, `` `409` ``, `` `case_closed` ``, «sin cambiar el
asesor»).

## 5. Cómo se amplían los tests existentes

Regla: solo añadir. Ninguna línea existente de aserción se borra ni se relaja.

- `test_contratos_doc.py`:
  - `ROUTES["POST /cases/{id}/assign"] = "handover"` → los tests parametrizados
    existentes (`test_doc_has_a_section_per_route`, `test_route_names_exposing_service`,
    `test_route_names_caller`, `test_route_names_models_in_package`,
    `test_request_table_lists_every_request_field`,
    `test_response_section_has_success_code_and_fields`,
    `test_errors_table_has_common_rows`) cubren R1, R2, R3 (parcial), R4, R5, R6, R7.
  - `SUCCESS_CODES["POST /cases/{id}/assign"] = "200"` (R6).
  - `OWN_ERRORS["POST /cases/{id}/assign"] = [("404", "not_found"), ("409", "case_closed")]` (R8).
  - Añadir `("409", "case_closed")` al conjunto `expected` de
    `test_common_rules_document_error_shape_and_codes` (R12, ampliación).
- `test_examples.py`: añadir las dos entradas a `EXAMPLES` y los dos nombres a
  `MODEL_NAMES` → `test_every_example_validates_against_its_model`,
  `test_every_example_file_is_mapped` y `test_every_model_has_an_example` cubren
  R23, R24, R25.
- `test_models.py`: añadir a `BASE_EXAMPLES`
  `CaseAssignRequest: ("case_assign_request.json", None)` y
  `CaseAssignResponse: ("case_assign_response.json", None)` → los genéricos
  `test_missing_required_field_is_rejected` (R16 y parte de R18) y
  `test_unexpected_field_is_rejected` (R21) los recogen solos; añadir a
  `IDENTIFIER_FIELDS` `(CaseAssignRequest, "advisor_id")` y
  `(CaseAssignResponse, "case_id")` (R17, R20).
  `test_every_model_has_a_required_field_case_except_check_timeouts_request`
  sigue verde porque ambos modelos tienen campos obligatorios.
- `test_packaging.py`: añadir los dos nombres a `MODEL_NAMES` →
  `test_model_is_exported_and_is_base_model` cubre R22.
  `test_package_imports_only_stdlib_and_pydantic` ya recorre `cases.py`.

Tests nuevos (nombres en `tasks.md`): los de R3 (contiene `orchestrator`), R9,
R10, R11, R12 (fila común), R14, R15, R18, R19 y R16 explícito (R13 retirado).

## 6. Alternativas descartadas

- **Reutilizar `CaseCloseResponse` o crear un `CaseStatusResponse` genérico con
  `status: Literal["closed", "assigned"]`.** Obligaría a modificar un modelo
  existente (rompe el carácter aditivo, R26) y aflojaría la validación de
  `POST /cases/{id}/close`, que hoy rechaza cualquier `status` distinto de
  `closed` (`test_case_close_response_rejects_invalid_status`).
- **Responder `409` (p. ej. `already_assigned`) al asignar un caso ya `assigned`.**
  Descartado por S11 y por R12 de la #7: el orquestador puede reenviar varias
  respuestas del mismo asesor y llamar a `assign` en cada una; la idempotencia
  evita tratar como error el caso normal (mismo criterio que S8 para `close`).
  Además, inventaría un código de error que la fuente de verdad no define.
- **Sin ruta `assign`: añadir `assigned_to` a `HandoverResponse` o que el
  orquestador lleve el estado del caso.** Ya descartado en
  `specs/traspaso_asesor/design.md`: el estado vive en handover y el orquestador
  no puede leer su base (`docs/architecture.md` §3.1); además cambiaría un modelo
  existente.
- **`PATCH /cases/{id}` con `{"status": "assigned", ...}`.** Más genérico pero
  abre transiciones que nadie ha pedido (p. ej. reabrir) y rompe la convención
  del contrato (todas las rutas son `POST` con verbo explícito).

## 7. Supuestos a confirmar

| Id | Supuesto | Valor por defecto |
|----|----------|-------------------|
| S11 | Asignar un caso ya `assigned` responde `200` (`status` = `assigned`) sin cambiar el asesor asignado; asignar un caso `closed` responde `409` `case_closed`. Viene de R12-R13 de `traspaso_asesor` y del acceptance de la #9 | — |
| — | `advisor_id` de `CaseAssignRequest` sigue S6 (texto; en la versión mínima, el chat_id del asesor en decimal). No es un supuesto nuevo | — |
| — | Quien llama es el orquestador (al procesar `POST /cases/{id}/reply`), según la precondición de la #7 | — |

Ninguna duda de `docs/proyecto.md` §12 se resuelve aquí; no hay variables de
entorno nuevas en `.env.example`.

## 8. Dependencias

Ninguna nueva. Se usa `pydantic>=2.12,<3`, ya fijado en `contracts/requirements.txt`.
