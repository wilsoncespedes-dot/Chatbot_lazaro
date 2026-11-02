# Despliegue en Render

> `render.yaml` es **preparación**: esta feature no despliega, no crea recursos
> ni fija planes ni precios. El humano elige el plan al crear el Blueprint.

## 1. Crear el Blueprint

1. En Render, elige **New → Blueprint** y conecta este repositorio.
2. Render leerá `render.yaml` y mostrará los recursos:
   - `telegram-gateway` y `orchestrator`: servicios `web` públicos con
     `healthCheckPath: /health`.
   - `rag` y `handover`: servicios privados (`pserv`), sin URL pública.
   - `timeouts-worker`: worker privado que ejecuta
     `python vencer_casos.py --intervalo`.
   - `retention-worker`: worker privado que ejecuta
     `python purgar_datos.py --intervalo`. No expone puertos ni recibe tráfico.
     Cada iteración purga primero `handover` y después `orchestrator`; si
     `handover` falla, no se llama a `orchestrator` en esa vuelta.
   - `lazaro-postgres` (PostgreSQL 16) y `lazaro-redis` (Key Value), ambos con
     `ipAllowList: []` para que solo se usen por la red privada.
3. Todos los recursos comparten la región del Blueprint. Si hace falta cambiarla,
   se edita en un único valor por recurso antes de crear el Blueprint.

## 2. Rellenar las variables `sync: false`

Render pedirá los valores que no están versionados. Rellénalos en el panel,
nunca en el repositorio:

| Variable | Dónde | Contenido |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | telegram-gateway | Token del bot de BotFather. |
| `TELEGRAM_WEBHOOK_SECRET` | telegram-gateway | 32-256 caracteres `A-Z a-z 0-9 _ -`. |
| `LLM_API_KEY`, `LLM_MODEL`, `TELEGRAM_BOT_USERNAME` | orchestrator | Proveedor de IA y bot público. |
| `EMBEDDINGS_API_KEY`, `EMBEDDINGS_MODEL` | rag | Proveedor de embeddings. |
| `ADVISOR_CHAT_IDS` | handover | Chat ids de Telegram separados por comas. |
| `PRIVACY_NOTICE_TEXT` | orchestrator | Texto del aviso de privacidad que ve el cliente. |
| `PRIVACY_NOTICE_VERSION` | orchestrator | Versión del aviso aceptado. |
| `PRIVACY_ACCEPT_PHRASE` | orchestrator | Frase con la que el cliente acepta el aviso. |
| `PRIVACY_ACCEPTED_REPLY` | orchestrator | Respuesta fija tras aceptar el aviso. |
| `PRIVACY_RETENTION_DAYS` | handover | Plazo de retención de datos personales; única fuente. |
| `PRIVACY_ACTIVE_CASE_MAX_DAYS` | handover | Antigüedad máxima de un caso activo antes de cerrarlo y borrarlo. |

`SERVICE_TOKEN` lo genera Render en el env group `lazaro-compartido`; no lo
copies al repositorio. `DATABASE_URL` y `REDIS_URL` salen de las referencias a
la base y a Key Value.

En producción cada servicio se niega a arrancar si falta una variable
obligatoria, si conserva un placeholder conocido o si `SERVICE_TOKEN` tiene
menos de 32 caracteres. El mensaje de arranque solo nombra las variables, nunca
sus valores.

### 2.1 Retención y privacidad (#27, #28)

`PRIVACY_RETENTION_DAYS` se rellena **solo en `handover`**. El `orchestrator`
lo hereda por referencia (`fromService` con `envVarKey`), de modo que existe un
único valor compartido. Tras cambiarlo hay que redesplegar **ambos** servicios
para que los dos usen el mismo plazo.

`PRIVACY_ACTIVE_CASE_MAX_DAYS` debe ser estrictamente menor que
`PRIVACY_RETENTION_DAYS`. Cuando un caso activo supera ese límite, la purga lo
cierra y lo borra sin avisar al cliente ni al asesor.

El texto del aviso, la frase de aceptación, la respuesta de confirmación, la
versión y los plazos los define el propietario con revisión legal **antes de
desplegar**; esta configuración no fija ningún valor. Mientras falten, el
`orchestrator` y `handover` no arrancan en producción y el worker registra
`privacy_purge_failed`. Los nombres, la semántica y las validaciones están en
`specs/privacidad_y_retencion_datos/design.md`.

La purga no cubre los logs de la plataforma Render, las copias de seguridad de
Postgres, la tabla `privacy_consents` ni las solicitudes individuales de
supresión o revocación, que se atienden por un procedimiento aparte.

## 3. Verificar `vector` en PostgreSQL

Tras crear la base, comprueba que la extensión está disponible:

```bash
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

El servicio `rag` también ejecuta esa sentencia al iniciar. No se usa
`scripts/db/init` en Render.

## 4. Configurar el webhook de Telegram

`PUBLIC_BASE_URL` es la URL pública de **telegram-gateway** (no la del
orchestrator) y debe empezar por `https://`. Con el token, el secreto y esa URL
en el entorno del operador:

```bash
python scripts/configurar_webhook.py
```

El script valida la URL y el formato del secreto, llama a `setWebhook` con
`url=<PUBLIC_BASE_URL>/telegram/webhook`, `secret_token` y
`allowed_updates=["message"]`, y después muestra `getWebhookInfo` con `url`,
`pending_update_count` y `last_error_message`.

Opciones:

- `--solo-consultar`: no registra; solo consulta `getWebhookInfo`.
- `--drop-pending`: descarta las actualizaciones pendientes al registrar.

El script nunca imprime `TELEGRAM_BOT_TOKEN` ni `TELEGRAM_WEBHOOK_SECRET`, ni
siquiera ante errores HTTP o de red.

## 5. Comprobar `/health`

Cuando Render termine el despliegue:

```bash
curl https://<telegram-gateway>/health
curl https://<orchestrator>/health
```

Ambos deben responder `{"status": "ok", "service": "<nombre>"}` sin token.

El orchestrator es público porque el panel `/admin` lo usan los clientes, pero
sus rutas internas siguen exigiendo `X-Service-Token`; `/admin` exige sesión y
CSRF. El gateway y handover hablan con el orchestrator por la red privada
(`hostport`), no por la URL pública.
