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
| `PRIVACY_NOTICE_TEXT` | orchestrator | Texto del aviso de privacidad que ve el cliente. |
| `PRIVACY_NOTICE_VERSION` | orchestrator | Versión del aviso aceptado. |
| `PRIVACY_ACCEPT_PHRASE` | orchestrator | Frase con la que el cliente acepta el aviso; el gateway la hereda por referencia como `MESSAGE_GROUPING_ACCEPT_PHRASE`. |
| `PRIVACY_ACCEPTED_REPLY` | orchestrator | Respuesta fija tras aceptar el aviso. |
| `PRIVACY_RETENTION_DAYS` | handover | Plazo de retención de datos personales; única fuente. |
| `PRIVACY_ACTIVE_CASE_MAX_DAYS` | handover | Antigüedad máxima de un caso activo antes de cerrarlo y borrarlo. |
| `IDENTITY_PUBLIC_BASE_URL` | orchestrator | URL pública del orchestrator; debe empezar por `https://`. Se usa para el enlace `/acceso`. |
| `IDENTITY_LINK_SIGNING_KEY` | orchestrator | Secreto de firma de los enlaces de login, distinto de `SERVICE_TOKEN`; mínimo 32 caracteres. |
| `PANEL_2FA_ENCRYPTION_KEY` | orchestrator | Clave Fernet de 32 bytes en base64 urlsafe para cifrar el secreto TOTP. Obligatoria en producción; no se versiona. |
| `PANEL_2FA_REQUIRED` | orchestrator | `true` en producción; si se deja sin definir, el valor efectivo es `true` con `APP_ENV=production` y `false` en otros entornos. |
| `PANEL_2FA_ISSUER` | orchestrator | Nombre del emisor en la URI `otpauth://`; entre 1 y 64 caracteres. |
| `PANEL_2FA_WINDOW_STEPS` | orchestrator | Ventana de pasos TOTP aceptada (0-2); por defecto 1. |
| `PANEL_2FA_RECOVERY_CODES` | orchestrator | Códigos de recuperación generados al activar el factor (4-20); por defecto 8. |

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

### 2.2 Agrupación de mensajes (#30)

`telegram-gateway` agrupa mensajes consecutivos del mismo chat antes de
llamarlos al `orchestrator`. Los valores por defecto están en `.env.example`
(`MESSAGE_GROUPING_*`); se pueden cambiar sin tocar el código. En el
Blueprint solo se declara `MESSAGE_GROUPING_ACCEPT_PHRASE`, que se hereda por
referencia de `PRIVACY_ACCEPT_PHRASE` del `orchestrator`: la frase de
aceptación debe ser idéntica en ambos servicios para que no se agrupe con otros
mensajes. Si el `orchestrator` cambia esa frase, hay que redesplegar el
`telegram-gateway` para que herede el valor nuevo.

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

### 4.1 Configurar el webhook de WhatsApp (Meta Cloud API, #43)

El proveedor de producción de WhatsApp es **Meta Cloud API**. En la app de Meta
(WhatsApp → Configuration) se registra la URL pública del **telegram-gateway**:

- **Callback URL:** `{PUBLIC_BASE_URL}/whatsapp/webhook` (debe empezar por
  `https://`).
- **Verify token:** el mismo valor que `WHATSAPP_VERIFY_TOKEN` en Render.
- **Suscripción:** el campo `messages` de la cuenta de WhatsApp Business.
- **Credenciales:** un token de sistema permanente en `WHATSAPP_ACCESS_TOKEN`,
  el App Secret de la app en `WHATSAPP_APP_SECRET` y el identificador del número
  emisor en `WHATSAPP_PHONE_NUMBER_ID`.

Mientras `WHATSAPP_ENABLED=false` (valor por defecto), el gateway responde
`404` a `GET/POST /whatsapp/webhook` y `POST /send` con `channel=whatsapp`
devuelve `502 upstream_error`. No se imprimen ni se versionan los secretos.

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

## 6. Recuperar el segundo factor del panel

Este procedimiento exige acceso operativo a la base de datos y está pensado
para un administrador único que perdió su factor y sus códigos. El bootstrap de
la feature #23 no sirve: se niega a actuar si ya existe un administrador.
Declara explícitamente el perfil en `:'profile_id'` (un `profiles.id`) y no
selecciona, muestra ni pide el secreto cifrado, los códigos de recuperación,
sus hashes ni la clave de cifrado.

```sql
-- psql "$DATABASE_URL" -v operator='nombre.operador' -v profile_id='<profiles.id>'
BEGIN;
SELECT id, username, role FROM profiles WHERE id = :'profile_id';  -- confirmar el perfil
INSERT INTO panel_audit (actor_profile_id, actor_role, action, target, result, at)
  SELECT 'ops:' || :'operator', 'operator', 'two_factor_reset_ops', id, 'ok', now()
  FROM profiles WHERE id = :'profile_id';
DELETE FROM staff_recovery_codes WHERE profile_id = :'profile_id';
DELETE FROM staff_two_factor     WHERE profile_id = :'profile_id';
DELETE FROM admin_sessions       WHERE profile_id = :'profile_id';
COMMIT;
```

Verifica que el `SELECT` devolvió exactamente una fila antes del `COMMIT`. Si el
perfil no existe, el `INSERT … SELECT` no inserta y los `DELETE` no tocan filas.
El actor de auditoría es `ops:<operador>` y no es un perfil real; la columna
`actor_profile_id` no tiene clave foránea.

Tras ejecutarlo, el perfil inicia sesión sin segundo factor. Si
`PANEL_2FA_REQUIRED` está activo, queda en una sesión restringida al registro
del nuevo factor, como cualquier perfil sin segundo factor.

### 6.1 Pérdida o cambio de `PANEL_2FA_ENCRYPTION_KEY`

Esta clave no se rota sin ejecutar antes este procedimiento para los perfiles
afectados: si cambia, los secretos cifrados dejan de descifrarse. La variante
recorre `staff_two_factor` y borra los datos de todos los perfiles con segundo
factor, dejando una fila de auditoría por perfil afectado.

```sql
-- psql "$DATABASE_URL" -v operator='nombre.operador'
BEGIN;
INSERT INTO panel_audit (actor_profile_id, actor_role, action, target, result, at)
  SELECT 'ops:' || :'operator', 'operator', 'two_factor_reset_ops',
         profile_id, 'ok', now()
  FROM staff_two_factor;
DELETE FROM staff_recovery_codes
  WHERE profile_id IN (SELECT profile_id FROM staff_two_factor);
DELETE FROM admin_sessions
  WHERE profile_id IN (SELECT profile_id FROM staff_two_factor);
DELETE FROM staff_two_factor;
COMMIT;
```
