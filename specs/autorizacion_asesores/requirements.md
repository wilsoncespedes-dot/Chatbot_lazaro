# Requirements — autorizacion_asesores (feature #14)

> Feature: «Autorización de asesores para responder y cerrar casos». Solo un asesor autorizado
> puede responder, asignar o cerrar un caso. Handover, dueño de los casos y de
> `ADVISOR_CHAT_IDS`, decide; el orquestador consulta antes de enviar.
>
> Fuentes de verdad: acceptance de la #14 en `feature_list.json` (en especial los criterios
> «Decidido por el humano (2026-10-31)») y `progress/propuesta_etapa2.md` §4 y §6. Consume
> **sin modificarlo** el contrato de la #13 (`specs/contrato_autorizacion_asesores/`, `done`):
> `POST /cases/{id}/authorize`, `CaseAuthorizeRequest`, `CaseAuthorizeResponse`,
> `CaseAuthorizeAction`, el código `403 forbidden`, la fila `409 case_closed` de reply y el
> supuesto S12 (C1-C6, R26). Consume la regla de cierre de casos huérfanos que publica en S12 la
> #17 (`contrato_cierre_casos_huerfanos`, `done`), con su texto real de `contracts/CONTRATOS.md`.
> Asume la #10 (`ADVISOR_CHAT_IDS` llega validada al construir `Settings`). No edita `contracts/`.
>
> Decisiones aplicadas (detalle en `design.md` §8):
> - **Decidido por el humano (2026-10-31) en la #13:** C1 (precedencia), C2 (`close` sobre
>   `closed` → `200` por S8), C3 (fallo cerrado con la fila `502` publicada), C6 (`reply` autoriza
>   antes de comprobar si el caso existe) y R26 de la #13 (`assign` de otro asesor → `403`).
> - **Decidido por el humano (2026-10-31) para esta feature** (numeración de la lista del
>   humano del 2026-10-31, usada en todo el spec):
>   1. C5: `reply` sobre un caso `closed` → `409 case_closed` propagado, sin envío; un `409` no
>      genera `advisor_forbidden` (R26, R29, R30, R53).
>   2. Asignación y cierre condicionales (opción (b) de la D1 de la #12). Una carrera no puede
>      cerrar un caso que ya quedó asignado a otro asesor: el cierre condicional exige en la
>      misma sentencia el estado o asesor autorizado (R35, R37-R43, R54, R55).
>   3. D7: solo los `403` cuentan como denegación, incluido el `403` por carrera perdida (R19,
>      R20, R38, R55). D8: si falla guardar la denegación → `500` (R22). D9: sin contacto
>      vinculado, solo el log del orquestador (R30).
>   4. D12: el recuento de huérfanos va en el `lifespan` (R49, R52). D13: si la consulta falla,
>      log `WARNING` y el servicio arranca igual (R51).
>   5. `threading.Lock` alrededor de `_run` en `PostgresCaseRepository` (R44, R45).
>   6. El candado equivalente del orquestador es la feature #18 `candado_repositorio_orquestador`
>      (previa a la #16); aquí solo se referencia, sin R.
>   7. Casos huérfanos: los cierra cualquier asesor registrado, sin `reply` ni `assign`; cuenta
>      el `advisor_id` nulo (R46-R52, R54).
> - No queda ningún requirement marcado REVISAR. Siguen abiertos, fuera de esta feature, los
>   riesgos (d) y (e) de la #12 (`design.md` §8.4).
>
> Notación EARS estricta (`docs/specs.md`). Cada requirement indica el servicio. Ids estables:
> no renumerar; los nuevos van al final. Los nombres de test están en `tasks.md`.
>
> Vocabulario:
> - **Asesor registrado**: `advisor_id` que cumple R1.
> - **Caso sin asignar**: caso en estado `open` o `timed_out`.
> - **Caso huérfano**: caso `assigned` cuyo `advisor_id` es nulo o no es asesor registrado.
>   Decidido por el humano (2026-10-31), decisión 7; regla publicada por la #17 en S12 de
>   `contracts/CONTRATOS.md` («un caso `assigned` cuyo `advisor_id` es nulo o ya no está en
>   `ADVISOR_CHAT_IDS`»), incluido el `advisor_id` nulo.
> - **Registro de denegación**: fila de la tabla nueva de handover (R19, R21).
> - **Escritura condicional**: una única sentencia que comprueba el estado (y, en el cierre, el
>   asesor) y escribe a la vez, y dice si cambió la fila (R37, R41, R43, R54).

---

## Servicio handover

### Quién es asesor

## R1
El sistema (handover) DEBE considerar asesor registrado a un `advisor_id` únicamente si es
idéntico, carácter a carácter, a la representación decimal canónica (`str(int)`) de uno de los
ids de `ADVISOR_CHAT_IDS`.

### `POST /cases/{id}/authorize`

## R2
CUANDO handover recibe `POST /cases/{id}/authorize` de un asesor registrado sobre un caso sin
asignar, con `action` = `reply` o `close`, el sistema (handover) DEBE responder `200` con
`{"allowed": true, "case_id": <id>}`.

## R3
CUANDO handover recibe `POST /cases/{id}/authorize` de un asesor registrado sobre un caso
`assigned` cuyo `advisor_id` es el mismo que el de la petición, con `action` = `reply` o
`close`, el sistema (handover) DEBE responder `200` con `{"allowed": true, "case_id": <id>}`.

## R4
SI handover recibe `POST /cases/{id}/authorize` con un `advisor_id` que no es asesor registrado
ENTONCES el sistema (handover) DEBE responder `403` con `{"error": "forbidden", ...}` sea cual
sea el estado del caso, también si el caso no existe y también si el caso estaba asignado a ese
mismo `advisor_id`. *Decidido por el humano (2026-10-31): C1 de la #13.*

## R5
SI handover recibe `POST /cases/{id}/authorize` de un asesor registrado sobre un caso que no
existe ENTONCES el sistema (handover) DEBE responder `404` con `{"error": "not_found", ...}`.

## R6
SI handover recibe `POST /cases/{id}/authorize` de un asesor registrado sobre un caso `closed`
ENTONCES el sistema (handover) DEBE responder `409` con `{"error": "case_closed", ...}`, con
`action` = `reply` y con `action` = `close`. *Decidido por el humano (2026-10-31): C1 y C2 de la
#13.*

## R7
SI handover recibe `POST /cases/{id}/authorize` de un asesor registrado sobre un caso
`assigned` a otro asesor que es asesor registrado, con `action` = `reply` o `close`, ENTONCES el
sistema (handover) DEBE responder `403` con `{"error": "forbidden", ...}`. *(Reescrito: el caso
huérfano se rige por R46 y R48.)*

## R8
CUANDO handover responde `POST /cases/{id}/authorize`, el sistema (handover) NO DEBE modificar
ningún caso ni enviar nada por `POST /send`.

## R9
SI una petición a `POST /cases/{id}/authorize` llega sin `X-Service-Token` válido ENTONCES el
sistema (handover) DEBE responder `401` con `{"error": "unauthorized", ...}` sin modificar
casos ni guardar registros de denegación.

## R10
SI el cuerpo de `POST /cases/{id}/authorize` no valida contra `CaseAuthorizeRequest` ENTONCES
el sistema (handover) DEBE responder `422` con `{"error": "validation_error", ...}`.

### `POST /cases/{id}/assign`

## R11
SI handover recibe `POST /cases/{id}/assign` con un `advisor_id` que no es asesor registrado
ENTONCES el sistema (handover) DEBE responder `403` con `{"error": "forbidden", ...}` sin
modificar el caso, sea cual sea su estado, también si el caso no existe. *Decidido por el humano
(2026-10-31): C1 de la #13.*

## R12
SI handover recibe `POST /cases/{id}/assign` de un asesor registrado sobre un caso `assigned` a
otro asesor (registrado o no) ENTONCES el sistema (handover) DEBE responder `403` con
`{"error": "forbidden", ...}` sin modificar el caso. *Decidido por el humano (2026-10-31): R26 de
la #13.*

## R13
CUANDO handover recibe `POST /cases/{id}/assign` del asesor al que ya está asignado el caso, el
sistema (handover) DEBE responder `200` con `{"status": "assigned", "case_id": <id>}` sin
cambiar el asesor ni la fecha de asignación (S11). *Decidido por el humano (2026-10-31): R26 de
la #13.*

### `POST /cases/{id}/close`

## R14
SI handover recibe `POST /cases/{id}/close` con un `advisor_id` que no es asesor registrado
ENTONCES el sistema (handover) DEBE responder `403` con `{"error": "forbidden", ...}` sin
modificar el caso, sea cual sea su estado, también si el caso no existe. *Decidido por el humano
(2026-10-31): C1 de la #13.*

## R15
SI handover recibe `POST /cases/{id}/close` de un asesor registrado sobre un caso `assigned` a
otro asesor que es asesor registrado ENTONCES el sistema (handover) DEBE responder `403` con
`{"error": "forbidden", ...}` sin modificar el caso. *(Reescrito: el caso huérfano se rige por
R47.)*

## R16
CUANDO handover recibe `POST /cases/{id}/close` del asesor al que está asignado un caso
`assigned`, el sistema (handover) DEBE marcarlo `closed` con ese `advisor_id` y la fecha del
reloj inyectado, y responder `200` con `{"status": "closed", "case_id": <id>}`.

## R17
CUANDO handover recibe `POST /cases/{id}/close` de cualquier asesor registrado sobre un caso sin
asignar, el sistema (handover) DEBE marcarlo `closed` con ese `advisor_id` y la fecha del reloj
inyectado, y responder `200` con `{"status": "closed", "case_id": <id>}`.

## R18
CUANDO handover recibe `POST /cases/{id}/close` de cualquier asesor registrado sobre un caso ya
`closed`, el sistema (handover) DEBE responder `200` con `{"status": "closed", "case_id": <id>}`
sin cambiar la fecha ni el asesor del cierre original (S8), aunque el caso estuviera asignado a
otro asesor. *Decidido por el humano (2026-10-31): C2 de la #13.*

### Registro de denegaciones

## R19
CUANDO handover responde `403 forbidden` en `POST /cases/{id}/authorize`,
`POST /cases/{id}/assign` o `POST /cases/{id}/close`, el sistema (handover) DEBE guardar un
registro de denegación con el `case_id` de la ruta, el `advisor_id` recibido, la acción
(`reply` o `close` según el `action` de `authorize`; `assign` en la ruta de asignar; `close` en
la ruta de cerrar) y la fecha del reloj inyectado, también cuando el `403` se debe a una carrera
perdida (R38, R55). *Decidido por el humano (2026-10-31), decisión 3: D7.*

## R20
CUANDO handover responde a `POST /cases/{id}/authorize`, `POST /cases/{id}/assign` o
`POST /cases/{id}/close` con un código distinto de `403`, el sistema (handover) NO DEBE guardar
ningún registro de denegación. *Decidido por el humano (2026-10-31), decisión 3: D7 (solo los
`403` cuentan como denegación).*

## R21
El sistema (handover) DEBE guardar los registros de denegación a través de un método nuevo del
`CaseRepository` con versión falsa en memoria y versión PostgreSQL que cree su tabla con
`CREATE TABLE IF NOT EXISTS` en el primer uso y use siempre SQL parametrizado (`%s`).

## R22
SI guardar el registro de denegación falla ENTONCES el sistema (handover) DEBE responder `500`
con `{"error": "internal_error", ...}` sin modificar el caso. *Decidido por el humano
(2026-10-31), decisión 3: D8.*

---

## Servicio orchestrator

### `POST /cases/{id}/reply`: orden y resultado de la autorización

## R23
CUANDO el orquestador recibe `POST /cases/{id}/reply` con token y cuerpo válidos, el sistema
(orchestrator) DEBE llamar a `POST /cases/{id}/authorize` de handover con el `advisor_id`
recibido y `action` = `reply` antes de consultar el vínculo caso-contacto, llamar a
`POST /send`, guardar mensajes o eventos y llamar a `POST /cases/{id}/assign`. *Decidido por el
humano (2026-10-31): C6 de la #13.*

## R24
CUANDO handover autoriza la respuesta (`200` con `allowed` = `true` y el mismo `case_id`), el
sistema (orchestrator) DEBE seguir el flujo de la #7 en este orden: consultar el vínculo
caso-contacto, enviar con `POST /send`, guardar el mensaje `advisor` y el evento
`advisor_reply`, y llamar a `POST /cases/{id}/assign`.

## R25
SI handover responde `403 forbidden` a la autorización ENTONCES el sistema (orchestrator) DEBE
responder `403` con `{"error": "forbidden", ...}` sin llamar a `POST /send`, sin guardar el
mensaje, sin registrar `advisor_reply` y sin llamar a `POST /cases/{id}/assign`.

## R26
SI handover responde `409 case_closed` a la autorización ENTONCES el sistema (orchestrator) DEBE
responder `409` con `{"error": "case_closed", ...}` sin llamar a `POST /send`, sin guardar el
mensaje, sin registrar `advisor_reply` y sin llamar a `POST /cases/{id}/assign`. *Decidido por el
humano (2026-10-31): C5 de la #13 (reescrito; antes `403`).*

## R27
SI handover responde `404 not_found` a la autorización ENTONCES el sistema (orchestrator) DEBE
responder `404` con `{"error": "not_found", ...}` sin llamar a `POST /send`, sin guardar nada y
sin llamar a `POST /cases/{id}/assign`.

## R28
SI la autorización no se puede obtener de handover (error de red o tiempo agotado, cualquier
código no contemplado en R24-R27, o un cuerpo que no valida contra `CaseAuthorizeResponse` o
trae otro `case_id`) ENTONCES el sistema (orchestrator) DEBE responder `502` con
`{"error": "upstream_error", ...}` sin llamar a `POST /send`, sin guardar nada y sin llamar a
`POST /cases/{id}/assign` (fallo cerrado). *Decidido por el humano (2026-10-31): acceptance de la
#14 y C3 de la #13.*

### Registro de denegaciones en el orquestador

## R29
CUANDO el orquestador responde `403` por R25 y el caso está vinculado a un contacto, el sistema
(orchestrator) DEBE registrar en ese contacto el evento `advisor_forbidden` con motivo
`case:<case_id> advisor:<advisor_id> code:forbidden` y la fecha del reloj inyectado.
*(Reescrito: ya no aplica a R26; decidido por el humano (2026-10-31), decisión 1.)*

## R30
SI el orquestador responde `403` por R25 y el caso no está vinculado a ningún contacto ENTONCES
el sistema (orchestrator) DEBE escribir en el log una línea `advisor_forbidden` con el `case_id`
y el `advisor_id`, sin guardar ningún evento. *Decidido por el humano (2026-10-31), decisión 3:
D9. (Reescrito: ya no aplica a R26.)*

## R31
CUANDO el orquestador deniega una respuesta (R25-R27) o falla cerrado (R28), el sistema
(orchestrator) NO DEBE escribir en el log el `text` de la respuesta del asesor.

### Cliente HTTP de handover

## R32
El sistema (orchestrator) DEBE pedir la autorización con un `POST` a
`{HANDOVER_URL}/cases/{case_id codificado}/authorize` que lleve `X-Service-Token`, un cuerpo
`CaseAuthorizeRequest` y el tiempo máximo `HTTP_TIMEOUT_SECONDS`.

## R33
CUANDO handover responde `403`, `404` o `409` con un `ErrorResponse` cuyo `error` es
respectivamente `forbidden`, `not_found` o `case_closed`, el cliente HTTP de handover del
orquestador DEBE lanzar una denegación interna con ese código.

## R34
SI la llamada a `POST /cases/{id}/authorize` falla por red o tiempo, o responde algo distinto
de R33 y de un `200` válido con el mismo `case_id`, ENTONCES el cliente HTTP de handover del
orquestador DEBE lanzar `ServiceUnavailable`.

### Carrera autorizar → enviar → asignar

## R35
SI `POST /cases/{id}/assign` falla después de un envío correcto, también con `403` porque otro
asesor ganó la asignación entre la autorización y la asignación (R38), ENTONCES el sistema
(orchestrator) DEBE registrar el evento `assign_failed` y responder `200` con `{"sent": true}`,
como R34 de la #7. *Decidido por el humano (2026-10-31), decisión 2: se acepta que en esa carrera
la respuesta del segundo asesor ya haya llegado al cliente.*

---

## Transversal

## R36
CUANDO se ejecuta la batería completa de tests tras el cambio, el sistema DEBE pasar todos los
tests que existían antes de la feature sin eliminar ninguno ni debilitar sus aserciones; los
únicos cambios en tests existentes son los listados en `design.md` §6 (incluidos los de
`services/handover/tests/test_timeout_races.py` de la #12).

---

## Servicio handover — asignación y cierre condicionales (decidido por el humano, 2026-10-31, decisión 2)

## R37
CUANDO handover asigna un caso por `POST /cases/{id}/assign`, el sistema (handover) DEBE hacerlo
con una escritura condicional que solo cambie `status` a `assigned`, `advisor_id` y
`assigned_at`, y solo si en el momento de escribir el caso sigue en `open` o `timed_out`.

## R38
SI la escritura condicional de asignación no cambia el caso porque otro asesor lo asignó entre la
lectura y la escritura ENTONCES el sistema (handover) DEBE responder `403` con
`{"error": "forbidden", ...}`, sin modificar el caso, y guardar el registro de denegación con
acción `assign` (R19).

## R39
SI la escritura condicional de asignación no cambia el caso porque se cerró entre la lectura y la
escritura ENTONCES el sistema (handover) DEBE responder `409` con `{"error": "case_closed", ...}`
sin modificar el caso.

## R40
SI la escritura condicional de asignación no cambia el caso porque el mismo asesor de la petición
lo asignó entre la lectura y la escritura ENTONCES el sistema (handover) DEBE responder `200` con
`{"status": "assigned", "case_id": <id>}` sin cambiar el asesor ni la fecha de asignación.

## R41
CUANDO handover cierra por `POST /cases/{id}/close` un caso que leyó sin asignar o asignado al
mismo `advisor_id` de la petición, el sistema (handover) DEBE hacerlo con una escritura
condicional que solo cambie `status` a `closed`, `closed_by` y `closed_at`, y solo si en el
momento de escribir el caso sigue en `open` o `timed_out` o sigue `assigned` a ese mismo
`advisor_id`, conservando `advisor_id`, `assigned_at` y `last_messages`. *(Reescrito: decidido
por el humano (2026-10-31), decisión 2; antes «solo si no está `closed`».)*

## R42
SI la escritura condicional de cierre no cambia el caso porque se cerró entre la lectura y la
escritura ENTONCES el sistema (handover) DEBE responder `200` con
`{"status": "closed", "case_id": <id>}` sin cambiar la fecha ni el asesor del cierre que ganó.

## R43
El sistema (handover) DEBE ofrecer las escrituras condicionales de R37, R41 y R54 como métodos del
`CaseRepository` con versión falsa en memoria (que comprueba y escribe sin ceder el control) y
versión PostgreSQL de una sola sentencia `UPDATE ... RETURNING` con SQL siempre parametrizado
(`%s`), que devuelvan si la fila cambió.

## Servicio handover — conexión compartida (decidido por el humano, 2026-10-31, decisión 5)

## R44
El sistema (handover) DEBE ejecutar cada operación de `PostgresCaseRepository` sobre la conexión
(sentencia, lectura de filas y `commit` o `rollback`) en exclusión mutua mediante un
`threading.Lock` propio de la instancia, de modo que dos hilos nunca usen la conexión a la vez.

## R45
CUANDO varios hilos hacen a la vez el primer uso de un `PostgresCaseRepository`, el sistema
(handover) DEBE abrir una sola conexión y crear el esquema una sola vez.

## Servicio handover — casos huérfanos (decidido por el humano, 2026-10-31, decisión 7: opción C + procedimiento A)

## R46
CUANDO handover recibe `POST /cases/{id}/authorize` con `action` = `close` de un asesor
registrado sobre un caso huérfano, el sistema (handover) DEBE responder `200` con
`{"allowed": true, "case_id": <id>}`.

## R47
CUANDO handover recibe `POST /cases/{id}/close` de un asesor registrado sobre un caso huérfano,
el sistema (handover) DEBE marcarlo `closed` con ese `advisor_id` como `closed_by` y la fecha del
reloj inyectado, conservando el `advisor_id` y el `assigned_at` del asesor retirado, y responder
`200` con `{"status": "closed", "case_id": <id>}`.

## R48
SI handover recibe `POST /cases/{id}/authorize` con `action` = `reply`, o `POST /cases/{id}/assign`,
de un asesor registrado sobre un caso huérfano ENTONCES el sistema (handover) DEBE responder
`403` con `{"error": "forbidden", ...}` sin modificar el caso.

## R49
CUANDO arranca la aplicación de handover (evento de arranque del servidor), el sistema
(handover) DEBE registrar en el log, a nivel `INFO`, `orphan_cases count=<n>` con el número de
casos huérfanos, sin ningún id de caso ni de asesor. *Decidido por el humano (2026-10-31),
decisión 4: D12 (en el `lifespan`).*

## R50
SI al arrancar la aplicación de handover hay al menos un caso huérfano ENTONCES el sistema
(handover) DEBE registrar además en el log, a nivel `WARNING`, `orphan_cases_present count=<n>`,
sin ningún id de caso ni de asesor.

## R51
SI el recuento de casos huérfanos al arrancar falla ENTONCES el sistema (handover) DEBE
registrar en el log, a nivel `WARNING`, `orphan_cases_check_failed` sin ids ni texto de la
excepción, y terminar de arrancar. *Decidido por el humano (2026-10-31), decisión 4: D13.*

## R52
CUANDO se importa `handover.main` o se llama a `create_app`, el sistema (handover) NO DEBE
contar casos huérfanos ni abrir la conexión a PostgreSQL.

## Servicio orchestrator — caso cerrado (decidido por el humano, 2026-10-31, decisión 1)

## R53
CUANDO el orquestador responde `409` por R26, el sistema (orchestrator) NO DEBE registrar el
evento `advisor_forbidden` ni escribir en el log una línea `advisor_forbidden`.

## Servicio handover — el cierre no gana a una asignación ajena (decidido por el humano, 2026-10-31, decisión 2)

## R54
CUANDO handover cierra por `POST /cases/{id}/close` un caso huérfano, el sistema (handover) DEBE
hacerlo con una escritura condicional que solo cambie `status` a `closed`, `closed_by` y
`closed_at`, y solo si en el momento de escribir el caso sigue en `open` o `timed_out` o sigue
`assigned` al mismo `advisor_id` huérfano que leyó (también nulo), conservando `advisor_id`,
`assigned_at` y `last_messages`.

## R55
SI la escritura condicional de cierre (R41 o R54) no cambia el caso y al releerlo el caso no está
`closed` ENTONCES el sistema (handover) DEBE responder `403` con `{"error": "forbidden", ...}`,
sin modificar el caso, y guardar el registro de denegación con acción `close` (R19).

---

## Trazabilidad con el `acceptance` de la #14

| Acceptance (resumido) | Requirements |
|---|---|
| Handover implementa `authorize`; un `advisor_id` fuera de `ADVISOR_CHAT_IDS` recibe `403` | R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R46, R48 |
| `close` y `assign` aplican las mismas reglas y responden `403` sin modificar el caso | R11, R12, R13, R14, R15, R16, R17, R18, R37, R38, R39, R40, R41, R42, R43, R47, R48, R54, R55 |
| `reply` del orquestador autoriza ANTES de enviar; con `403` no envía ni guarda | R23, R24, R25, R26, R27, R32, R33 |
| Cada denegación registrada: `advisor_forbidden` en el orquestador y registro en handover | R19, R20, R21, R22, R29, R30, R38, R53, R55 |
| Decidido: solo son asesores los de `ADVISOR_CHAT_IDS` | R1, R4, R11, R14 |
| Decidido: sin asignar responde cualquiera y la 1.ª respuesta asigna; `assigned` solo el asignado; sin reasignar ni supervisor | R2, R3, R7, R12, R13, R24, R35, R37, R38, R40, R48 |
| Decidido: sin asignar lo cierra cualquiera; `assigned` solo el asignado, salvo un caso huérfano | R15, R16, R17, R18, R41, R42, R46, R47, R54, R55 |
| Decidido: handover no disponible → falla cerrado, `502 upstream_error`, sin enviar | R28, R34 |
| Limitación de identidad documentada | `design.md` §7 (no es comportamiento verificable; ver nota) |
| Tests de la #7 con asesores no registrados se ajustan sin debilitar aserciones | R36 (`design.md` §6) |
| Tests, incluida la prueba de seguridad obligatoria | Todos; pruebas de seguridad en `tasks.md` T32 (handover) y T51 (orchestrator) |
| Decidido por el humano (2026-10-31), 1 (C5): `reply` sobre `closed` → `409`, sin `advisor_forbidden` | R26, R29, R30, R53 |
| Decidido por el humano (2026-10-31), 2: asignación y cierre condicionales; el cierre no gana a una asignación ajena | R35, R37, R38, R39, R40, R41, R42, R43, R54, R55 |
| Decidido por el humano (2026-10-31), 3: D7, D8, D9 | R19, R20, R22, R30, R38, R55 |
| Decidido por el humano (2026-10-31), 4: D12, D13 | R49, R51, R52 |
| Decidido por el humano (2026-10-31), 5: candado en `PostgresCaseRepository` | R44, R45 |
| Decidido por el humano (2026-10-31), 6: candado del orquestador en la #18 | ninguno (fuera de esta feature; `design.md` §3.5) |
| Decidido por el humano (2026-10-31), 7 (#17): casos huérfanos, opción C + procedimiento A, incluido `advisor_id` nulo | R46, R47, R48, R49, R50, R51, R52, R54 |

Nota: la limitación de identidad describe lo que el sistema **no** garantiza; no admite un test
que la «cumpla». Se documenta en `design.md` §7 y ya figura en S12 de `CONTRATOS.md` (#13).
