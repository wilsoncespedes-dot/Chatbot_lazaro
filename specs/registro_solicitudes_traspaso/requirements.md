# Requirements — registro_solicitudes_traspaso

Feature #11. Servicio: **solo `handover`**. No modifica `contracts/` ni el orquestador, y no
cambia la respuesta de `POST /handover` ni los avisos a asesores. Añade la tabla
`handover_requests` (un registro por solicitud) y dos métodos nuevos al repositorio de casos.

Fuente: `acceptance` de la #11 en `feature_list.json` y `progress/propuesta_etapa2.md` §6
(decisiones del humano del 2026-10-31). Fuera de alcance: rutas para consultar los registros
(panel de asesores) y política de retención y borrado.

Vocabulario usado abajo:

- **Solicitud válida:** `POST /handover` con `X-Service-Token` correcto y cuerpo que valida
  como `HandoverRequest`.
- **Registro:** una fila de `handover_requests` (modelo `HandoverRequestRecord`, ver design.md).
- **Caso efectivo:** el caso que `open_case` crea o reutiliza (el `case_id` que devuelve la
  respuesta).
- **Error interno:** cualquier excepción no controlada mientras handover procesa la solicitud
  (la que hoy acaba en `500 internal_error`).

## Creación del registro

## R1
CUANDO handover recibe una solicitud válida, el sistema DEBE crear un registro, antes de
buscar o crear el caso, con: id propio, `requested_case_id` = `case_id` de la petición,
`case_id` efectivo vacío (`None`), `contact_id`, `reason`, `received_at` tomado del reloj
inyectado, resultado `received`, `advisors_configured` = número de asesores de
`ADVISOR_CHAT_IDS` y `notices_delivered` = 0 (`messages_count` lo fija R19).

## R2
El registro NO DEBE contener el texto de `last_messages` ni ningún otro texto de mensajes.

## R19
CUANDO handover crea un registro, el sistema DEBE guardar en `messages_count` el número de
elementos de `last_messages` de la petición.

(R19 sale de partir el R2 original —regla «un solo `DEBE`» de `docs/specs.md`— y se numera
al final para mantener estables los ids R3-R18.)

## Resultado del registro

## R3
CUANDO handover responde `notified` a una solicitud, el sistema DEBE completar su registro
con resultado `notified`, el `case_id` efectivo y `notices_delivered` igual al número de
avisos enviados con éxito.

## R4
CUANDO handover responde `no_advisors` a una solicitud porque no hay asesores configurados,
el sistema DEBE completar su registro con resultado `no_advisors`, el `case_id` efectivo,
`advisors_configured` = 0 y `notices_delivered` = 0.

## R5
CUANDO handover responde `no_advisors` a una solicitud porque todos los avisos fallaron, el
sistema DEBE completar su registro con resultado `no_advisors`, el `case_id` efectivo,
`advisors_configured` igual al número de asesores configurados y `notices_delivered` = 0.

## Reutilización de un caso

## R6
CUANDO handover reutiliza un caso abierto o asignado del contacto, el sistema DEBE crear un
registro nuevo (con id distinto de los anteriores) cuyo `reason` y `requested_case_id` son
los de la petición nueva y cuyo `case_id` efectivo es el del caso reutilizado.

## R7
CUANDO handover reutiliza un caso con una petición de motivo distinto, el sistema NO DEBE
cambiar `Case.reason`, que conserva el motivo original (aceptado por el humano en la #7).

## Errores

## R8
SI el procesamiento de una solicitud termina con un error interno ENTONCES el sistema DEBE
completar su registro con resultado `error`, el `case_id` efectivo si ya se conocía (`None`
si no) y `notices_delivered` igual a los avisos enviados con éxito antes del error.

## R9
SI el procesamiento de una solicitud termina con un error interno ENTONCES el sistema DEBE
propagar la excepción original, de modo que `POST /handover` responda `500` con
`{"error": "internal_error", ...}` como antes de esta feature.

## R10
SI falla la creación del registro ENTONCES el sistema DEBE procesar la solicitud igualmente y
devolver la misma respuesta que devolvería sin registro.

## R11
SI falla la actualización del registro después de un resultado `notified` o `no_advisors`
ENTONCES el sistema DEBE devolver igualmente esa respuesta.

## R12
SI falla la actualización del registro a `error` ENTONCES el sistema DEBE propagar la
excepción original del procesamiento, no la de la actualización.

## R13
SI `POST /handover` se rechaza con `401` (token) o `422` (cuerpo no válido) ENTONCES el
sistema NO DEBE crear ningún registro.

## Sin cambios en lo existente

## R14
El sistema NO DEBE cambiar el código HTTP ni el cuerpo de la respuesta de `POST /handover`
respecto a la feature #7.

## R15
El sistema NO DEBE cambiar los avisos a asesores (destinatarios, texto y orden) ni las filas
de `handover_notifications` respecto a la feature #7.

## Persistencia y logs

## R16
CUANDO `PostgresCaseRepository` abre su conexión por primera vez, el sistema DEBE crear la
tabla `handover_requests` con `CREATE TABLE IF NOT EXISTS`, una sola vez, junto a las tablas
existentes de handover.

## R17
`PostgresCaseRepository` DEBE pasar todos los valores de los registros como parámetros `%s`,
sin interpolarlos en el texto SQL.

## R18
Los logs que handover emite al crear, completar o no poder guardar un registro NO DEBEN
contener texto de `last_messages`.

## R20
SI falla la creación o la actualización de un registro ENTONCES el sistema DEBE emitir un log
de nivel `ERROR` con el código `handover_request_not_recorded` (creación) o
`handover_request_update_failed` (actualización).

## R21
SI el procesamiento de una solicitud termina con un error interno ENTONCES el sistema DEBE
emitir un log de nivel `ERROR` con el código `handover_request_failed`, el id del registro y
el `case_id` efectivo (o `None`).
