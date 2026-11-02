# Design — contrato_autorizacion_asesores (feature #13)

> Cómo se construye lo pedido en `requirements.md`. Fuentes de verdad: acceptance de
> la #13, criterios «Decidido por el humano (2026-10-31)» de la #14,
> `progress/propuesta_etapa2.md` §4 y §6, y las decisiones del humano del 2026-10-31
> sobre C1-C6, (d)/R26 y D4 de la #16 (§7). Forma y estilo: los de la #9
> (`specs/contrato_asignar_caso/`). Apoyado en `docs/architecture.md` §3
> (principios 1 y 2) y `docs/conventions.md`.

## 1. Alcance

- Solo se tocan archivos bajo `contracts/`. No se toca `services/`, `eval/`,
  `scripts/`, `docker-compose.yml`, `.github/` ni `requirements*.txt`.
- **Aditivo con dos excepciones cerradas** (R18, R41, R42, R52): se añaden un alias de
  tipo, un modelo de request, un modelo de response, dos ejemplos, una sección de ruta,
  una fila de error común (`403`), tres filas `403` en tablas de rutas existentes, una
  fila `409 case_closed` en la tabla de reply, una fila de supuesto (`S12`) y tests.
  Ningún modelo, ejemplo, ruta o test existente cambia de comportamiento ni se elimina.
  Los tests existentes solo se amplían (entradas nuevas en sus dicts/listas o elementos
  nuevos en sus conjuntos esperados).
- En secciones ya publicadas de `CONTRATOS.md` los cambios son **filas nuevas**, salvo
  las **dos líneas** de §1.1, editadas con permiso expreso del humano (2026-10-31). El
  diff de `CONTRATOS.md` elimina exactamente esas dos líneas y ninguna otra (R52, T39).
  Cualquier otra edición de líneas publicadas sigue prohibida.
- Única edición de texto ya existente fuera de `CONTRATOS.md`, de documentación sin
  efecto en comportamiento: la docstring de módulo de `cases.py` (añade
  `/cases/{id}/authorize`).
- Sin dependencias nuevas. Sin variables de entorno nuevas (el contrato no tiene
  configuración; `ADVISOR_CHAT_IDS` ya existe en handover y S12 es comportamiento).

### 1.1 Excepciones al principio aditivo (lista cerrada)

Decidido por el humano (2026-10-31). Son las únicas líneas publicadas de `contracts/`
que cambian (además de la docstring de `cases.py`). C5 en reply **no** exige editar
ninguna línea publicada: la fila `409 case_closed` de la tabla de reply es nueva (R48).

| # | Línea publicada | R | Test nombrado | Motivo |
|---|-----------------|---|---------------|--------|
| E1 | Fila común `409 \| case_closed` de `## Reglas comunes` (solo la columna «Dónde») | R49 (excepción en R18) | `test_common_rules_case_closed_row_cites_reply` (T50); diff de T39 (R52) | C5: reply sobre `closed` responde `409` |
| E2 | Fila `S11` de `## Supuestos a confirmar` | R50 (excepción en R41) | `test_assumptions_s11_other_advisor_gets_forbidden` (T51); diff de T39 (R52) | (d)/R26: otro asesor recibe `403` |

**E1 — antes** (`CONTRATOS.md`, línea 43 de la versión actual):

```markdown
| 409  | `case_closed`        | `/cases/{id}/assign` | el caso está cerrado (S11) |
```

**E1 — después** (solo cambia «Dónde»; «Cuándo» no se toca):

```markdown
| 409  | `case_closed`        | `/cases/{id}/assign`, `/cases/{id}/reply` | el caso está cerrado (S11) |
```

**E2 — antes** (`CONTRATOS.md`, línea 391 de la versión actual):

```markdown
| S11 | Asignar con `POST /cases/{id}/assign` un caso ya `assigned` responde `200` con `status` = `assigned` sin cambiar el asesor asignado; asignar un caso `closed` responde `409` con `error` = `case_closed` | — |
```

**E2 — después:**

```markdown
| S11 | Asignar con `POST /cases/{id}/assign` un caso ya `assigned` responde `200` con `status` = `assigned` sin cambiar el asesor asignado cuando quien asigna es el asesor asignado; si es otro asesor, responde `403` con `error` = `forbidden` sin cambiar el caso (S12, cambio de la #13); asignar un caso `closed` responde `409` con `error` = `case_closed` | — |
```

La línea «después» de E2 conserva los siete fragmentos que busca
`test_assumptions_include_assign_idempotency` de la #9 (ver §5.1) y no contiene `|`
dentro del texto, así que `_assumption_row` la sigue leyendo.

### Fuera de alcance

- **Implementar** la ruta en handover, aplicar las reglas en `close`/`assign`,
  consultar `authorize` desde el orquestador y propagar su `409`, el registro de
  denegaciones (`advisor_forbidden`) y el ajuste de tests de la #7: todo es la #14.
- **La #15** (`POST /cases/{id}/client-message`, S13, línea `Llama` de `close`): va
  después de esta feature. Aquí no se toca la línea `- **Llama:**` de ninguna ruta
  existente ni se reserva S13. (La línea `Llama` de `authorize` es nueva: §4.1.)
- **Fila común `404 | not_found` y `/cases/{id}/authorize` en la «Dónde» de las filas
  comunes.** La fila `404` no se edita, y en la fila `409` solo se añade
  `/cases/{id}/reply` (E1), que es lo único que autorizó el humano. La ruta nueva
  declara `404` y `409` en su propia tabla `#### Errores` (R9).
- **El «Cuándo» de la fila común `409`** («el caso está cerrado (S11)») y **la prosa de
  la sección `### POST /cases/{id}/assign`** (l.344-347, «Asignar un caso ya `assigned`
  responde igual, `200` …»). No están en la lista cerrada de §1.1; ver §7, dudas.
- **Una fila `502 upstream_error` nueva en `/cases/{id}/reply`** para «handover no
  disponible al autorizar», y **editar el «Cuándo»** de la fila `502 upstream_error`
  existente de `reply` o de la común. Decidido por el humano (C3): se reutiliza la fila
  publicada y S12 lo explica (R23, R45).

## 2. Archivos

| Acción | Ruta | Cambio |
|--------|------|--------|
| modificar | `contracts/lazaro_contracts/cases.py` | añadir `CaseAuthorizeAction`, `CaseAuthorizeRequest` y `CaseAuthorizeResponse` tras `CaseAssignResponse`; ampliar la docstring de módulo |
| modificar | `contracts/lazaro_contracts/__init__.py` | importar los tres nombres desde `.cases`; añadir `"CaseAuthorizeRequest"`, `"CaseAuthorizeResponse"` a `__all__` tras `"CaseAssignResponse"`, y `"CaseAuthorizeAction"` tras `"HandoverReason"` |
| crear | `contracts/examples/case_authorize_request.json` | `{"advisor_id": "222222222", "action": "reply"}` |
| crear | `contracts/examples/case_authorize_response.json` | `{"allowed": true, "case_id": "6f1c2a3e-0000-4000-8000-000000000001"}` |
| modificar | `contracts/CONTRATOS.md` | sección `### POST /cases/{id}/authorize` al final de `## Rutas` (tras `### POST /cases/{id}/assign`); fila `403` en `## Reglas comunes`; fila `403` en los `#### Errores` de reply, close y assign; fila `409 case_closed` en los `#### Errores` de reply; fila `S12` tras S11; excepciones E1 y E2 (§1.1) |
| modificar | `contracts/tests/test_contratos_doc.py` | ampliar `ROUTES`, `OWN_ERRORS`, `SUCCESS_CODES` y el conjunto `expected` de `test_common_rules_document_error_shape_and_codes`; tests nuevos (ver `tasks.md`) |
| modificar | `contracts/tests/test_examples.py` | ampliar imports, `EXAMPLES` y `MODEL_NAMES` |
| modificar | `contracts/tests/test_models.py` | ampliar imports, `BASE_EXAMPLES` e `IDENTIFIER_FIELDS`; tests nuevos (ver `tasks.md`) |
| modificar | `contracts/tests/test_packaging.py` | ampliar `MODEL_NAMES`; test nuevo del alias |

Los ejemplos reutilizan los valores ficticios de `case_assign_*.json` (asesor
`222222222`, mismo `case_id`).

## 3. Firmas nuevas

Estilo de `docs/conventions.md` y de los modelos vecinos (docstring de una línea).

```python
# contracts/lazaro_contracts/cases.py  (tras CaseAssignResponse)

# S12: acciones que se autorizan.
CaseAuthorizeAction = Literal["reply", "close"]


class CaseAuthorizeRequest(ContractModel):
    """Consulta de si un asesor puede responder o cerrar un caso (S12)."""

    # S6: en la versión mínima, el chat_id del asesor en decimal.
    advisor_id: Identifier
    action: CaseAuthorizeAction


class CaseAuthorizeResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/authorize; una denegación es 403 (S12)."""

    allowed: Literal[True]
    case_id: Identifier
```

`CaseAuthorizeAction` se define junto a los modelos que lo usan y se exporta como ya
se hace con `HandoverReason`. `ContractModel` ya tiene `extra="forbid"` (R36) e
`Identifier` ya limita a 1–64 caracteres (R32, R35).

No se añaden excepciones: el contrato solo declara códigos. `forbidden` (403) es
nuevo en el documento; su excepción en los servicios la define la #14, igual que la
propagación del `409 case_closed` en reply.

Docstring de módulo de `cases.py` (la segunda línea cambia):

```python
"""Modelos de /handover, /cases/{id}/reply, /cases/{id}/close, /cases/check-timeouts,
/cases/{id}/assign y /cases/{id}/authorize."""
```

## 4. Cambios en `CONTRATOS.md`

### 4.1 Sección nueva (al final de `## Rutas`)

Misma forma que `### POST /cases/{id}/assign` (los tests parametrizados parsean esa
estructura). La línea `- **Llama:**` nombra también el comando `/cerrar` de la #16
(D4 de la #16, opción (a), decidido por el humano 2026-10-31; R53). Como la línea es
nueva en esta feature, no es editar nada publicado.

```markdown
### POST /cases/{id}/authorize

- **Expone:** handover
- **Llama:** orchestrator (antes de reenviar la respuesta de un asesor con `POST /cases/{id}/reply` y, con el comando `/cerrar` de un asesor, antes de `POST /cases/{id}/close`)
- **Modelos:** `CaseAuthorizeRequest` → `CaseAuthorizeResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Consulta si el asesor
`advisor_id` puede hacer `action` sobre el caso según las reglas de S12. Si puede,
responde `200` con `allowed` = `true`; si no, responde `403` con `error` =
`forbidden` (nunca `allowed` = `false`). Autorizar sobre un caso `closed` responde
`409` con `error` = `case_closed`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que quiere actuar sobre el caso (S6) |
| `action` | `reply` \| `close` | sí | acción que se quiere autorizar: responder o cerrar |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `allowed` | `true` | sí | siempre `true`; si no está autorizado se responde `403` |
| `case_id` | identificador | sí | caso consultado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAuthorizeRequest` |
| 403 | forbidden | el asesor no está autorizado para `action` sobre el caso (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado |
| 500 | internal_error | error inesperado |
```

### 4.2 `## Reglas comunes` → tabla de errores

Fila nueva entre la `422 | validation_error` y la `404 | not_found`:

```markdown
| 403  | `forbidden`          | `/cases/{id}/authorize`, `/cases/{id}/reply`, `/cases/{id}/close`, `/cases/{id}/assign` | el asesor no está autorizado para esa acción sobre el caso (S12) |
```

Y la excepción E1 (§1.1): la «Dónde» de la fila `409 | case_closed` pasa de
`` `/cases/{id}/assign` `` a `` `/cases/{id}/assign`, `/cases/{id}/reply` `` (R49).
Ninguna otra fila existente cambia.

### 4.3 Filas nuevas en rutas existentes

Una línea `403` nueva tras la fila `422 | validation_error` de cada tabla `#### Errores`:

- `### POST /cases/{id}/reply`: `| 403 | forbidden | el asesor no está autorizado a responder el caso; no se envía nada al cliente (S12) |`
- `### POST /cases/{id}/close`: `| 403 | forbidden | el asesor no está autorizado a cerrar el caso; el caso no cambia (S12) |`
- `### POST /cases/{id}/assign`: `| 403 | forbidden | el asesor no está autorizado sobre el caso; el caso no cambia (S12) |`

Y una línea `409` nueva en `### POST /cases/{id}/reply`, tras la fila
`404 | not_found` (R48; mismo criterio que hoy: cada tabla de ruta repite las filas
comunes que le aplican, p. ej. `404` en reply y close, `409` en assign):

- `| 409 | case_closed | el caso está cerrado; no se envía nada al cliente (S12) |`

Orden resultante de reply: 401, 422, 403, 404, 409, 502, 500.

### 4.4 `## Supuestos a confirmar` → fila `S12` tras S11

```markdown
| S12 | Autorización de asesores (`POST /cases/{id}/authorize`). Solo son asesores los chat_id de `ADVISOR_CHAT_IDS` (hasta que existan el panel y la verificación de cuentas); un `advisor_id` que no está en `ADVISOR_CHAT_IDS` recibe `403` con `error` = `forbidden`. Responder (`reply`): un caso `open` o `timed_out` lo responde cualquier asesor registrado y la primera respuesta lo asigna; un caso `assigned` solo lo responde el asesor asignado. Cerrar (`close`): un caso `open` o `timed_out` lo cierra cualquier asesor registrado; un caso `assigned` solo lo cierra el asesor asignado. Sin reasignación y sin rol supervisor. Las mismas reglas se aplican en `POST /cases/{id}/reply` (el orquestador responde `403` sin enviar nada al cliente), `POST /cases/{id}/close` y `POST /cases/{id}/assign` (handover responde `403` sin modificar el caso); asignar un caso ya `assigned` (S11) solo responde `200` al asesor asignado y otro asesor recibe `403`. Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor: el asesor asignado sigue recibiendo `200` sin cambios. Precedencia de errores en `POST /cases/{id}/authorize`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor). En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista. `POST /cases/{id}/close` sobre un caso `closed` sigue S8: `200` sin cambios para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre un caso `closed` responde `409`. `POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Si handover no está disponible para autorizar, el orquestador falla cerrado: no envía la respuesta y responde `502` con `error` = `upstream_error`; es la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`, cuyo texto no se edita. Limitación: la autorización por HTTP con `SERVICE_TOKEN` no impide que un proceso que ya tenga ese token suplante un `advisor_id` registrado; la identidad por persona llega con el remitente validado del webhook de Telegram o con el panel y la verificación de cuentas | — |
```

Cambios frente a la versión aprobada en la tercera vuelta: la frase de reply sobre
`closed` (C5, R46) y la frase «Esto cambia el `200` sin cambios que S11 daba en la #9 …»
(R51). El resto, igual.

### 4.5 Fila `S11` (excepción E2)

Antes/después en §1.1. Solo se reescribe el tramo «sin cambiar el asesor asignado;»
para distinguir al asesor asignado de otro asesor (R50). La frase de `closed` → `409`
no cambia.

La redacción exacta de §4.1-§4.5 puede variar mientras los tests de `tasks.md`
encuentren los fragmentos que buscan (listados en cada task), salvo las líneas
«antes» de E1 y E2, que T39 compara literalmente.

## 5. Cómo se amplían los tests existentes

Regla: solo añadir. Ninguna línea existente de aserción se borra ni se relaja.

- `test_contratos_doc.py`:
  - `ROUTES["POST /cases/{id}/authorize"] = "handover"` → los parametrizados
    existentes (`test_doc_has_a_section_per_route`, `test_route_names_exposing_service`,
    `test_route_names_caller`, `test_route_names_models_in_package`,
    `test_request_table_lists_every_request_field`,
    `test_response_section_has_success_code_and_fields`,
    `test_errors_table_has_common_rows`) cubren R1, R2, R4, R5, R7, R8.
  - `SUCCESS_CODES["POST /cases/{id}/authorize"] = "200"` (R7).
  - `OWN_ERRORS["POST /cases/{id}/authorize"] = [("403", "forbidden"), ("404", "not_found"), ("409", "case_closed")]` (R9).
    Las entradas existentes de `OWN_ERRORS` (reply, close, assign) NO se editan: la
    fila `403` de esas rutas la cubre un test nuevo (R15-R17) y la `409` de reply otro
    (R48).
  - Añadir `("403", "forbidden")` al conjunto `expected` de
    `test_common_rules_document_error_shape_and_codes` (R14, ampliación).
- `test_examples.py`: dos entradas en `EXAMPLES` y dos nombres en `MODEL_NAMES` →
  `test_every_example_validates_against_its_model`, `test_every_example_file_is_mapped`
  y `test_every_model_has_an_example` cubren R38-R40.
- `test_models.py`: `BASE_EXAMPLES` gana `CaseAuthorizeRequest` y
  `CaseAuthorizeResponse` → `test_missing_required_field_is_rejected` (R29, R30, R33)
  y `test_unexpected_field_is_rejected` (R36) los recogen solos;
  `IDENTIFIER_FIELDS` gana `(CaseAuthorizeRequest, "advisor_id")` y
  `(CaseAuthorizeResponse, "case_id")` (R32, R35).
  `test_every_model_has_a_required_field_case_except_check_timeouts_request` sigue
  verde porque ambos modelos tienen campos obligatorios.
- `test_packaging.py`: dos nombres en `MODEL_NAMES` →
  `test_model_is_exported_and_is_base_model` cubre R37 para los modelos.
  `CaseAuthorizeAction` NO va en `MODEL_NAMES` (no es `BaseModel`); lo cubre un test
  nuevo.

Los tests nuevos llevan en su docstring el prefijo `contrato_autorizacion_asesores R<n>`.

El test de R18 (T21) comprueba inclusión, no igualdad: «filas previas ∪ {`403 forbidden`}
⊆ filas». R18 solo prohíbe quitar o modificar filas; con igualdad exacta, una fila que
añada después otra feature de contrato (o la `409` de reply de R48) obligaría a editar
un test de la #13.

### 5.1 Tests de contrato existentes que leen las líneas editadas (E1, E2, R48)

Revisados en `contracts/tests/test_contratos_doc.py` (versión actual, solo lectura).
Resultado: **ningún test existente cambia de código ni pierde aserciones**; los que
leen las líneas editadas siguen verdes porque las líneas «después» conservan todos los
fragmentos que buscan. Se listan para que el implementer no los toque y el reviewer lo
compruebe.

| Test existente (archivo::test) | Qué lee | Cambio en el test | Aserciones (todas se conservan) |
|---|---|---|---|
| `contracts/tests/test_contratos_doc.py::test_assumptions_include_assign_idempotency` (#9 R14) | fila `S11` (E2) | ninguno | `` `POST /cases/{id}/assign` ``, `` `assigned` ``, `` `200` ``, «sin cambiar el asesor», `` `closed` ``, `` `409` ``, `` `case_closed` `` están en la línea «después» de E2 |
| `contracts/tests/test_contratos_doc.py::test_common_rules_case_closed_row_cites_assign` (#9 R12) | fila común `409 \| case_closed` (E1) | ninguno | el regex `^\| 409\s+\| `case_closed`\s+\|(.*)$` sigue casando y `/cases/{id}/assign` sigue en la «Dónde» |
| `contracts/tests/test_contratos_doc.py::test_common_rules_document_error_shape_and_codes` (R10) | filas de la tabla común, incluida la `409` (E1) | solo la ampliación de T9 (`("403", "forbidden")` en `expected`) | `("409", "case_closed")` y las demás siguen en `expected` y en el documento (`<=`) |
| `contracts/tests/test_contratos_doc.py::test_errors_table_has_route_specific_rows[POST /cases/{id}/reply]` (R8) | tabla de errores de reply (gana `403` y `409`) | ninguno (la entrada de `OWN_ERRORS` de reply no se edita) | `{("404", "not_found"), ("502", "upstream_error")} <=` filas: sigue verde |
| `contracts/tests/test_contratos_doc.py::test_errors_table_has_common_rows[POST /cases/{id}/reply]` (R7) | tabla de errores de reply | ninguno | `401` y `422` siguen |
| `contracts/tests/test_contratos_doc.py::test_assign_section_documents_s11` (#9 R11) | prosa de `### POST /cases/{id}/assign` | ninguno (la prosa no se edita, §7 duda 1) | todos sus fragmentos siguen |
| `contracts/tests/test_contratos_doc.py::test_assumptions_mention_s1_to_s10` (R15) | filas S1-S10 | ninguno | no lee S11 |

Tests de servicios que comprueban el `200` de assign para otro asesor o el envío de
reply sobre un caso `closed` no son de contrato: los ajusta la #14 (su design §5).

## 6. Alternativas descartadas

- **Responder siempre `200` con `allowed: bool` (`true`/`false`).** Descartada: el
  acceptance fija `403 forbidden` para la denegación y `allowed` = `true`. Además, un
  cliente que olvidara mirar `allowed` enviaría la respuesta igualmente; con
  `Literal[True]` un `200` significa permiso y cualquier otra cosa es error, lo que
  encaja con «el orquestador falla cerrado».
- **Sin ruta nueva: que el orquestador llame antes a `POST /cases/{id}/assign` y
  trate su `403` como denegación.** Descartada: mezcla consulta con modificación
  (asignaría antes de saber si el envío funciona) y no sirve para `close`, que no
  asigna. Cambiaría además el uso de una ruta publicada.
- **Que el orquestador lea `ADVISOR_CHAT_IDS` o el estado del caso y decida él.**
  Descartada por el principio 1 de `docs/architecture.md` §3: handover es el único
  dueño de los casos y de la lista de asesores; el orquestador pregunta por HTTP.
- **Editar las filas comunes `404 | not_found` y `409 | case_closed` para citar
  `/cases/{id}/authorize`.** Descartada: el humano solo autorizó añadir
  `/cases/{id}/reply` a la fila `409` (E1); cualquier otra edición de filas publicadas
  sigue prohibida (precedente de R13 retirado de la #9).
- **Un `action` más amplio (`assign`, `read`, …) o un rol supervisor.** Descartada: el
  humano decidió solo `reply` y `close`, sin reasignación ni supervisor.
- **Reply sobre un caso `closed` → `403 forbidden`** (el orquestador traduce el `409` de
  `authorize` a `403`; sin filas nuevas). Era la recomendación del leader y la D5 de la
  #14. Descartada por el humano (2026-10-31, C5): el `403` dejaría de significar solo
  «no autorizado» y ocultaría al asesor que el caso ya está cerrado. Se elige `409
  case_closed`, con fila nueva en reply (R48) y la excepción E1 (R49).
- **Mantener S11 sin editar y que solo S12 lo estreche.** Descartada por el humano
  (2026-10-31, (d)): S11 seguiría prometiendo `200` a cualquier asesor y contradiría
  S12 dentro del mismo documento. Se edita S11 (E2, R50) y S12 documenta el cambio
  (R51).
- **Precedencia con `404` antes que el `403` de asesor no registrado.** Descartada por
  el humano (2026-10-31, C1): revelaría a quien no es asesor si un caso existe.
- **Editar el «Cuándo» de la fila `502 upstream_error` de reply o de la común.**
  Descartada por el humano (2026-10-31, C3): se reutiliza la fila publicada y S12 lo
  explica.

## 7. Supuestos a confirmar

| Id | Supuesto | Valor por defecto |
|----|----------|-------------------|
| S12 | Reglas de autorización de la #14, precedencia, casos `closed`, cambio de S11 y limitación de identidad (texto en §4.4). Vienen de los criterios «Decidido por el humano (2026-10-31)» de la #14, de `progress/propuesta_etapa2.md` §4 y §6 y de las decisiones C1-C6 y (d) de abajo | — |
| — | `advisor_id` de `CaseAuthorizeRequest` sigue S6. No es un supuesto nuevo | — |
| — | Quien llama es el orquestador (antes de reenviar con `POST /cases/{id}/reply` y, con el comando `/cerrar` de la #16, antes de `POST /cases/{id}/close`) | — |

Ninguna duda de `docs/proyecto.md` §12 se resuelve aquí; no hay variables de entorno
nuevas en `.env.example`.

### Decisiones del humano (2026-10-31)

Todas cerradas. Ya no hay marcas REVISAR en este spec.

| Id | Duda | Decisión | Requirements / tests | En la #14 / #16 |
|----|------|----------|----------------------|-----------------|
| C1 | (a) Precedencia de errores en `authorize`, `close` y `assign` | **Decidido por el humano (2026-10-31), tal cual.** `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8, C2) → `403` (caso asignado a otro asesor), escrito en S12 | R43 / T41 | #14 D1 (alineada) |
| C2 | (b) `close` de un caso ya `closed` | **Decidido por el humano (2026-10-31), tal cual.** `POST /cases/{id}/close` mantiene S8 (`200` sin cambios) para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre `closed` responde `409` | R44 / T42 | #14 D2 (alineada) |
| C3 | (c) Fallo cerrado | **Decidido por el humano (2026-10-31), tal cual.** Se reutiliza la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`, sin editarla, y se explica en S12 | R23, R45 / T26, T43 | #14 D3 (alineada) |
| C5 | (e) `POST /cases/{id}/reply` sobre un caso `closed` | **Decidido por el humano (2026-10-31), cambia la recomendación.** Responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Fila nueva `409` en reply (R48) y `/cases/{id}/reply` en la «Dónde» de la fila común `409` (E1, R49). La alternativa `403 forbidden` queda descartada (§6) | R46, R48, R49 / T44, T49, T50 | #14 D5 y #16 Rec. 2 **desalineadas** (§9) |
| C6 | Precedencia en `POST /cases/{id}/reply` | **Decidido por el humano (2026-10-31), tal cual.** El orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403 forbidden` aunque el caso no exista | R47 / T45 | #14 D6 (alineada) |
| (d) | `assign` de un caso `assigned` por otro asesor | **Decidido por el humano (2026-10-31).** `403` para otro asesor; el asesor asignado sigue recibiendo `200` sin cambios. Se edita S11 (E2) y S12 documenta que cambia el `200` sin cambios que definió la #9 | R26, R50, R51 / T29, T51, T52 | #14 D4 (alineada) |
| D4 #16 | Línea `- **Llama:**` de `authorize` y el comando `/cerrar` | **Decidido por el humano (2026-10-31), opción (a).** El paréntesis de la línea `Llama` (§4.1) nombra también el comando `/cerrar`, antes de `POST /cases/{id}/close`. Línea nueva en esta feature: no edita nada publicado | R3, R53 / T13, T53 | #16 D4 (alineada con la opción (a)) |

### Dudas que este spec NO resuelve (no se inventan)

1. **Dos líneas publicadas que quedan imprecisas y no están en la lista cerrada de §1.1.**
   - La prosa de `### POST /cases/{id}/assign` (`CONTRATOS.md` l.344-347): «Asignar un
     caso ya `assigned` responde igual, `200` con `status` = `assigned`, sin cambiar el
     asesor asignado …». Tras E2, para otro asesor la respuesta es `403`. La precisan la
     fila `403` de la tabla de assign (R17), S11 editado (R50) y S12 (R26, R51).
   - El «Cuándo» de la fila común `409` dice «(S11)»; tras E1 también aplica a reply,
     cuya regla está en S12.

   El humano autorizó solo la «Dónde» de la fila `409` y el texto de S11, así que este
   spec **no** las edita (valor por defecto). No bloquea. Si el humano quiere que se
   corrijan, se añade una R y una excepción E3/E4 con su antes/después antes de
   implementar; después serían otra feature de contrato.

## 8. Dependencias

Ninguna nueva. Se usa `pydantic>=2.12,<3`, ya fijado en `contracts/requirements.txt`.

## 9. Desalineaciones con la #14 y la #16 (no se editan aquí)

C5 contradice lo que hoy dicen los specs de la #14 y la #16 (ambos escritos con la
recomendación `403 forbidden`). Este spec **no** los edita; deberán corregirse cuando
toque cada feature (su spec_author, con revisión):

**`specs/autorizacion_asesores/` (#14):**

- `design.md` §8, **D5** (l.360): «`authorize` → `409 case_closed` se traduce en el
  orquestador a `403 forbidden`» y su justificación («la tabla de reply no tiene `409`»,
  «añadir `409` a reply sería otra feature de contrato»). Con C5, el orquestador
  propaga `409 case_closed` y la tabla de reply sí tiene `409` (R48).
- `design.md` §8, nota de alineación (l.352-353): «D5 = #13 R46». R46 dice ahora `409`.
- `design.md` §4.2 (flujo, l.229): `AuthorizationDenied("case_closed") → _record_forbidden
  → AdvisorForbidden 403`. Debe acabar en una respuesta `409 case_closed` (excepción
  del orquestador que defina la #14).
- `requirements.md` **R26** (l.178-182): «SI handover responde `409 case_closed` …
  ENTONCES … `403`». Debe ser `409` con `error` = `case_closed`, sin enviar nada.
- `requirements.md` R29/R30 (l.199-205) y `tasks.md` T44: el evento `advisor_forbidden`
  con `code:case_closed` en reply. Que un `409` siga registrándose como denegación es
  decisión de la #14 (su D7 dice que handover no registra denegación por `409`).
- `tasks.md` **T41** (`test_reply_closed_case_returns_403_without_sending`): debe
  esperar `409 case_closed` (y renombrarse). T33/T35/T46 citan R26 y pueden necesitar
  ajuste.
- Sin desalineación en D1 (C1), D2 (C2), D3 (C3), D4 ((d)/R26 de la #13) y D6 (C6).

**`specs/conversacion_cliente_asesor/` (#16):**

- `requirements.md` R14 (l.117-118): «`AdvisorForbidden` … por la D5 de la #14, `409
  case_closed`». Con C5, `reply_to_case` ya no convierte `case_closed` en
  `AdvisorForbidden`; el manejador de `/responder` tendrá que tratar ese caso aparte.
- `design.md` l.35 (D5 de la #14 como base de la Rec. 2), **Rec. 2** (l.464: `/responder`
  sobre `closed` → texto de no autorizado «como la D5 de la #14») y D6 (l.484: «en
  `/responder` el código es siempre `forbidden` porque `reply_to_case` no distingue
  `case_closed`»).
- `tasks.md` T24 (parametrizado con `case_closed` dentro de «forbidden or closed») y
  T33 (códigos de `advisor_forbidden`).
- D4 de la #16 (`/cerrar` autoriza antes de `close`) queda alineada con la línea `Llama`
  de §4.1 (opción (a)). El ajuste de R21, R24, T30 y T33 que pide el cambio 3 de
  `progress/specreview_conversacion_cliente_asesor.md` sigue siendo trabajo de la #16.
