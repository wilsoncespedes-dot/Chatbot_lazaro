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
anteriores. El script es de una sola ejecución; debe ejecutarse cada 60 segundos
desde un scheduler:

```text
python scripts/sincronizar_gmail.py
```

Variables necesarias: `TELEGRAM_GATEWAY_URL` (URL interna del servicio) y
`SERVICE_TOKEN`. Se procesan solo canales Gmail activos. El comando falla si
algún canal falla y el scheduler puede reintentarlo. Mensajes de `INBOX` se
deduplican por el ID que asigna Gmail; los correos enviados por la propia
bandeja se ignoran.

### Cierre pendiente del despliegue en AWS

El despliegue de producción se encuentra en AWS, pero se debe confirmar qué
servicio ejecuta Lázaro antes de configurar el scheduler:

- **EC2:** instalar un timer de `systemd` o `cron` en la instancia y ejecutar el
  script desde un entorno que tenga el código y `httpx` disponibles.
- **ECS/Fargate:** usar EventBridge Scheduler para lanzar una tarea recurrente
  cada minuto. La imagen de esa tarea debe incluir el script y sus dependencias;
  la imagen actual del gateway no copia `scripts/sincronizar_gmail.py`.
- **Otro servicio AWS:** elegir un scheduler que pueda ejecutar el script y
  alcanzar el endpoint interno del gateway.

En todos los casos, proporcionar `TELEGRAM_GATEWAY_URL` y `SERVICE_TOKEN` desde
la configuración segura del entorno. No incluir tokens ni credenciales OAuth en
el payload del scheduler, comandos guardados, ni logs.

Checklist para completar la conexión:

- [ ] Confirmar si el servicio de producción es EC2, ECS/Fargate u otro.
- [ ] Configurar una ejecución recurrente del script cada 60 segundos.
- [ ] Ejecutar una sincronización inicial; esta fija el cursor y no importa
  mensajes anteriores.
- [ ] Enviar un correo nuevo de texto plano desde otra cuenta y comprobar que
  Lázaro lo recibe y responde dentro del mismo hilo.

AWS documenta [cómo conectar a una instancia EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-to-linux-instance.html)
y [cómo programar tareas de ECS con EventBridge Scheduler](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html).

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
