# Requirements — contrato_listar_casos_asesor (feature #33)

> Publica en el contrato y en handover `GET /cases?advisor_id=<id>`: lista mínima,
> de solo lectura, de los casos que un asesor puede gestionar según S12 (#13/#14) y
> la regla de huérfanos (#17). Lo consumirá `GET /asesor/cases` del panel (#29).
> Filtros y campos: borrador de `specs/panel_asesores/design.md` §«Dependencia #33»
> y `progress/spec_panel_asesores.md`. Este spec **no cambia** S12 ni las reglas de
> #14/#17; solo las lee.
>
> Servicios: **contrato** (`contracts/`, R1–R7, R21) y **handover** (R8–R20, R22).
> Cambio de contrato aditivo: ninguna línea publicada de `CONTRATOS.md` se edita.

## Contrato (`contracts/`)

## R1
El sistema DEBE documentar en `contracts/CONTRATOS.md` una sección `### GET /cases`
con `Expone: handover`, `Llama: orchestrator (panel de asesores, #29)`, el
parámetro de query `advisor_id`, la respuesta `200`, la tabla de errores
(`401 unauthorized`, `422 validation_error`, `500 internal_error`) y la exigencia de
`X-Service-Token`.

## R2
El sistema DEBE exponer en `lazaro_contracts` el modelo `CaseListQuery` con un único
campo obligatorio `advisor_id` de tipo `Identifier` que rechaza campos no declarados.

## R3
El sistema DEBE exponer en `lazaro_contracts` el modelo `CaseListItem` con
exactamente los campos `case_id` (`Identifier`), `status`
(`open` | `timed_out` | `assigned`), `created_at` (`AwareDatetime`) y `actions`
(lista no vacía y sin repetidos de `reply` | `assign` | `close`).

## R4
El sistema DEBE exponer en `lazaro_contracts` el modelo `CaseListResponse` como
arreglo JSON de nivel superior de `CaseListItem` con como máximo
`MAX_CASE_LIST_LIMIT` (200) elementos, y la constante
`DEFAULT_CASE_LIST_LIMIT` = 50.

## R5
SI un `CaseListItem` recibe un campo de contacto o de conversación (`contact_id`,
`chat_id`, `reason`, `last_messages`, `advisor_id` u otro no declarado) ENTONCES el
sistema DEBE rechazarlo con error de validación.

## R6
El sistema DEBE incluir los ejemplos `case_list_query.json`,
`case_list_response.json` (un caso `open`, uno `assigned` al asesor y uno huérfano)
y `case_list_response_empty.json` (`[]`) en `contracts/examples/`.

## R7
El sistema DEBE añadir a `## Supuestos a confirmar` la fila `S14` con las reglas de
inclusión, las `actions` por caso, el orden, el límite `CASE_LIST_LIMIT` (default
50, máximo 200), la lista vacía para un asesor no registrado y la ausencia de
cursor, sin modificar ninguna fila existente (S1–S13).

## Handover (`services/handover/`)

## R8
SI una petición a `GET /cases` llega sin `X-Service-Token` válido ENTONCES handover
DEBE responder `401` con `error` = `unauthorized`.

## R9
SI `GET /cases` llega sin `advisor_id`, con un `advisor_id` vacío o de más de 64
caracteres, o con un parámetro de query no declarado ENTONCES handover DEBE
responder `422` con `error` = `validation_error`.

## R10
CUANDO `GET /cases` recibe un `advisor_id` que no está en `ADVISOR_CHAT_IDS`,
handover DEBE responder `200` con `[]`.

## R11
CUANDO un asesor registrado pide `GET /cases`, handover DEBE incluir cada caso
`open` o `timed_out` con `actions` = `["reply", "assign", "close"]`.

## R12
CUANDO un asesor registrado pide `GET /cases`, handover DEBE incluir cada caso
`assigned` cuyo `advisor_id` es el solicitado con `actions` = `["reply", "close"]`.

## R13
CUANDO un asesor registrado pide `GET /cases`, handover DEBE incluir cada caso
huérfano (`assigned` con `advisor_id` nulo o fuera de `ADVISOR_CHAT_IDS`) con
`actions` = `["close"]`.

## R14
handover NO DEBE incluir en `GET /cases` casos `closed` ni casos `assigned` a otro
asesor registrado.

## R15
handover DEBE ordenar el resultado de `GET /cases` por `created_at` ascendente y, a
igual `created_at`, por `case_id` ascendente.

## R16
handover DEBE devolver como máximo `CASE_LIST_LIMIT` casos (los primeros según R15),
aplicando el límite después de los filtros R10–R14.

## R17
SI `CASE_LIST_LIMIT` no es un entero entre 1 y 200 ENTONCES handover DEBE fallar al
construir `Settings` (no arranca).

## R18
Cada elemento de la respuesta de `GET /cases` DEBE contener solo `case_id`,
`status`, `created_at` y `actions` (sin `contact_id`, `chat_id`, `reason`,
`last_messages` ni `advisor_id`).

## R19
CUANDO handover atiende `GET /cases`, el sistema NO DEBE modificar casos ni
registrar denegaciones ni notificaciones.

## R20
SI falla inesperadamente la lectura del repositorio en `GET /cases` ENTONCES
handover DEBE responder `500` con `error` = `internal_error` sin stack trace.

## Requirements añadidos al partir R6 y R17 (IDs estables)

## R21
Cada ejemplo de R6 DEBE validar contra su modelo (`CaseListQuery` o
`CaseListResponse`).

## R22
handover DEBE usar `CASE_LIST_LIMIT` = 50 cuando la variable no está definida.

## Trazabilidad con el acceptance de #33

| Acceptance | Requirements |
|------------|--------------|
| CONTRATOS.md define la ruta, token, parámetros, respuesta, errores y límite | R1, R7 |
| Modelos tipados y ejemplos | R2, R3, R4, R6, R21 |
| Solo `case_id`, `status`, `created_at`, `actions` | R3, R5, R18 |
| Reglas de inclusión en handover; no registrado → lista vacía | R10–R14, R19 |
| `CASE_LIST_LIMIT=50`, orden por antigüedad y desempate por `case_id` | R4, R15, R16, R17, R22 |
| Pruebas de contrato y handover; `./init.sh` pasa | R1–R22 (tests en `tasks.md`) |
