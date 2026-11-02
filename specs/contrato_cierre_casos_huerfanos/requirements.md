# Requirements — contrato_cierre_casos_huerfanos (feature #17)

> Feature: «Contrato: cierre de casos huérfanos (asesor retirado de
> `ADVISOR_CHAT_IDS`)». Feature de contrato previa a la #14 (`autorizacion_asesores`).
> Solo toca `contracts/`. Actualiza el supuesto S12 (publicado por la #13, done) con la
> decisión del humano del 2026-10-31: opción C + procedimiento A de
> `progress/specreview_conversacion_cliente_asesor.md` §6 y «Decisiones para el
> humano», punto 2.
>
> Fuentes de verdad: acceptance de la #17 en `feature_list.json` y la decisión del
> humano (2026-10-31), que este spec no cambia ni amplía:
>
> - Caso huérfano = caso `assigned` cuyo `advisor_id` ya no está en `ADVISOR_CHAT_IDS`.
> - Caso `assigned` con `advisor_id` nulo: también es huérfano (decidido por el humano,
>   2026-10-31). Un asesor registrado puede cerrarlo (`close` y `authorize(close)`), pero no
>   responderlo ni asignarlo (`403`). Ver `design.md` §1.1, «Decisión: `advisor_id` nulo».
> - Cualquier asesor registrado puede CERRARLO (`POST /cases/{id}/close` y `authorize`
>   con `action` = `close` → permitido). No es reasignar: el caso pasa a `closed`.
> - Nadie más puede responderlo ni asignarlo (`reply`/`assign`/`authorize(reply)` de otro
>   asesor → `403 forbidden`, como hoy).
> - Procedimiento A: antes de retirar a un asesor, este cierra sus casos; handover
>   registrará al arrancar cuántos casos huérfanos hay, sin ids (lo implementa la #14).
> - El contrato se cambia SOLO con esta feature: la #14 no edita el contrato publicado.
>
> Cambio con **una excepción cerrada** al principio aditivo: la única línea publicada que
> cambia es la fila `S12` de `## Supuestos a confirmar` (excepción H1, antes/después
> exactos en `design.md` §1.1). Ninguna otra línea de `CONTRATOS.md` se edita, añade ni
> elimina; ningún modelo, ejemplo ni test existente cambia (R12-R15).
>
> Notación EARS estricta (`docs/specs.md`). «El sistema» es el paquete de contrato
> (`contracts/`). Ids estables: no renumerar. Los nombres de test están en `tasks.md`.

---

## A. Supuesto S12 — definición y regla de cierre

## R1
La fila `S12` de `contracts/CONTRATOS.md` DEBE definir caso huérfano como un caso
`` `assigned` `` cuyo `` `advisor_id` `` es nulo o ya no está en `` `ADVISOR_CHAT_IDS` ``.
*(Actualizado: el `advisor_id` nulo, decidido por el humano el 2026-10-31.)*

## R2
La fila `S12` de `CONTRATOS.md` DEBE indicar que un caso huérfano lo cierra cualquier
asesor registrado con `` `POST /cases/{id}/close` ``, que lo pasa a `` `closed` ``.

## R3
La fila `S12` de `CONTRATOS.md` DEBE indicar que `` `authorize` `` con `` `action` `` =
`` `close` `` sobre un caso huérfano responde `` `200` `` con `` `allowed` `` =
`` `true` ``.

## R4
La fila `S12` de `CONTRATOS.md` DEBE indicar que cerrar un caso huérfano no es
reasignarlo.

## R5
La fila `S12` de `CONTRATOS.md` DEBE recoger que un caso `` `assigned` `` solo lo cierra
el asesor asignado, salvo un caso huérfano.

---

## B. Supuesto S12 — sin responder ni asignar un caso huérfano

## R6
La fila `S12` de `CONTRATOS.md` DEBE indicar que `` `POST /cases/{id}/reply` `` y
`` `authorize` `` con `` `action` `` = `` `reply` `` de otro asesor sobre un caso
huérfano responden `` `403` `` con `` `error` `` = `` `forbidden` ``.

## R7
La fila `S12` de `CONTRATOS.md` DEBE indicar que `` `POST /cases/{id}/assign` `` de otro
asesor sobre un caso huérfano responde `` `403` `` con `` `error` `` = `` `forbidden` ``
sin modificar el caso.

---

## C. Supuesto S12 — precedencia de errores

## R8
La fila `S12` de `CONTRATOS.md` DEBE indicar, a continuación del escalón
`` `403` (caso asignado a otro asesor) `` de la precedencia de errores, que ese escalón no
se aplica a `` `POST /cases/{id}/close` `` ni a `` `authorize` `` con `` `action` `` =
`` `close` `` sobre un caso huérfano.

## R9
La fila `S12` de `CONTRATOS.md` DEBE indicar que, en `` `POST /cases/{id}/close` `` y en
`` `authorize` `` con `` `action` `` = `` `close` `` sobre un caso huérfano, el cierre está
permitido una vez superados los tres primeros escalones de la precedencia publicada por la
#13 (`403` asesor no registrado → `404` caso inexistente → caso `closed`).

---

## D. Supuesto S12 — procedimiento de retirada (procedimiento A)

## R10
La fila `S12` de `CONTRATOS.md` DEBE indicar que, antes de quitar su chat_id de
`` `ADVISOR_CHAT_IDS` ``, el asesor cierra sus casos.

## R11
La fila `S12` de `CONTRATOS.md` DEBE indicar que, al arrancar, handover registra cuántos
casos huérfanos hay, sin sus ids.

---

## E. Excepción cerrada al principio aditivo

## R12
CUANDO se aplica el cambio de esta feature, el diff de `contracts/CONTRATOS.md` frente a
su versión previa DEBE constar exactamente de una línea eliminada, la línea «antes» de
H1, y una línea añadida, la línea «después» de H1 (`design.md` §1.1), comparadas
literalmente.

## R13
CUANDO se aplica el cambio de esta feature, el sistema NO DEBE modificar, crear ni
eliminar ningún archivo de `contracts/` distinto de `contracts/CONTRATOS.md` y
`contracts/tests/test_contratos_doc.py`.

## R14
CUANDO se aplica el cambio de esta feature, el sistema NO DEBE eliminar ni modificar
ninguna línea existente de `contracts/tests/test_contratos_doc.py`.

## R15
CUANDO se ejecuta la batería completa de tests del repositorio tras el cambio, el sistema
DEBE pasar todos los tests, incluidos todos los que existían antes de la feature.

---

## Cobertura del acceptance

| Criterio del acceptance (#17) | Requirements |
|---|---|
| 1. Cualquier asesor registrado puede CERRAR un caso huérfano por `POST /cases/{id}/close` y con `authorize` `action` = `close` | R1, R2, R3, R4, R5 |
| 2. Un caso huérfano NO lo puede responder ni asignar ningún otro asesor; `reply`/`assign` siguen respondiendo `403` | R6, R7 |
| 3. S12 se actualiza, incluida la precedencia (el escalón `403` por caso asignado a otro asesor no aplica a `close`/`authorize(close)` sobre un huérfano); excepción cerrada con antes/después exacta | R8, R9, R12 |
| 4. Procedimiento A documentado (cierre previo; recuento al arrancar sin ids, lo implementa la #14) | R10, R11 |
| 5. Tests de contrato: S12 contiene la regla y la prohibición; ninguna otra fila publicada se edita; ningún test existente se elimina ni se debilita | R1-R11 (tests nuevos), R12, R13, R14, R15 |
