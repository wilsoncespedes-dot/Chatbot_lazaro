# Requirements — contrato_asignar_caso (feature #9)

> Feature: «Contrato: asignar un caso a un asesor». Feature previa de contrato que
> desbloquea la #7 (`traspaso_asesor`). Añade la ruta `POST /cases/{id}/assign`
> (la expone `handover`, la llama `orchestrator`) tal como la define
> `specs/traspaso_asesor/design.md` §«Precondición de contrato» y R11-R14 de
> `specs/traspaso_asesor/requirements.md`.
>
> Todo lo de esta feature vive en `contracts/` (principio 2 de
> `docs/architecture.md`: cambiar un contrato es una feature propia). Ningún
> servicio de `services/` se toca: implementar la ruta en handover y llamarla
> desde el orquestador es trabajo de la #7.
>
> Cambio **estrictamente aditivo**: no se modifica ni elimina ningún modelo, ruta,
> ejemplo ni test existente; los tests existentes solo se amplían.
>
> Notación EARS estricta (`docs/specs.md`). «El sistema» es el paquete de contrato
> (`contracts/`: `CONTRATOS.md`, `lazaro_contracts`, `examples/`, `tests/`).
> Ids estables: no renumerar. Los nombres de test citados están en `tasks.md`.

---

## A. Documento `contracts/CONTRATOS.md`

## R1
El sistema DEBE incluir en `contracts/CONTRATOS.md`, dentro de `## Rutas`, un
encabezado de nivel 3 con el texto exacto `### POST /cases/{id}/assign`.

## R2
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE indicar el
servicio que la expone con la línea `- **Expone:** handover`.

## R3
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE indicar quién la
llama con una línea `- **Llama:** …` que contenga `orchestrator`.

## R4
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE nombrar en la
línea `- **Modelos:**` los modelos `CaseAssignRequest` (primero) y
`CaseAssignResponse` (segundo), entre comillas invertidas.

## R5
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE incluir la
subsección `#### Request` con una tabla de columnas
`Campo | Tipo | Obligatorio | Descripción` que contenga la fila del campo
`advisor_id`.

## R6
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE incluir la
subsección `#### Respuesta` con el código de éxito `` `200 OK` `` y una tabla de
columnas `Campo | Tipo | Obligatorio | Descripción` que contenga las filas de los
campos `status` y `case_id`.

## R7
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE incluir la
subsección `#### Errores` con una tabla de columnas `HTTP | error | Cuándo` que
contenga las filas `401 unauthorized` y `422 validation_error`.

## R8
En la tabla `#### Errores` de `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE
contener las filas `404 not_found` y `409 case_closed`.

## R9
En la tabla `#### Errores` de `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE
contener la fila `500 internal_error`.

## R10
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE indicar que
`{id}` es el `case_id` (identificador, 1–64 caracteres), con la misma frase que
usan `### POST /cases/{id}/reply` y `### POST /cases/{id}/close`.

## R11
En la sección `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE describir el
comportamiento de S11: asignar un caso ya `assigned` responde `200` sin cambiar
el asesor asignado, y asignar un caso `closed` responde `409` `case_closed`,
citando `S11`.

## R12
En la tabla de errores de `## Reglas comunes`, `CONTRATOS.md` DEBE contener una
fila `409 | case_closed` cuya columna «Dónde» cite `/cases/{id}/assign`.

## R13
(Retirado por el humano en la aprobación del spec: la fila `404 | not_found` existente de la
tabla de errores de `## Reglas comunes` de `CONTRATOS.md` no se modifica; el cambio en esa tabla
queda estrictamente aditivo, solo la fila nueva de R12. El número no se reutiliza.)

## R14
En la tabla de `## Supuestos a confirmar`, `CONTRATOS.md` DEBE incluir una fila
`S11` que recoja que asignar con `POST /cases/{id}/assign` un caso ya `assigned`
responde `200` sin cambiar el asesor, y que asignar un caso `closed` responde
`409` con `case_closed`.

---

## B. Modelos en `contracts/lazaro_contracts/cases.py`

## R15
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` la clase
`CaseAssignRequest`, subclase de `ContractModel`, cuyo único campo es
`advisor_id: Identifier`, obligatorio.

## R16
SI un `CaseAssignRequest` se valida sin el campo `advisor_id` ENTONCES el sistema
DEBE lanzar `ValidationError`.

## R17
SI el `advisor_id` de un `CaseAssignRequest` es vacío o tiene más de
`MAX_IDENTIFIER_LENGTH` caracteres ENTONCES el sistema DEBE lanzar
`ValidationError`.

## R18
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` la clase
`CaseAssignResponse`, subclase de `ContractModel`, con exactamente los campos
obligatorios `status: Literal["assigned"]` y `case_id: Identifier`.

## R19
SI un `CaseAssignResponse` se valida con un `status` distinto de `assigned`
ENTONCES el sistema DEBE lanzar `ValidationError`.

## R20
SI el `case_id` de un `CaseAssignResponse` es vacío o tiene más de
`MAX_IDENTIFIER_LENGTH` caracteres ENTONCES el sistema DEBE lanzar
`ValidationError`.

## R21
SI un `CaseAssignRequest` o un `CaseAssignResponse` se valida con un campo no
declarado ENTONCES el sistema DEBE lanzar `ValidationError`.

## R22
El paquete `lazaro_contracts` DEBE exportar `CaseAssignRequest` y
`CaseAssignResponse` en `lazaro_contracts/__init__.py` y listarlos en `__all__`.

---

## C. Ejemplos en `contracts/examples/`

## R23
El sistema DEBE incluir `contracts/examples/case_assign_request.json`, válido
contra `CaseAssignRequest`.

## R24
El sistema DEBE incluir `contracts/examples/case_assign_response.json`, válido
contra `CaseAssignResponse`.

## R25
El mapa `EXAMPLES` y la lista `MODEL_NAMES` de `contracts/tests/test_examples.py`
DEBEN incluir los dos ejemplos nuevos y los dos modelos nuevos, de modo que los
tests de cobertura de ejemplos los exijan.

---

## D. Carácter aditivo

## R26
El sistema NO DEBE modificar el comportamiento ni eliminar ningún modelo,
constante, ejemplo JSON, sección de ruta o supuesto (S1–S10) existente de
`contracts/`.

## R27
CUANDO se ejecuta la batería completa de tests del repositorio tras el cambio, el
sistema DEBE pasar todos los tests que existían antes de la feature, sin que se
haya eliminado ninguno ni debilitado ninguna de sus aserciones.
