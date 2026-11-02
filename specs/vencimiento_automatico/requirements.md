# Requirements — vencimiento_automatico

Feature #12. Toca `scripts/` (script nuevo `vencer_casos.py`), `docker-compose.yml`,
`.env.example`, el `Dockerfile` de handover y `services/handover` (escrituras condicionales).
NO cambia `contracts/` ni la forma de ninguna respuesta. NO despliega nada en Render
(decisión del humano 2026-10-31: queda pendiente cómo se ejecuta allí).

Vocabulario:
- **Llamada única**: el script ejecutado sin `--intervalo`.
- **Modo bucle**: el script ejecutado con `--intervalo`.
- **Reclamación de vencimiento**: marca con fecha que una ejecución de `check-timeouts` pone en un
  caso `open` antes de enviarle `HANDOVER_TIMEOUT_REPLY` (ver design.md). Es **vigente** mientras
  su antigüedad, medida con el reloj inyectado, sea menor que `HANDOVER_TIMEOUT_SECONDS`.

Las requirements R17-R22 de la feature #7 (`specs/traspaso_asesor/`) siguen vigentes; las de esta
feature precisan cómo se escriben los cambios de estado.

## Script `scripts/vencer_casos.py`

## R1
CUANDO el script se ejecuta sin opciones, el sistema DEBE enviar exactamente una petición
`POST {HANDOVER_URL}/cases/check-timeouts` con cuerpo `{}` y el encabezado `X-Service-Token`
igual a `SERVICE_TOKEN`.

## R2
CUANDO en llamada única handover responde `200`, el script DEBE terminar con código de salida 0.

## R3
SI en llamada única handover responde con un código HTTP distinto de `200` (incluido `401`)
ENTONCES el script DEBE terminar con un código de salida distinto de 0.

## R4
SI en llamada única la petición falla por un error de red o de tiempo de espera ENTONCES el
script DEBE terminar con un código de salida distinto de 0.

## R5
SI falta `HANDOVER_URL` o `SERVICE_TOKEN` (o está vacía) ENTONCES el script DEBE terminar con un
código de salida distinto de 0 sin enviar ninguna petición.

## R6
CUANDO el script se ejecuta con `--intervalo <segundos>`, el script DEBE repetir la llamada de R1
esperando `<segundos>` segundos después de cada llamada.

## R7
CUANDO el script se ejecuta con `--intervalo` sin valor, el script DEBE usar como intervalo
`CHECK_TIMEOUTS_INTERVAL_SECONDS`, o 60 segundos si esa variable no está definida.

## R8
SI en modo bucle el intervalo que se va a usar (el valor de `--intervalo` o, si la opción no
lleva valor, `CHECK_TIMEOUTS_INTERVAL_SECONDS`) no es un número mayor que 0 ENTONCES el script
DEBE terminar con un código de salida distinto de 0 sin enviar ninguna petición.

## R9
SI en modo bucle una llamada falla (error de red, `401`, `5xx` o cualquier respuesta distinta de
`200`) ENTONCES el script DEBE registrar en el log el código HTTP o, si no hubo respuesta, el
tipo de error.

## R10
SI en modo bucle una llamada falla ENTONCES el script DEBE continuar con la siguiente vuelta del
bucle tras esperar el intervalo.

## R11
El script NO DEBE escribir el valor de `SERVICE_TOKEN` en el log, en la salida estándar ni en
la salida de error, en ningún modo ni caso de error.

## R12
El script DEBE usar como tiempo de espera de cada petición
`CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS`, o 120 segundos si esa variable no está definida.

## R29
SI `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` está definida y no es un número mayor que 0 ENTONCES el
script DEBE terminar con un código de salida distinto de 0 sin enviar ninguna petición, tanto en
llamada única como en modo bucle.

## R30
MIENTRAS el script se ejecuta en llamada única, el script NO DEBE terminar con error por el
valor de `CHECK_TIMEOUTS_INTERVAL_SECONDS` (la llamada única no usa el intervalo).

(R29 y R30 se añadieron en la revisión del spec; la numeración de R1-R28 no cambia.)

## Docker Compose y configuración

## R13
`docker-compose.yml` DEBE incluir un servicio `timeouts_worker` que ejecute
`vencer_casos.py` en modo bucle (`--intervalo`) leyendo las variables de `.env`.

## R14
El servicio `timeouts_worker` de `docker-compose.yml` NO DEBE publicar puertos.

## R15
La imagen que usa `timeouts_worker` (la de `services/handover/Dockerfile`) DEBE contener
`scripts/vencer_casos.py`.

## R16
`.env.example` DEBE declarar `CHECK_TIMEOUTS_INTERVAL_SECONDS=60` y
`CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS` con su valor por defecto.

## Servicio handover — `POST /cases/check-timeouts`

## R17
CUANDO handover procesa `POST /cases/check-timeouts` y encuentra un caso `open` vencido, el
sistema DEBE obtener la reclamación de vencimiento de ese caso mediante una escritura condicional
(estado `open` y sin reclamación vigente) antes de enviarle `HANDOVER_TIMEOUT_REPLY`.

## R18
SI la reclamación de vencimiento de un caso no se obtiene porque otra ejecución de
`check-timeouts` tiene una reclamación vigente ENTONCES el sistema NO DEBE enviar
`HANDOVER_TIMEOUT_REPLY` a ese caso en esta ejecución.

## R19
SI un caso leído como `open` pasó a `assigned` o `closed` antes de obtener la reclamación
ENTONCES el sistema NO DEBE enviarle `HANDOVER_TIMEOUT_REPLY` ni modificar el caso.

## R20
CUANDO el envío de `HANDOVER_TIMEOUT_REPLY` tiene éxito, el sistema DEBE marcar el caso
`timed_out` mediante una escritura condicional a que el caso siga en estado `open`.

## R21
SI un caso pasó a `assigned` o `closed` mientras se le enviaba `HANDOVER_TIMEOUT_REPLY`
ENTONCES el sistema NO DEBE modificar su estado, `advisor_id`, `assigned_at`, `closed_at` ni
`closed_by`.

## R22
SI un caso pasó a `assigned` o `closed` mientras se le enviaba `HANDOVER_TIMEOUT_REPLY`
ENTONCES el sistema NO DEBE incluirlo en `timed_out_cases`.

## R23
SI el envío de `HANDOVER_TIMEOUT_REPLY` a un caso falla ENTONCES el sistema DEBE liberar su
reclamación de vencimiento, de modo que el caso siga `open` y la siguiente llamada a
`check-timeouts` lo reintente sin esperar (mantiene R19 de la #7).

## R24
SI un caso `open` vencido tiene una reclamación de vencimiento que ya no es vigente (ejecución
interrumpida) ENTONCES el sistema DEBE reclamarlo de nuevo y enviarle `HANDOVER_TIMEOUT_REPLY`.

## Servicio handover — `POST /handover` (reutilización)

## R25
CUANDO handover reutiliza un caso en `POST /handover`, el sistema DEBE escribir únicamente sus
`last_messages`, sin escribir `status`, `advisor_id`, `assigned_at`, `closed_at` ni
`closed_by`.

## R26
SI la respuesta de `POST /handover` es `no_advisors` y el caso reutilizado pasó a `assigned`
entre su lectura y el marcado `timed_out` de R10 (#7) ENTONCES el sistema NO DEBE cambiar su
estado ni su asesor.

## Servicio handover — persistencia Postgres

## R27
`PostgresCaseRepository` DEBE ejecutar cada escritura condicional (reclamar, liberar, marcar
`timed_out`) como una única sentencia `UPDATE` parametrizada con `%s` cuya condición de estado
va en el `WHERE`.

## R28
`PostgresCaseRepository` DEBE añadir la columna de la reclamación de vencimiento a
`handover_cases` con `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` en el primer uso, junto al resto
del esquema.
