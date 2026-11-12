# Requirements — health checks de dependencias (#47)

Servicios: `telegram_gateway`, `orchestrator`, `rag` y `handover`.

## R1 — Dependencias saludables
CUANDO las dependencias críticas de un servicio responden correctamente, `GET /health` DEBE responder `200` sin `X-Service-Token` y conservar el cuerpo actual `{"status":"ok","service":"<nombre>"}`.

## R2 — Dependencia no disponible
SI una dependencia crítica configurada no responde o falla ENTONCES `GET /health` DEBE responder `503` con `status` igual a `unhealthy`, el nombre del servicio y el nombre de cada dependencia fallida, sin exponer URLs, credenciales ni DSN.

## R3 — Redis comprobado
CUANDO `telegram_gateway` verifica su salud, el sistema DEBE comprobar Redis.

## R4 — PostgreSQL comprobado
CUANDO `orchestrator`, `rag` o `handover` verifican su salud, cada sistema DEBE comprobar PostgreSQL.

## R5 — Probe limitado y de solo lectura
CUANDO se comprueba una dependencia, el sistema DEBE usar una operación de solo lectura y un timeout finito para terminar la comprobación aunque la conexión quede bloqueada.

## R6 — Contenedor no saludable
CUANDO un servicio responde `503` en `/health`, Docker Compose DEBE marcar el contenedor como `unhealthy`.

## R7 — Contenedor saludable
CUANDO un servicio responde `200` en `/health`, Docker Compose DEBE marcar el contenedor como `healthy`.

## R8 — Verificación aislada
CUANDO se prueba cada servicio, las pruebas DEBEN verificar estado saludable, fallo y timeout mediante adaptadores falsos, sin requerir Postgres, Redis ni red reales.

## R9 — Verificación del repositorio
CUANDO se ejecuta `./init.sh` después de implementar la feature, el sistema DEBE completar la suite sin fallos.
