# Conectar una bandeja Gmail

El canal Gmail utiliza el mismo núcleo y panel que los demás canales. Cada
correo entrante se convierte en un mensaje de cliente; las respuestas del bot
y del asesor se envían como texto plano en el hilo original.

## Requisitos de Google

1. En Google Cloud crea/elige un proyecto y habilita **Gmail API**.
2. Configura la pantalla de consentimiento OAuth y crea un OAuth Client ID para
   una aplicación web/servidor.
3. Autoriza la cuenta dedicada de soporte con los scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
4. Obtén un `refresh_token` autorizado para esa cuenta. Al usar scopes
   restringidos, Google puede exigir verificación de la aplicación; si los
   datos se almacenan o transmiten desde servidores, pueden aplicar requisitos
   de evaluación de seguridad. Consulta los requisitos vigentes de Google antes
   de producción.

Usa una bandeja dedicada al soporte. Lázaro no necesita el scope
`https://mail.google.com/`, no borra correo y no descarga adjuntos.

## Crear el canal

Con `X-Service-Token` crea `canal-soporte-gmail` mediante `POST /channels`:

```json
{
  "id": "soporte-gmail",
  "name": "Soporte por correo",
  "adapter_type": "gmail_api",
  "icon": "✉️",
  "color": "#C2410C",
  "config": {
    "email_address": "soporte@tu-dominio.com",
    "consent_mode": "texto"
  },
  "credentials": {
    "client_id": "...apps.googleusercontent.com",
    "client_secret": "...",
    "refresh_token": "..."
  },
  "active": true
}
```

El gateway cifra los tres valores OAuth con `CHANNEL_SECRETS_KEY`. Asegúrate de
que `CHANNEL_SECRETS_KEY` sea estable entre reinicios y despliegues; perderla
impide descifrar y usar las credenciales guardadas. La cuenta de la respuesta
`users.getProfile` debe coincidir con `config.email_address`.

También se puede crear desde **Administración → Canales**: elige `gmail_api`,
escribe el correo de la bandeja y pega las tres credenciales, una por línea
(`nombre=valor`). El valor del secreto solo aparece al guardar. Activa el canal
cuando confirmes que el proyecto OAuth tiene permiso para abrir esa bandeja.

## Activar el procesamiento

La primera sincronización guarda el `historyId` actual y no importa correos
anteriores. Con Docker Compose no hay que programar nada: el servicio
`gmail_sync_worker` (imagen del gateway) ejecuta en bucle

```text
python sincronizar_gmail.py --intervalo
```

cada 60 segundos (configurable con `GMAIL_SYNC_INTERVAL_SECONDS`) y se reinicia
solo si se cae. Sin `--intervalo` el script hace una única pasada y devuelve 1 si algún
canal falla, por si se prefiere un scheduler externo
(`python scripts/sincronizar_gmail.py`).

Variables necesarias: `TELEGRAM_GATEWAY_URL` (URL interna del servicio) y
`SERVICE_TOKEN`, ambas del `.env`. Se procesan solo canales Gmail activos; sin
ninguno, el worker solo consulta la lista de canales. Un fallo en una pasada se
registra y se reintenta en la siguiente. Mensajes de `INBOX` se deduplican por el
ID que asigna Gmail; los correos enviados por la propia bandeja se ignoran.

Para ver su actividad: `docker compose logs -f gmail_sync_worker` (registra
`gmail_channel_synced channel_id=... status=... processed=N`, nunca texto ni
credenciales).

### Despliegue en AWS (EC2)

Producción corre en una instancia EC2 con Docker Compose, por lo que el
`gmail_sync_worker` se despliega con el resto de servicios en cada push a la
rama de despliegue. No hace falta cron, `systemd` ni EventBridge. (En
ECS/Fargate habría que lanzar la misma imagen del gateway con el comando
anterior como servicio o tarea programada.)

Checklist de la conexión:

- [x] Producción es EC2 con Docker Compose.
- [x] Sincronización recurrente cada 60 s: servicio `gmail_sync_worker`.
- [x] Sincronización inicial ejecutada (`status=initialized`): fijó el cursor
  sin importar mensajes anteriores.
- [ ] Enviar un correo nuevo de texto plano desde otra cuenta y comprobar que
  Lázaro lo recibe y responde dentro del mismo hilo.

Si Gmail responde que el cursor ya venció, el endpoint de sincronización devuelve
`gmail_history_expired` sin saltar el problema. Un administrador puede ejecutar
`POST /channels/soporte-gmail/gmail/reset-cursor` con `X-Service-Token`; ese
reinicio ignora el backlog anterior al momento en que se ejecuta.

## Alcance y privacidad

- En esta versión se procesan cuerpos `text/plain`. Correos HTML-only y
  mensajes que solo contienen adjuntos se tratan como no soportados; no se
  descarga ni envía ningún adjunto.
- La primera sincronización no importa históricos. Para vincular o recuperar
  mensajes anteriores se debe responder el correo de nuevo; no hay backfill.
- El consentimiento, login, retención, memoria y supresión se mantienen según
  las reglas vigentes del orquestador.
- El envío conserva `threadId`, `In-Reply-To` y `References`, con MIME
  `text/plain`; la salida del modelo nunca se inserta como HTML.
- No configures logs HTTP que expongan `Authorization`, cuerpos de correo o
  credenciales OAuth. Los logs propios registran conteos y códigos, no texto.

## Referencias oficiales

- [Scopes Gmail API](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Sincronización incremental](https://developers.google.com/workspace/gmail/api/guides/sync)
- [Enviar correo](https://developers.google.com/workspace/gmail/api/guides/sending)
- [Hilos y respuestas](https://developers.google.com/workspace/gmail/api/guides/threads)
