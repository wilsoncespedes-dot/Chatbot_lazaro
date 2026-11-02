# Requirements — contrato_conversacion_caso (feature #15)

> Feature: «Contrato: mensajes del cliente hacia el asesor». Feature previa de
> contrato que desbloquea la #16 (`conversacion_cliente_asesor`). Añade la ruta
> `POST /cases/{id}/client-message` (la expone `handover`, la llama `orchestrator`),
> el supuesto S13 y la mención de `orchestrator` como llamador de
> `POST /cases/{id}/close`.
>
> Fuentes: acceptance de la #15 y de la #16 en `feature_list.json` (criterios
> «Decidido por el humano (2026-10-31)») y `progress/propuesta_etapa2.md` §6. No se
> añade ninguna decisión de negocio fuera de esas fuentes.
>
> **Estado de partida.** Este spec se escribe sobre `contracts/` tal como quede
> tras la #13 (`contrato_autorizacion_asesores`), que se implementa ANTES: esa
> feature añade `POST /cases/{id}/authorize`, el código `403 forbidden` y el
> supuesto S12. Por eso el supuesto de esta feature es S13, que cita S12 como las
> reglas de autorización de los comandos de asesor (R38). Sin la #13 implementada
> no se empieza (T0 de `tasks.md`; ver `design.md` §1).
>
> Todo vive en `contracts/` (principio 2 de `docs/architecture.md`). Ningún
> servicio de `services/` se toca: implementar la ruta en handover y llamarla desde
> el orquestador es trabajo de la #16.
>
> Cambio **aditivo** salvo una única edición de texto en una sección ya publicada:
> la línea `- **Llama:**` de `### POST /cases/{id}/close` (R14). Además se amplía la
> docstring de módulo de `cases.py` (sin efecto en el comportamiento; R34).
>
> R37 y R39 fijan la identidad de los comandos (S6 ↔ S13) con la opción más
> conservadora (la más restrictiva), adoptada como supuesto en modo nocturno el
> 2026-11-01 porque el humano no la ha decidido: se compara con el `telegram_user_id`
> del remitente y un id de grupo no usa comandos. No bloquea la implementación; si
> el humano elige la alternativa (ids positivos), se sustituyen R39 y T34
> (`design.md` §7).
>
> Notación EARS estricta (`docs/specs.md`). «El sistema» es el paquete de contrato
> (`contracts/`: `CONTRATOS.md`, `lazaro_contracts`, `examples/`, `tests/`).
> Ids estables: no renumerar. Los nombres de test están en `tasks.md`.

---

## A. Documento `contracts/CONTRATOS.md` — ruta nueva

## R1
El sistema DEBE incluir en `contracts/CONTRATOS.md`, dentro de `## Rutas`, un
encabezado de nivel 3 con el texto exacto `### POST /cases/{id}/client-message`.

## R2
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE indicar el
servicio que la expone con la línea `- **Expone:** handover`.

## R3
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE indicar
quién la llama con una línea `- **Llama:** …` que contenga `orchestrator`.

## R4
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE nombrar en
la línea `- **Modelos:**` los modelos `CaseClientMessageRequest` (primero) y
`CaseClientMessageResponse` (segundo), entre comillas invertidas.

## R5
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE incluir la
subsección `#### Request` con una tabla de columnas
`Campo | Tipo | Obligatorio | Descripción` que contenga las filas de los campos
`text` y `at`.

## R6
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE incluir la
subsección `#### Respuesta` con el código de éxito `` `200 OK` `` y una tabla de
columnas `Campo | Tipo | Obligatorio | Descripción` que contenga las filas de los
campos `status` y `case_id`.

## R7
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE incluir la
subsección `#### Errores` con una tabla de columnas `HTTP | error | Cuándo` que
contenga las filas `401 unauthorized` y `422 validation_error`.

## R8
En la tabla `#### Errores` de `### POST /cases/{id}/client-message`, `CONTRATOS.md`
DEBE contener las filas `404 not_found` y `502 upstream_error`.

## R9
En la tabla `#### Errores` de `### POST /cases/{id}/client-message`, `CONTRATOS.md`
DEBE contener la fila `500 internal_error`.

## R10
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE indicar que
`{id}` es el `case_id` (identificador, 1–64 caracteres), con la misma frase que usan
`### POST /cases/{id}/reply` y `### POST /cases/{id}/close`.

## R11
En la sección `### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE describir
que un caso `assigned` responde `200` con `status` = `forwarded` tras enviar el texto
al asesor asignado, y que un caso que existe y no está `assigned` responde `200` con
`status` = `not_assigned` sin enviar nada, citando `S13`.

## R12
En la fila `502 upstream_error` de la tabla `#### Errores` de
`### POST /cases/{id}/client-message`, `CONTRATOS.md` DEBE indicar que falló el envío
al asesor.

## R13
Todo código de error de la tabla `#### Errores` de
`### POST /cases/{id}/client-message` DEBE figurar ya en la tabla de errores de
`## Reglas comunes` (la ruta no introduce códigos nuevos; esa tabla no se modifica,
ver `design.md` §1).

---

## B. Documento `contracts/CONTRATOS.md` — sección existente y supuesto

## R14
En la sección `### POST /cases/{id}/close`, la línea `- **Llama:**` de
`CONTRATOS.md` DEBE contener `orchestrator`, conservando el texto previo
`asesor (herramienta interna con token; panel en el futuro)`.

## R15
En la tabla de `## Supuestos a confirmar`, `CONTRATOS.md` DEBE incluir una fila `S13`
que recoja que solo se reenvían al asesor, con `POST /cases/{id}/client-message`,
los mensajes de un cliente cuyo caso está `assigned`, y que con un caso `open`,
con `not_assigned` o con `404` sigue el flujo actual.

## R16
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que, si el reenvío al
asesor falla (`502`), el cliente recibe un texto fijo y NO se vuelve al RAG.

## R17
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que los comandos de asesor
`/responder <case_id> <texto>` y `/cerrar <case_id>` llegan por `POST /messages` y
que ese contrato no cambia.

## R18
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que, en esos comandos, el
`advisor_id` es el `telegram_user_id` del update validado con
`TELEGRAM_WEBHOOK_SECRET`, nunca un id escrito en el texto del mensaje.

## R36
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que un mensaje de un asesor
por `POST /messages` que no es `/responder` ni `/cerrar` sigue el flujo actual, como
el de cualquier cliente.

## R37
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que, en los comandos de
asesor, la pertenencia a `ADVISOR_CHAT_IDS` se comprueba con el `telegram_user_id`
del remitente y no con el `chat_id` del update. (Supuesto conservador adoptado en
modo nocturno; `design.md` §7.)

## R38
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que los comandos de asesor
se autorizan con las reglas de `S12`.

## R39
La fila `S13` de `## Supuestos a confirmar` DEBE recoger que un id de grupo
(negativo) de `ADVISOR_CHAT_IDS` no puede usar los comandos de asesor. (Supuesto
conservador adoptado en modo nocturno; `design.md` §7.)

---

## C. Modelos en `contracts/lazaro_contracts/cases.py`

## R19
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` la clase
`CaseClientMessageRequest`, subclase de `ContractModel`, con exactamente los campos
obligatorios `text: MessageText` y `at: AwareDatetime`.

## R20
SI un `CaseClientMessageRequest` se valida sin el campo `text` ENTONCES el sistema
DEBE lanzar `ValidationError`.

## R21
SI un `CaseClientMessageRequest` se valida sin el campo `at` ENTONCES el sistema
DEBE lanzar `ValidationError`.

## R22
SI el `at` de un `CaseClientMessageRequest` es una fecha sin zona horaria ENTONCES
el sistema DEBE lanzar `ValidationError`.

## R23
SI el `text` de un `CaseClientMessageRequest` es vacío o tiene más de
`MAX_TEXT_LENGTH` caracteres ENTONCES el sistema DEBE lanzar `ValidationError`.

## R24
El sistema DEBE definir en `contracts/lazaro_contracts/cases.py` la clase
`CaseClientMessageResponse`, subclase de `ContractModel`, con exactamente los campos
obligatorios `status: Literal["forwarded", "not_assigned"]` y `case_id: Identifier`.

## R25
SI un `CaseClientMessageResponse` se valida con un `status` distinto de `forwarded`
y de `not_assigned` ENTONCES el sistema DEBE lanzar `ValidationError`.

## R26
SI el `case_id` de un `CaseClientMessageResponse` es vacío o tiene más de
`MAX_IDENTIFIER_LENGTH` caracteres ENTONCES el sistema DEBE lanzar
`ValidationError`.

## R27
SI un `CaseClientMessageRequest` o un `CaseClientMessageResponse` se valida con un
campo no declarado ENTONCES el sistema DEBE lanzar `ValidationError`.

## R28
El paquete `lazaro_contracts` DEBE exportar `CaseClientMessageRequest` y
`CaseClientMessageResponse` en `lazaro_contracts/__init__.py` y listarlos en
`__all__`.

---

## D. Ejemplos en `contracts/examples/`

## R29
El sistema DEBE incluir `contracts/examples/case_client_message_request.json`,
válido contra `CaseClientMessageRequest`.

## R30
El sistema DEBE incluir `contracts/examples/case_client_message_response.json`,
válido contra `CaseClientMessageResponse` y con `status` = `forwarded`.

## R31
El sistema DEBE incluir
`contracts/examples/case_client_message_response_not_assigned.json`, válido contra
`CaseClientMessageResponse` y con `status` = `not_assigned`.

## R32
El mapa `EXAMPLES` y la lista `MODEL_NAMES` de `contracts/tests/test_examples.py`
DEBEN incluir los tres ejemplos nuevos y los dos modelos nuevos, de modo que los
tests de cobertura de ejemplos los exijan.

---

## E. Carácter aditivo

## R33
El sistema NO DEBE modificar la sección `### POST /messages` de `CONTRATOS.md` ni
los modelos `MessageRequest` y `MessageResponse`.

## R34
El sistema NO DEBE modificar el comportamiento ni eliminar ningún modelo, constante,
ejemplo JSON, sección de ruta, fila de tabla o supuesto (S1–S12) existente de
`contracts/`, salvo la línea `- **Llama:**` de `### POST /cases/{id}/close` (R14) y
la docstring de módulo de `contracts/lazaro_contracts/cases.py`, que solo se amplía
con la ruta `/cases/{id}/client-message`.

## R35
CUANDO se ejecuta la batería completa de tests del repositorio tras el cambio, el
sistema DEBE pasar todos los tests que existían antes de la feature, sin que se haya
eliminado ninguno ni debilitado ninguna de sus aserciones.
