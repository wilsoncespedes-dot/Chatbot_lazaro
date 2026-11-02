# Requirements — traspaso_asesor

Feature #7. Servicios: `handover` (casos, avisos, vencimiento, cierre), `orchestrator`
(aviso al cliente sin asesores, respuesta del asesor). Esta feature NO modifica `contracts/`:
depende de una feature previa de contrato (`POST /cases/{id}/assign`, ver design.md
«Precondición de contrato»). Estados de un caso: `open` (sin asignar),
`assigned`, `timed_out`, `closed`.

## Servicio handover

### POST /handover — casos

## R1
CUANDO handover recibe `POST /handover` y el contacto no tiene un caso en estado `open` o
`assigned`, el sistema DEBE crear un caso en estado `open` con el `case_id` de la petición,
guardando `contact_id`, `chat_id`, `reason`, `last_messages` y la fecha de creación.

## R2
CUANDO handover recibe `POST /handover` y el contacto ya tiene un caso en estado `open` o
`assigned`, el sistema DEBE reutilizar ese caso, actualizar sus `last_messages` y responder
con el `case_id` del caso reutilizado.

### POST /handover — avisos

## R3
CUANDO handover procesa `POST /handover` y hay asesores configurados, el sistema DEBE enviar
un aviso a cada `chat_id` de `ADVISOR_CHAT_IDS` mediante `POST /send` del gateway.

## R4
El aviso a un asesor DEBE ser texto plano que contenga el `case_id`, el motivo y los
`last_messages` (con `role`).

## R41
El aviso a un asesor NO DEBE superar 4096 caracteres.

## R5
CUANDO un aviso a un asesor se envía con éxito, el sistema DEBE registrar una notificación con
`case_id`, `advisor_id` (el chat_id en decimal, S6), `reason`, fecha y `delivered = true`.

## R6
SI el envío del aviso a un asesor falla ENTONCES el sistema DEBE registrar la notificación con
`delivered = false` y continuar con los demás asesores.

## R7
CUANDO al menos un aviso se entregó, el sistema DEBE responder `200` con
`{"status": "notified", "case_id": <caso efectivo>}`.

## R8
SI `ADVISOR_CHAT_IDS` no contiene ningún asesor ENTONCES el sistema DEBE responder `200` con
`{"status": "no_advisors", "case_id": <caso efectivo>}` sin llamar a `POST /send`.

## R9
SI todos los avisos a los asesores fallan ENTONCES el sistema DEBE responder `200` con
`{"status": "no_advisors", "case_id": <caso efectivo>}`.

## R10
CUANDO la respuesta es `no_advisors` y el caso efectivo está en estado `open`, el sistema DEBE
marcarlo `timed_out` sin enviar `HANDOVER_TIMEOUT_REPLY` (el cliente ya es informado por el
orquestador, R30). Justificación: el acceptance 3 hace que el orquestador avise al cliente
con `NO_ADVISORS_REPLY`; si el caso siguiera `open`, `check-timeouts` enviaría un segundo aviso
de espera. Supuesto confirmable (ver design.md).

### POST /cases/{id}/assign (ruta definida por la feature previa de contrato)

## R11
CUANDO handover recibe `POST /cases/{id}/assign` de un caso en estado `open` o `timed_out`
(`timed_out` → `assigned` es un supuesto confirmable, ver design.md; el acceptance 4 pide marcar
`assigned` sin excluir ese estado),
el sistema DEBE marcarlo `assigned` al `advisor_id` recibido, guardar la fecha de asignación y
responder `200` con `{"status": "assigned", "case_id": <id>}`.

## R12
CUANDO handover recibe `POST /cases/{id}/assign` de un caso ya `assigned`, el sistema DEBE
responder `200` igual que en R11 sin cambiar el asesor asignado.

## R13
SI handover recibe `POST /cases/{id}/assign` de un caso `closed` ENTONCES el sistema DEBE
responder `409` con `{"error": "case_closed", ...}` sin modificar el caso.

## R14
SI handover recibe `POST /cases/{id}/assign` o `POST /cases/{id}/close` de un caso que no
existe ENTONCES el sistema DEBE responder `404` con `{"error": "not_found", ...}`.

### POST /cases/{id}/close

## R15
CUANDO handover recibe `POST /cases/{id}/close` de un caso existente no cerrado, el sistema
DEBE marcarlo `closed`, guardar `advisor_id` y la fecha de cierre, y responder `200` con
`{"status": "closed", "case_id": <id>}`.

## R16
CUANDO handover recibe `POST /cases/{id}/close` de un caso ya `closed`, el sistema DEBE
responder `200` con `{"status": "closed", "case_id": <id>}` sin cambiar la fecha ni el asesor
del cierre original (S8).

### POST /cases/check-timeouts

## R17
CUANDO handover recibe `POST /cases/check-timeouts`, el sistema DEBE, por cada caso en estado
`open` cuya antigüedad sea mayor o igual que `HANDOVER_TIMEOUT_SECONDS`, enviar
`HANDOVER_TIMEOUT_REPLY` al `chat_id` del caso mediante `POST /send` y marcar el caso
`timed_out`.

## R18
MIENTRAS un caso esté `assigned`, `closed`, `timed_out` o `open` con antigüedad menor que
`HANDOVER_TIMEOUT_SECONDS`, el sistema NO DEBE enviarle `HANDOVER_TIMEOUT_REPLY` ni cambiar su
estado en `POST /cases/check-timeouts`.

## R19
SI el envío de `HANDOVER_TIMEOUT_REPLY` al cliente falla ENTONCES el sistema DEBE dejar el caso
en `open` (se reintenta en la siguiente llamada) y no incluirlo en `timed_out_cases`.

## R20
SI el envío de `HANDOVER_TIMEOUT_REPLY` falla para un caso ENTONCES el sistema DEBE seguir
procesando el resto de casos vencidos de la misma llamada.

## R21
CUANDO `POST /cases/check-timeouts` termina, el sistema DEBE responder `200` con
`{"timed_out_cases": [<ids marcados en esta llamada>]}`, lista vacía si ninguno venció.

## R22
El sistema (handover) DEBE obtener la hora actual únicamente del reloj inyectado en sus
adaptadores, de modo que un reloj falso determine la antigüedad de los casos.

### Configuración, seguridad y persistencia (handover)

## R23
El sistema (handover) DEBE leer de variables de entorno `ADVISOR_CHAT_IDS` (enteros separados
por comas; las entradas vacías o no numéricas se descartan), `HANDOVER_TIMEOUT_SECONDS`
(entero ≥ 1, por defecto 300) y `HANDOVER_TIMEOUT_REPLY` (texto, con valor por defecto).

> **Nota (2026-10-31): R23 modificada por la #10 `validacion_config_asesores`.** Las entradas
> vacías se siguen descartando, pero una entrada no numérica o un id repetido en
> `ADVISOR_CHAT_IDS` ya no se descartan: `Settings()` lanza un error de validación y handover no
> arranca. Ver `specs/validacion_config_asesores/` (decisión del humano del 2026-10-31).

## R24
SI una petición a `POST /handover`, `POST /cases/{id}/assign`, `POST /cases/{id}/close` o
`POST /cases/check-timeouts` llega sin `X-Service-Token` válido ENTONCES el sistema (handover)
DEBE responder `401` con `{"error": "unauthorized", ...}` sin crear ni modificar casos ni
enviar avisos.

## R25
SI el cuerpo de una de esas rutas no valida contra su modelo ENTONCES el sistema (handover)
DEBE responder `422` con `{"error": "validation_error", ...}`.

## R26
El sistema (handover) DEBE guardar casos y notificaciones a través de una interfaz
`CaseRepository` con versión falsa en memoria y versión PostgreSQL cuyo SQL use siempre
parámetros (`%s`) y nunca texto interpolado.

## Servicio orchestrator

## R27
El sistema (orchestrator) DEBE leer de variables de entorno `NO_ADVISORS_REPLY` (texto, con
valor por defecto no vacío).

## R28
CUANDO `POST /handover` de handover responde con cualquier `status`, el sistema (orchestrator)
DEBE guardar el vínculo entre el `case_id` devuelto (el efectivo) y el `contact_id`.

## R29
CUANDO `POST /handover` de handover responde `no_advisors`, el sistema (orchestrator) DEBE
registrar el evento `handover_failed` con motivo `no_advisors`.

## R30
CUANDO `POST /handover` de handover responde `no_advisors`, el sistema (orchestrator) DEBE
enviar `NO_ADVISORS_REPLY` al chat del cliente con `POST /send` y guardarlo en su historial
con rol `bot` (prueba de seguridad obligatoria: el cliente nunca queda sin respuesta).

### POST /cases/{id}/reply

## R31
CUANDO el orquestador recibe `POST /cases/{id}/reply` de un caso que conoce, el sistema DEBE
enviar `text` al `chat_id` del contacto del caso con `POST /send` y responder `200` con
`{"sent": true}`.

## R32
CUANDO el envío de la respuesta del asesor tiene éxito, el sistema (orchestrator) DEBE guardar
el mensaje en el historial del contacto con rol `advisor` y registrar el evento
`advisor_reply`.

## R33
CUANDO el envío de la respuesta del asesor tiene éxito, el sistema (orchestrator) DEBE llamar a
`POST /cases/{id}/assign` de handover con el `advisor_id` recibido.

## R34
SI la llamada a `POST /cases/{id}/assign` falla o responde error ENTONCES el sistema
(orchestrator) DEBE registrar el evento `assign_failed` y responder igualmente `200` con
`{"sent": true}`, porque el cliente ya recibió el mensaje.

## R35
SI el orquestador recibe `POST /cases/{id}/reply` de un caso que no conoce ENTONCES el sistema
DEBE responder `404` con `{"error": "not_found", ...}` sin llamar a `POST /send`.

## R36
SI `POST /send` falla al reenviar la respuesta del asesor ENTONCES el sistema (orchestrator)
DEBE responder `502` con `{"error": "upstream_error", ...}` sin guardar el mensaje ni llamar
a `POST /cases/{id}/assign`.

## R37
SI `POST /cases/{id}/reply` llega sin `X-Service-Token` válido ENTONCES el sistema
(orchestrator) DEBE responder `401` con `{"error": "unauthorized", ...}` sin enviar nada.

## R38
SI el cuerpo de `POST /cases/{id}/reply` no valida contra `CaseReplyRequest` ENTONCES el
sistema (orchestrator) DEBE responder `422` con `{"error": "validation_error", ...}`.

## Contratos

## R39
(Retirado de esta feature: la documentación de `POST /cases/{id}/assign` en `CONTRATOS.md` y los
modelos `CaseAssignRequest`/`CaseAssignResponse` pasan a la feature previa de contrato, por el
principio 2 de `docs/architecture.md`. El número no se reutiliza.)

## R40
(Retirado: ejemplos y tests de contrato, misma razón que R39. El número no se reutiliza.)

## Fuera de alcance

Panel de asesores, reenvío al asesor de los mensajes posteriores del cliente mientras el caso
está `assigned`, autenticación de asesores, verificación de que `advisor_id` pertenezca a
`ADVISOR_CHAT_IDS`, worker o cron que llame a `check-timeouts`, y recibir las respuestas de
los asesores por Telegram.

## Trazabilidad con el `acceptance` de feature_list.json

| Criterio (orden) | Requirements |
|------------------|--------------|
| 1. `POST /handover` crea/reutiliza, avisa, `notified` | R1, R2, R3, R4, R41, R7 |
| 2. Aviso registrado (caso, asesor, motivo, fecha) | R5, R6 |
| 3. `no_advisors` y `NO_ADVISORS_REPLY` | R8, R9, R10, R27, R29, R30 |
| 4. `reply` en orquestador, historial, `assigned`, 404 | R11, R12, R13, R14, R28, R31-R38 |
| 5. Vencimiento con reloj inyectado | R17, R18, R19, R20, R21, R22 |
| 6. Cierre de caso registrado | R15, R16, R14 |
| 7. Supuesto 300 s y `ADVISOR_CHAT_IDS` | R23 |
| 8. Tests listados | cubiertos por las tasks de prueba (aviso a 3, sin asesores, fallo de un aviso, reply, 404, vencimiento, cierre) |
| Seguridad y contratos (añadidos por el diseño) | R24, R25, R26 (R39, R40 retirados a la feature de contrato) |
