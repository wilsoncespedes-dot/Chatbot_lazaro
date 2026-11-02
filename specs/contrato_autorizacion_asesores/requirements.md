# Requirements — contrato_autorizacion_asesores (feature #13)

> Feature: «Contrato: autorización de asesores sobre un caso». Feature previa de
> contrato que desbloquea la #14 (`autorizacion_asesores`). Añade la ruta
> `POST /cases/{id}/authorize` (la expone `handover`, la llama `orchestrator`), el
> código `403 forbidden` y el supuesto S12.
>
> Fuentes de verdad: acceptance de la #13 y criterios «Decidido por el humano
> (2026-10-31)» de la #14 en `feature_list.json`; `progress/propuesta_etapa2.md` §4 y §6.
> Modelo de forma: la #9 (`specs/contrato_asignar_caso/`).
>
> Todo vive en `contracts/` (principio 2 de `docs/architecture.md`: cambiar un
> contrato es una feature propia). Implementar la ruta en handover y consultarla
> desde el orquestador es trabajo de la #14. La #15 (`contrato_conversacion_caso`,
> S13) va DESPUÉS y no se anticipa aquí.
>
> Cambio **aditivo con dos excepciones cerradas** (decididas por el humano el
> 2026-10-31): no se elimina ni debilita ningún modelo, ruta, ejemplo, supuesto ni
> test existente. En secciones ya publicadas de `CONTRATOS.md` el cambio son filas
> nuevas (`403 forbidden` ×4, `409 case_closed` en reply, `S12`), salvo dos líneas
> publicadas que se editan con permiso expreso del humano: la «Dónde» de la fila común
> `409 | case_closed` (R49) y la fila `S11` (R50). Ninguna otra línea publicada se
> edita (R18, R41, R52). Antes/después exactos en `design.md` §1.1.
>
> Notación EARS estricta (`docs/specs.md`). «El sistema» es el paquete de contrato
> (`contracts/`: `CONTRATOS.md`, `lazaro_contracts`, `examples/`, `tests/`).
> Ids estables: no renumerar. Los nombres de test citados están en `tasks.md`.

---

## A. Documento `contracts/CONTRATOS.md` — ruta nueva

## R1
El sistema DEBE incluir en `contracts/CONTRATOS.md`, dentro de `## Rutas`, un
encabezado de nivel 3 con el texto exacto `### POST /cases/{id}/authorize`.

## R2
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE indicar el
servicio que la expone con la línea `- **Expone:** handover`.

## R3
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE indicar quién la
llama con una línea `- **Llama:** …` que contenga `orchestrator`.

## R4
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE nombrar en la
línea `- **Modelos:**` los modelos `CaseAuthorizeRequest` (primero) y
`CaseAuthorizeResponse` (segundo), entre comillas invertidas.

## R5
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE incluir la
subsección `#### Request` con una tabla de columnas
`Campo | Tipo | Obligatorio | Descripción` que contenga las filas de los campos
`advisor_id` y `action`.

## R6
En la tabla `#### Request` de `### POST /cases/{id}/authorize`, la fila del campo
`action` DEBE listar los valores `` `reply` `` y `` `close` ``.

## R7
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE incluir la
subsección `#### Respuesta` con el código de éxito `` `200 OK` `` y una tabla de
columnas `Campo | Tipo | Obligatorio | Descripción` que contenga las filas de los
campos `allowed` y `case_id`.

## R8
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE incluir la
subsección `#### Errores` con una tabla de columnas `HTTP | error | Cuándo` que
contenga las filas `401 unauthorized` y `422 validation_error`.

## R9
En la tabla `#### Errores` de `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE
contener las filas `403 forbidden`, `404 not_found` y `409 case_closed`.

## R10
En la tabla `#### Errores` de `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE
contener la fila `500 internal_error`.

## R11
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE indicar que
`{id}` es el `case_id` (identificador, 1–64 caracteres), con la misma frase que
usan `### POST /cases/{id}/reply`, `### POST /cases/{id}/close` y
`### POST /cases/{id}/assign`.

## R12
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE indicar que un
asesor autorizado recibe `200` con `allowed` = `true` y uno no autorizado recibe
`403` con `error` = `forbidden` (nunca `allowed` = `false`), citando `S12`.

## R13
En la sección `### POST /cases/{id}/authorize`, `CONTRATOS.md` DEBE indicar que
autorizar sobre un caso `closed` responde `409` con `error` = `case_closed`.

---

## B. Documento `contracts/CONTRATOS.md` — `403 forbidden` en tablas existentes

## R14
En la tabla de errores de `## Reglas comunes`, `CONTRATOS.md` DEBE contener una
fila nueva `403 | forbidden` cuya columna «Dónde» cite `/cases/{id}/authorize`,
`/cases/{id}/reply`, `/cases/{id}/close` y `/cases/{id}/assign`.

## R15
En la tabla `#### Errores` de `### POST /cases/{id}/reply`, `CONTRATOS.md` DEBE
contener una fila nueva `403 forbidden`.

## R16
En la tabla `#### Errores` de `### POST /cases/{id}/close`, `CONTRATOS.md` DEBE
contener una fila nueva `403 forbidden`.

## R17
En la tabla `#### Errores` de `### POST /cases/{id}/assign`, `CONTRATOS.md` DEBE
contener una fila nueva `403 forbidden`.

## R18
CUANDO se añaden las filas de R14-R17 y R48, el sistema NO DEBE modificar ni eliminar
ninguna línea ya existente de esas cuatro tablas ni del resto de las secciones
`## Reglas comunes`, `### POST /cases/{id}/reply`, `### POST /cases/{id}/close` y
`### POST /cases/{id}/assign`, con la única excepción de la fila común
`409 | case_closed`, cuya columna «Dónde» cambia como fija R49.

> Reescrita el 2026-10-31 (decisión del humano sobre C5): antes no tenía excepción.

---

## C. Supuesto S12 en `## Supuestos a confirmar`

## R19
En la tabla de `## Supuestos a confirmar`, `CONTRATOS.md` DEBE incluir una fila
`S12` que cite `` `POST /cases/{id}/authorize` `` y recoja que solo son asesores los
chat_id de `` `ADVISOR_CHAT_IDS` `` y que un `advisor_id` que no está en esa lista
recibe `` `403` `` con `` `forbidden` ``.

## R20
La fila `S12` de `CONTRATOS.md` DEBE recoger la regla de responder: un caso
`` `open` `` o `` `timed_out` `` lo responde cualquier asesor registrado y la primera
respuesta lo asigna; un caso `` `assigned` `` solo lo responde el asesor asignado.

## R21
La fila `S12` de `CONTRATOS.md` DEBE recoger la regla de cerrar: un caso `` `open` ``
o `` `timed_out` `` lo cierra cualquier asesor registrado; un caso `` `assigned` ``
solo lo cierra el asesor asignado.

## R22
La fila `S12` de `CONTRATOS.md` DEBE indicar que no hay reasignación ni rol
supervisor.

## R23
La fila `S12` de `CONTRATOS.md` DEBE indicar que, si handover no está disponible
para autorizar, el orquestador falla cerrado: no envía la respuesta y responde
`` `502` `` con `` `upstream_error` ``.

## R24
La fila `S12` de `CONTRATOS.md` DEBE indicar que las mismas reglas se aplican en
`` `POST /cases/{id}/reply` `` (el orquestador responde `403` sin enviar nada al
cliente) y en `` `POST /cases/{id}/close` `` y `` `POST /cases/{id}/assign` `` (handover
responde `403` sin modificar el caso).

## R25
La fila `S12` de `CONTRATOS.md` DEBE recoger la limitación de identidad: la
autorización por HTTP con `` `SERVICE_TOKEN` `` no impide que un proceso que ya
tenga ese token suplante un `` `advisor_id` `` registrado.

## R26
La fila `S12` de `CONTRATOS.md` DEBE indicar que asignar un caso ya `` `assigned` ``
(S11) solo responde `200` al asesor asignado y que otro asesor recibe `403`.

---

## D. Modelos en `contracts/lazaro_contracts/cases.py`

## R27
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` el alias
`CaseAuthorizeAction = Literal["reply", "close"]`.

## R28
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` la clase
`CaseAuthorizeRequest`, subclase de `ContractModel`, con exactamente los campos
obligatorios `advisor_id: Identifier` y `action: CaseAuthorizeAction`.

## R29
SI un `CaseAuthorizeRequest` se valida sin el campo `advisor_id` ENTONCES el
sistema DEBE lanzar `ValidationError`.

## R30
SI un `CaseAuthorizeRequest` se valida sin el campo `action` ENTONCES el sistema
DEBE lanzar `ValidationError`.

## R31
SI un `CaseAuthorizeRequest` se valida con un `action` distinto de `reply` y de
`close` ENTONCES el sistema DEBE lanzar `ValidationError`.

## R32
SI el `advisor_id` de un `CaseAuthorizeRequest` es vacío o tiene más de
`MAX_IDENTIFIER_LENGTH` caracteres ENTONCES el sistema DEBE lanzar
`ValidationError`.

## R33
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` la clase
`CaseAuthorizeResponse`, subclase de `ContractModel`, con exactamente los campos
obligatorios `allowed: Literal[True]` y `case_id: Identifier`.

## R34
SI un `CaseAuthorizeResponse` se valida con un `allowed` distinto de `true`
ENTONCES el sistema DEBE lanzar `ValidationError`.

## R35
SI el `case_id` de un `CaseAuthorizeResponse` es vacío o tiene más de
`MAX_IDENTIFIER_LENGTH` caracteres ENTONCES el sistema DEBE lanzar
`ValidationError`.

## R36
SI un `CaseAuthorizeRequest` o un `CaseAuthorizeResponse` se valida con un campo no
declarado ENTONCES el sistema DEBE lanzar `ValidationError`.

## R37
El paquete `lazaro_contracts` DEBE exportar `CaseAuthorizeRequest`,
`CaseAuthorizeResponse` y `CaseAuthorizeAction` en `lazaro_contracts/__init__.py`
y listarlos en `__all__`.

---

## E. Ejemplos en `contracts/examples/`

## R38
El sistema DEBE incluir `contracts/examples/case_authorize_request.json`, válido
contra `CaseAuthorizeRequest`.

## R39
El sistema DEBE incluir `contracts/examples/case_authorize_response.json`, válido
contra `CaseAuthorizeResponse`.

## R40
El mapa `EXAMPLES` y la lista `MODEL_NAMES` de `contracts/tests/test_examples.py`
DEBEN incluir los dos ejemplos nuevos y los dos modelos nuevos, de modo que los
tests de cobertura de ejemplos los exijan.

---

## F. Carácter aditivo

## R41
El sistema NO DEBE modificar el comportamiento ni eliminar ningún modelo,
constante, ejemplo JSON, sección de ruta o supuesto (S1–S11) existente de
`contracts/`, con la única excepción de la fila `S11`, que cambia como fija R50.

> Reescrita el 2026-10-31 (decisión del humano sobre (d)/R26): antes no tenía excepción.

## R42
CUANDO se ejecuta la batería completa de tests del repositorio tras el cambio, el
sistema DEBE pasar todos los tests que existían antes de la feature, sin que se
haya eliminado ninguno ni debilitado ninguna de sus aserciones.

---

## G. Supuesto S12 — precedencia de errores y casos cerrados

> Añadidas tras `progress/specreview_contrato_autorizacion_asesores.md` (cambios 1-3).
> **Decidido por el humano (2026-10-31)** (`design.md` §7, C1-C6): R43, R44, R45 y R47
> se aceptan tal cual; R46 se reescribe (C5: reply sobre `closed` → `409 case_closed`,
> no `403 forbidden`). La #14 (`specs/autorizacion_asesores/design.md` §8, D1-D6)
> coincide con D1-D4 y D6, y queda desalineada con C5 en su D5 (ver `design.md` §9).

## R43
La fila `S12` de `CONTRATOS.md` DEBE fijar la precedencia de errores de
`` `POST /cases/{id}/authorize` ``, `` `POST /cases/{id}/close` `` y
`` `POST /cases/{id}/assign` `` en este orden: `403` por asesor no registrado, `404`
por caso inexistente, caso `closed` (`409` en `authorize` y `assign`; `200` sin
cambios por S8 en `close`, R44) y `403` por caso asignado a otro asesor.

## R44
La fila `S12` de `CONTRATOS.md` DEBE indicar que `` `POST /cases/{id}/close` `` sobre
un caso `` `closed` `` sigue S8 (`200` sin cambios) para cualquier asesor registrado,
y que `authorize` con `action` = `close` sobre un caso `` `closed` `` responde `409`.

## R45
La fila `S12` de `CONTRATOS.md` DEBE indicar que el `502` del fallo cerrado (R23) es
la fila `502 upstream_error` ya publicada de `` `POST /cases/{id}/reply` ``.

## R46
La fila `S12` de `CONTRATOS.md` DEBE indicar que `` `POST /cases/{id}/reply` `` sobre
un caso `` `closed` `` responde `409` con `error` = `case_closed`, sin enviar nada al
cliente.

> Reescrita el 2026-10-31 (C5, decidido por el humano). Antes: `403` con `error` =
> `forbidden`. Esa alternativa queda descartada en `design.md` §6.

## R47
La fila `S12` de `CONTRATOS.md` DEBE indicar que en `` `POST /cases/{id}/reply` `` el
orquestador autoriza antes de comprobar si el caso existe, de modo que un
`advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no
exista.

---

## H. Decisiones del humano (2026-10-31): reply sobre `closed`, S11 y línea `Llama`

> Añadidas el 2026-10-31 con las decisiones del humano: C5 (R48, R49), (d)/R26 (R50,
> R51), cierre de las excepciones al principio aditivo (R52) y D4 de la #16, opción (a)
> (R53). Antes/después exactos de las líneas editadas en `design.md` §1.1.

## R48
En la tabla `#### Errores` de `### POST /cases/{id}/reply`, `CONTRATOS.md` DEBE
contener una fila nueva `409 case_closed`.

## R49
En la tabla de errores de `## Reglas comunes`, la columna «Dónde» de la fila
`409 | case_closed` DEBE citar `/cases/{id}/assign` y `/cases/{id}/reply`.

## R50
La fila `S11` de `CONTRATOS.md` DEBE indicar que asignar un caso ya `` `assigned` ``
responde `200` sin cambiar el asesor asignado cuando quien asigna es el asesor
asignado, y que otro asesor recibe `403` con `error` = `forbidden`.

## R51
La fila `S12` de `CONTRATOS.md` DEBE indicar que la regla de R26 cambia el `200` sin
cambios que S11 daba en la #9 a cualquier asesor, y que el asesor asignado sigue
recibiendo `200` sin cambios.

## R52
CUANDO se aplica el cambio de esta feature, el sistema NO DEBE eliminar ni modificar
en `contracts/CONTRATOS.md` ninguna línea distinta de las dos líneas «antes» de R49
(fila común `409 | case_closed`) y R50 (fila `S11`).

## R53
En la sección `### POST /cases/{id}/authorize`, la línea `- **Llama:**` de
`CONTRATOS.md` DEBE nombrar el comando `` `/cerrar` `` y `` `POST /cases/{id}/close` ``.

---

## Historial de cambios

- **2026-10-31, tras la 1.ª y 2.ª vuelta de `progress/specreview_contrato_autorizacion_asesores.md`:**
  R43-R47 añadidas con la recomendación del leader (REVISAR).
- **2026-10-31, decisiones del humano:**
  - C1, C2, C3 y C6 aceptadas tal cual: R43, R44, R45 y R47 sin cambios de texto; deja de
    haber marca REVISAR.
  - C5 cambia: R46 reescrita (`409 case_closed`, no `403 forbidden`); R48 y R49 nuevas.
  - (d)/R26 decidida: `403` para otro asesor. R26 sin cambios; R50 (edición de S11) y R51
    (S12 documenta el cambio frente a la #9) nuevas.
  - Principio aditivo con excepciones cerradas: R18 y R41 reescritas; R52 nueva.
  - D4 de la #16, opción (a): R53 nueva (línea `Llama` de `authorize` con `/cerrar`).
  - Ningún id existente se renumera.
