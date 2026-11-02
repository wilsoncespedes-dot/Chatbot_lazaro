# #24 despliegue_produccion — Requirements

> Preparación de despliegue en Render. El Blueprint (`render.yaml`) es un
> artefacto versionado: **no** se despliega, no se crean recursos y no se fijan
> planes ni precios en esta feature.
>
> Referencias oficiales (consultadas 2026-11-01): Render `blueprint-spec`,
> `health-checks`, `private-network`, `postgresql-extensions`,
> `configure-environment-variables`; Telegram Bot API `setWebhook`
> (`secret_token`: 1-256 caracteres `A-Z a-z 0-9 _ -`); Render
> `https://render.com/articles/how-render-handles-ddos-attacks` y
> `https://feedback.render.com/features/p/send-the-correct-x-forwarded-for`
> (el primer valor de `X-Forwarded-For` es la IP del cliente).

## Cobertura del acceptance

| Acceptance | Requirements |
|---|---|
| Blueprint con servicios, base, Redis y worker; gateway y orchestrator públicos (`web`, `/health`), rag/handover `pserv`, worker privado | R1–R11 |
| Rutas internas del orchestrator (y de rag/handover) con 401 sin `X-Service-Token`; panel con sesión/CSRF | R29–R31 |
| Secretos fuera del repo; arranque falla en producción con secretos faltantes/placeholders | R12–R20 |
| CI verifica tests y construcción Docker | R21–R22 |
| Procedimiento verificable del webhook sin imprimir secretos | R23–R28 |
| Rate limit del login por IP real del cliente tras el proxy de Render | R32 |

## Blueprint (`render.yaml`)

### R1
El Blueprint DEBE declarar exactamente dos servicios `type: web`, `telegram-gateway` y `orchestrator`, construidos con `services/telegram_gateway/Dockerfile` y `services/orchestrator/Dockerfile` respectivamente, ambos con `healthCheckPath: /health`.

### R2
El Blueprint DEBE declarar `rag` y `handover` como servicios `type: pserv` (privados, sin URL pública), cada uno con su Dockerfile de `services/<servicio>/Dockerfile`, y NO DEBE declarar ningún otro servicio `web` ni `pserv`.

### R3
El Blueprint DEBE declarar `timeouts-worker` como `type: worker` construido con `services/handover/Dockerfile` y comando `python vencer_casos.py --intervalo`.

### R4
El Blueprint DEBE declarar una base Render Postgres con `postgresMajorVersion: "16"` e `ipAllowList: []` (solo red privada).

### R5
El Blueprint DEBE declarar una instancia `type: keyvalue` con `ipAllowList: []`.

### R6
El Blueprint DEBE asignar el mismo valor de `region` a todos los servicios, a la base y a la instancia Key Value.

### R7
El Blueprint NO DEBE contener la clave `plan` en ningún recurso.

### R8
El Blueprint NO DEBE contener un `value` literal para ninguna variable secreta (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `SERVICE_TOKEN`, `LLM_API_KEY`, `EMBEDDINGS_API_KEY`, `DATABASE_URL`, `REDIS_URL`); los secretos de terceros DEBEN declararse con `sync: false`.

### R9
El Blueprint DEBE definir `SERVICE_TOKEN` con `generateValue: true` dentro de un env group compartido enlazado (`fromGroup`) por los cinco servicios.

### R10
El Blueprint DEBE obtener `DATABASE_URL` mediante `fromDatabase` (`property: connectionString`) y `REDIS_URL` mediante `fromService` (`type: keyvalue`, `property: connectionString`).

### R11
El Blueprint DEBE obtener `ORCHESTRATOR_URL`, `RAG_URL`, `HANDOVER_URL` y `TELEGRAM_GATEWAY_URL` mediante `fromService` con `property: hostport`, sin URLs literales.

## Configuración de producción

### R12
CUANDO una variable `*_URL` interna llega como `host:port` sin esquema, cada servicio y `scripts/vencer_casos.py` DEBEN usarla como `http://host:port`.

### R13
CUANDO `APP_ENV` tiene un valor distinto de `development` o `production`, el servicio DEBE negarse a arrancar.

### R14
MIENTRAS `APP_ENV=production`, cada servicio DEBE negarse a arrancar si alguna de sus variables obligatorias (tabla en `design.md`) está vacía.

### R15
MIENTRAS `APP_ENV=production`, cada servicio DEBE negarse a arrancar si una variable obligatoria coincide (sin distinguir mayúsculas) con un placeholder conocido (`cambia-esto`, `changeme`, `change-me`, `placeholder`, `secret`, `test`, `xxx`).

### R16
MIENTRAS `APP_ENV=production`, cada servicio y el worker DEBEN negarse a arrancar si `SERVICE_TOKEN` tiene menos de 32 caracteres.

### R17
MIENTRAS `APP_ENV=production`, orchestrator, rag y handover DEBEN negarse a arrancar si `DATABASE_URL` contiene las credenciales de desarrollo `lazaro:lazaro@`.

### R18
MIENTRAS `APP_ENV=production`, telegram_gateway DEBE negarse a arrancar si `TELEGRAM_WEBHOOK_SECRET` no cumple `^[A-Za-z0-9_-]{32,256}$`.

### R19
MIENTRAS `APP_ENV=production`, orchestrator DEBE negarse a arrancar si `ADMIN_COOKIE_SECURE` es `false`.

### R20
SI la validación de producción falla ENTONCES el mensaje de error DEBE nombrar solo las variables afectadas y NO DEBE incluir sus valores.

## CI

### R21
CUANDO hay `push` o `pull_request`, CI DEBE ejecutar `python -m pytest` (incluye las pruebas del Blueprint).

### R22
CUANDO hay `push` o `pull_request`, CI DEBE construir (sin publicar) las imágenes Docker de los cuatro Dockerfiles de `services/`.

## Webhook de Telegram

### R23
CUANDO se ejecuta `scripts/configurar_webhook.py` con `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` y `PUBLIC_BASE_URL` válidos, el script DEBE llamar a `setWebhook` con `url=<PUBLIC_BASE_URL>/telegram/webhook` y `secret_token=<TELEGRAM_WEBHOOK_SECRET>`.

### R24
SI `PUBLIC_BASE_URL` no usa `https://` ENTONCES el script DEBE terminar con código distinto de 0 sin llamar a Telegram.

### R25
SI `TELEGRAM_WEBHOOK_SECRET` no cumple `^[A-Za-z0-9_-]{32,256}$` o falta una variable obligatoria ENTONCES el script DEBE terminar con código distinto de 0 sin llamar a Telegram.

### R26
CUANDO el script termina `setWebhook`, DEBE llamar a `getWebhookInfo` e imprimir `url`, `pending_update_count` y `last_error_message`.

### R27
El script NO DEBE escribir el valor de `TELEGRAM_BOT_TOKEN` ni de `TELEGRAM_WEBHOOK_SECRET` en stdout ni stderr, incluido ante errores HTTP o de red.

### R28
El repositorio DEBE incluir `docs/despliegue.md` con el procedimiento: crear el Blueprint, rellenar las variables `sync: false`, verificar `vector`, ejecutar el script del webhook y comprobar `/health`.

## Exposición pública del orchestrator

### R29
SI una petición a `POST /messages`, `POST /profiles`, `POST /profiles/{id}/link-token` o `POST /cases/{id}/reply` del orchestrator no trae `X-Service-Token` o trae uno distinto de `SERVICE_TOKEN` ENTONCES el orchestrator DEBE responder 401 con `error=unauthorized` sin ejecutar la operación.

### R30
SI una petición a una ruta protegida de rag o handover (toda ruta distinta de `/health`) no trae `X-Service-Token` válido ENTONCES el servicio DEBE responder 401.

### R31
SI una petición a `/admin/*` (salvo `/admin/login` y `/admin/static/*`) no trae sesión válida ENTONCES el orchestrator DEBE redirigir con 303 a `/admin/login` aunque traiga un `X-Service-Token` válido, y SI un `POST` del panel con sesión no trae `csrf_token` válido ENTONCES DEBE responder 403.

## IP del cliente tras el proxy de Render

### R32
El Blueprint DEBE definir `ADMIN_TRUST_PROXY_HEADERS=true` en el servicio `orchestrator`, y MIENTRAS `ADMIN_TRUST_PROXY_HEADERS=true` la IP usada por el rate limit del login del panel DEBE ser el **primer** valor (sin espacios) de `X-Forwarded-For` —nunca el último, que es el salto del proxy—; SI la cabecera falta, está vacía o su primer valor está vacío ENTONCES DEBE usarse `request.client.host`.
