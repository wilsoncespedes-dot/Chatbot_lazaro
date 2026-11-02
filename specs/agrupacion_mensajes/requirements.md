# Requirements — agrupacion_mensajes (#30)

Servicio único: `telegram_gateway`. No cambia ninguna ruta ni contrato: el grupo se entrega al
`orchestrator` con el `POST /messages` existente (`lazaro_contracts.MessageRequest`).
Dependencias: #3 `telegram_gateway`, #4 `orquestador_basico`, #7 `traspaso_asesor`.

Glosario: **buffer** = mensajes de texto pendientes de un `chat_id` en Redis; **grupo** = buffer
reclamado para enviarse; **mensaje inmediato** = texto que empieza por `/` tras `strip()` o
que, normalizado (minúsculas, espacios colapsados), es igual a `PRIVACY_ACCEPT_PHRASE` no vacía.

## Configuración

## R1
El gateway DEBE leer de variables de entorno `MESSAGE_GROUPING_ENABLED` (por defecto `true`),
`MESSAGE_GROUPING_WINDOW_SECONDS` (`2.0`), `MESSAGE_GROUPING_MAX_WAIT_SECONDS` (`8.0`),
`MESSAGE_GROUPING_MAX_MESSAGES` (`10`), `MESSAGE_GROUPING_BUFFER_TTL_SECONDS` (`300`),
`MESSAGE_GROUPING_LEASE_SECONDS` (`30`), `MESSAGE_GROUPING_MAX_ATTEMPTS` (`3`),
`MESSAGE_GROUPING_POLL_SECONDS` (`0.5`) y `PRIVACY_ACCEPT_PHRASE` (por defecto vacía).

## R2
SI `WINDOW_SECONDS <= 0`, `MAX_WAIT_SECONDS < WINDOW_SECONDS`, `MAX_MESSAGES < 1`,
`MAX_ATTEMPTS < 1`, `POLL_SECONDS <= 0`, `LEASE_SECONDS <= 0` o
`BUFFER_TTL_SECONDS <= MAX_WAIT_SECONDS + LEASE_SECONDS` ENTONCES `Settings` DEBE fallar al
construirse con un error de validación.

## R3
`.env.example` DEBE listar todas las variables `MESSAGE_GROUPING_*` de R1 con sus valores por
defecto e indicar que `PRIVACY_ACCEPT_PHRASE` también la lee el gateway.

## Agrupación

## R4
CUANDO la agrupación está activa y llega un update nuevo con texto que no es mensaje inmediato,
el gateway DEBE añadirlo al buffer de su `chat_id` y responder `200` a Telegram sin llamar al
orquestador durante esa petición.

## R5
CUANDO se añade un mensaje a un buffer, el gateway DEBE fijar su vencimiento en
`min(received_at_último + WINDOW_SECONDS, received_at_primero + MAX_WAIT_SECONDS)`.

## R6
CUANDO el worker encuentra un buffer vencido, el gateway DEBE enviar al orquestador un único
`MessageRequest` cuyo `text` es la unión con `"\n"` de los textos en orden ascendente de
`update_id`.

## R7
CUANDO se construye el `MessageRequest` de un grupo, el gateway DEBE usar el menor `update_id`
del grupo, el `telegram_user_id` y `chat_id` del grupo y el `received_at` del último mensaje.

## R8
El gateway NO DEBE incluir en un grupo mensajes de un `chat_id` distinto al del buffer.

## R9
SI un mensaje nuevo tiene un `telegram_user_id` distinto al del buffer pendiente de su chat, o
añadirlo superaría `MAX_MESSAGES` mensajes o `MAX_TEXT_LENGTH` (4096) caracteres del texto
unido, ENTONCES el gateway DEBE enviar primero el buffer pendiente y después iniciar un buffer
nuevo con ese mensaje.

## R10
SI un único mensaje no cabe en `MAX_TEXT_LENGTH` ENTONCES el gateway DEBE tratarlo como hoy
(fallo de validación registrado sin texto y `200`), sin dejarlo en el buffer.

## Deduplicación

## R11
CUANDO llega un update cuyo `update_id` ya está marcado por `DedupStore`, el gateway NO DEBE
añadirlo a ningún buffer.

## R12
SI un `update_id` ya presente en el buffer se intenta añadir otra vez (p. ej. Redis de
deduplicación caído) ENTONCES el buffer DEBE conservar una sola copia.

## Mensajes inmediatos, comandos y consentimiento

## R13
CUANDO llega un mensaje inmediato, el gateway DEBE enviar primero el buffer pendiente de ese
chat (si existe) y después el mensaje inmediato como `MessageRequest` individual con su propio
`update_id`, ambos dentro de la misma petición del webhook.

## R14
El gateway NO DEBE concatenar un mensaje inmediato con ningún otro texto.

## R15
CUANDO llega un update sin texto, el gateway DEBE mantener el comportamiento de #3 (enviar
`NON_TEXT_REPLY`) sin modificar el buffer del chat.

## R16
MIENTRAS `MESSAGE_GROUPING_ENABLED` es `false` o no hay adaptador de buffer, el gateway DEBE
reenviar cada update de texto individualmente como en #3 R4.

## R17
SI Redis falla al añadir al buffer o al reclamarlo desde el webhook ENTONCES el gateway DEBE
reenviar ese mensaje individualmente al orquestador y registrar el error con su `update_id`.

## Worker, concurrencia, fallos y reinicio

## R18
CUANDO dos workers o un worker y el webhook intentan reclamar el mismo buffer a la vez, el
gateway DEBE permitir que solo uno lo reclame y lo envíe.

## R19
MIENTRAS un grupo de un chat está reclamado y no confirmado, el gateway NO DEBE reclamar otro
buffer del mismo chat.

## R20
SI el envío de un grupo falla (`OrchestratorError`) ENTONCES el gateway DEBE liberarlo para
reintento con su contador de intentos incrementado, conservando los mismos mensajes.

## R21
SI un grupo alcanza `MAX_ATTEMPTS` intentos fallidos o falla la validación de `MessageRequest`
ENTONCES el gateway DEBE descartarlo y registrar un error con los `update_id` y el número de
mensajes.

## R22
CUANDO el worker arranca o vence la `LEASE_SECONDS` de un grupo reclamado no confirmado, el
gateway DEBE volver a reclamarlo y reenviarlo hasta `MAX_ATTEMPTS` veces en total.

## R23
El gateway DEBE crear y renovar cada clave de buffer y de grupo reclamado en Redis con caducidad
`BUFFER_TTL_SECONDS`.

## R24
SI una iteración del worker lanza una excepción ENTONCES el gateway DEBE registrarla y continuar
con la siguiente iteración.

## R25
CUANDO la app arranca con agrupación activa y adaptador de buffer, el gateway DEBE iniciar el
worker; CUANDO la app se detiene, DEBE pararlo.

## Privacidad y adaptadores

## R26
El gateway NO DEBE incluir texto de mensajes, `PRIVACY_ACCEPT_PHRASE` ni tokens en logs de
agrupación, reintento, descarte o fallo.

## R27
El gateway DEBE acceder al buffer únicamente mediante un `Protocol` `MessageBuffer` con versión
falsa `FakeMessageBuffer`, de modo que los tests no usen Redis real ni hilos reales salvo el
test de concurrencia.

## Cobertura del acceptance

| Criterio de `feature_list.json` | Requirements |
|---|---|
| Agrupa consecutivos del mismo usuario/chat en ventana configurable y con orden | R1, R2, R3, R4, R5, R6, R7, R9, R10 |
| Otro chat no se mezcla; cada `update_id` como máximo una vez | R8, R11, R12, R18, R19 |
| Recupera o expira buffers de forma acotada ante reinicios; fallos sin texto personal | R17, R20, R21, R22, R23, R24, R25, R26 |
| Comandos de asesores y estados de traspaso sin cambios | R13, R14, R15, R16 |
| Pruebas de ventana, orden, dedup, concurrencia, reinicio y errores | R27 + tests de `tasks.md` |
