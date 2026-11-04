# #42 administracion_y_avisos — Requirements

Servicios afectados: **orchestrator** (panel administrativo, dominio, repositorio,
ruta interna del aviso), **contracts** (modelos aditivos de la ruta del aviso) y
**scripts** (worker `avisar_vencimientos.py`, ejecutado con la imagen de
handover como los workers existentes). `telegram_gateway`, `rag`, `handover`
(código) y `eval` no cambian.

Amplía lo existente sin duplicarlo: reutiliza las funciones de dominio de #38
(`create_client`, `renew_credential`, `revoke_credential`,
`close_client_session`, `_client_status`, `credential_status`,
`days_remaining`, `resolve_identity_policy` y las claves `identity.*` de
`app_settings`), los textos fijos de #37 (`ConversationTexts`, `/admin/texts`),
las plantillas y la ventana WhatsApp de #41 (`channel_window`,
`advisor_send_template`, `TemplateBlock`), la auditoría `panel_audit` de #41 y
la sesión/CSRF del panel admin de #21.

Vocabulario:

- **Administrador**: perfil `role = "admin"` con sesión válida de
  `admin_sessions` (`_require_session` de `admin_routes.py`). Una sesión de
  asesor no es sesión de administrador.
- **Registro de ajustes operativos**: conjunto cerrado de claves de
  `app_settings` listado en `design.md` (§Ajustes operativos), cada una con
  tipo, rango y valor por defecto tomado de la variable de entorno.
- **Valor efectivo** de un ajuste: el valor de `app_settings` si existe y es
  válido; si no, el valor por defecto de entorno.
- **Periodo de vigencia**: la pareja `(profile_id, valid_until)` de una
  credencial. Renovar crea un periodo nuevo.
- **Credencial candidata a aviso**: credencial con `revoked_at IS NULL`,
  `valid_from <= now < valid_until` y `valid_until - now <=
  identity.expiry_notice_days` efectivo (mismo criterio que el estado
  `por_vencer` de #38).
- **Último chat del cliente**: contacto de la fila de `client_sessions` del
  perfil con mayor `last_activity_at` (activa o finalizada).
- **Dentro de horario**: con `now` UTC desplazado por
  `business_hours.utc_offset_minutes`, el día ISO (1 = lunes) pertenece a
  `business_hours.days` y la hora local `t` cumple `start <= t < end`; si
  `end < start` el rango cruza medianoche y se cumple con `t >= start` o
  `t < end`.
- **Fecha local**: `valid_until` desplazada por
  `business_hours.utc_offset_minutes`, formato `dd/mm/aaaa`.

Trazabilidad con el acceptance de `feature_list.json` (#42):

| Criterio de aceptación | Requirements |
|---|---|
| 1. Crear clientes y credenciales, renovar por periodo configurado, revocar y cerrar sesiones; días calculados desde fechas | R1–R11 |
| 2. Textos legales/fijos versionados, plantillas y aprobación, horarios y plazos/tiempos sin redeploy | R15–R44, R72–R74 |
| 3. Aviso de vencimiento con plazo configurable, plantilla aprobada fuera de ventana, sin duplicados | R45–R61 |
| 4. Métricas: primera respuesta, conversaciones por asesor, motivos de escalamiento, preguntas sin respuesta | R62–R68 |
| 5. Pruebas de permisos, configuración efectiva, renovación y aviso único; `./init.sh` verde | R12–R14, R40, R55, R56, R69–R71 |

---

## Clientes y credenciales (orchestrator, panel admin)

## R1
CUANDO un administrador solicita `GET /admin/clientes`, el sistema DEBE
responder `200` con una tabla que contenga, por cada perfil `cliente` con fila
en `client_credentials`, el usuario, el estado (`vigente`, `por_vencer`,
`vencida`, `revocada`, `no_iniciada`), `valid_from`, `valid_until`, los días
restantes, si tiene sesión activa y el estado del aviso de vencimiento del
periodo vigente (`sent`, `failed`, `sending` o vacío).

## R2
El sistema DEBE calcular el estado y los días restantes de cada credencial en
cada lectura a partir de `valid_from`, `valid_until`, `revoked_at` y el reloj
inyectado, sin almacenar ni decrementar ningún contador de días.

## R3
CUANDO un administrador envía `POST /admin/clientes` con usuario y contraseña
válidos y `valid_from`/`valid_until` opcionales (`AAAA-MM-DD`), el sistema DEBE
crear el perfil `cliente` y su credencial mediante `create_client` de #38 y
redirigir con `303` a `/admin/clientes`.

## R4
CUANDO `POST /admin/clientes` llega sin `valid_until`, el sistema DEBE fijar
`valid_until = valid_from + identity.validity_days` efectivo (o `now +
identity.validity_days` si tampoco llega `valid_from`).

## R5
SI `POST /admin/clientes` trae un usuario que no cumple `USERNAME_PATTERN`,
una contraseña más corta que `PROFILE_PASSWORD_MIN_LENGTH`, una fecha no
parseable o `valid_until <= valid_from` ENTONCES el sistema DEBE responder
`422` con el formulario y un mensaje de error, sin crear perfil ni credencial
y sin incluir la contraseña en la respuesta.

## R6
SI `POST /admin/clientes` trae un usuario ya existente ENTONCES el sistema DEBE
responder `409` con el código `username_taken` sin crear filas nuevas.

## R7
CUANDO un administrador envía `POST /admin/clientes/{profile_id}/renovar`, el
sistema DEBE extender `valid_until` a `max(valid_until, now) +
identity.validity_days` efectivo mediante `renew_credential` de #38.

## R8
SI se solicita renovar una credencial revocada ENTONCES el sistema DEBE
responder `409` con el código `credential_revoked` sin modificar la credencial.

## R9
CUANDO un administrador envía `POST /admin/clientes/{profile_id}/revocar`, el
sistema DEBE revocar la credencial y cerrar su sesión activa mediante
`revoke_credential` de #38.

## R10
CUANDO un administrador envía `POST /admin/clientes/{profile_id}/cerrar-sesion`,
el sistema DEBE finalizar la sesión activa del cliente mediante
`close_client_session` de #38 sin modificar `valid_from`, `valid_until` ni
`revoked_at`.

## R11
SI `{profile_id}` de una acción de R7–R10 no corresponde a un cliente con
credencial ENTONCES el sistema DEBE responder `404` con el código
`client_not_found`.

## Permisos (orchestrator)

## R12
SI una petición a cualquier ruta nueva de este spec bajo `/admin/` llega sin
sesión de administrador (sin cookie, sesión vencida o sesión de un perfil
`asesor`/`cliente`) ENTONCES el sistema DEBE redirigir con `303` a
`/admin/login` sin ejecutar la lectura ni la acción.

## R13
SI un `POST` a una ruta nueva de este spec bajo `/admin/` llega sin un
`csrf_token` igual al de la sesión ENTONCES el sistema DEBE responder `403`
sin aplicar ningún cambio.

## R14
SI `POST /credentials/expiry-notices` llega sin un `X-Service-Token` válido
ENTONCES el sistema DEBE responder `401` con `{"error": "unauthorized", ...}`
sin ejecutar la pasada.

## Textos fijos versionados (orchestrator)

## R15
El sistema DEBE añadir a `ConversationTexts` los campos `expiry_notice`,
`out_of_hours_reply`, `closing_reply` y `topics_list`, editables en
`/admin/texts` como el resto de campos, con valor vacío por defecto.

## R16
CUANDO un administrador guarda `/admin/texts`, el sistema DEBE insertar en
`text_versions`, por cada campo cuyo valor cambió, una fila con `version =
última versión del campo + 1`, el valor, el `profile_id` del autor y la fecha,
en la misma transacción que actualiza `app_settings`.

## R17
SI al guardar `/admin/texts` un campo conserva su valor vigente ENTONCES el
sistema NO DEBE crear una versión nueva para ese campo.

## R18
SI al guardar `/admin/texts` cambia `notice_text` y `notice_version` es igual a
la versión vigente ENTONCES el sistema DEBE responder `422` sin guardar ningún
campo ni versión.

## R19
CUANDO un administrador solicita `GET /admin/texts`, el sistema DEBE mostrar
junto a cada campo su número de versión vigente (o «sin historial» si no tiene
versiones).

## R20
CUANDO un administrador solicita `GET /admin/texts/{field}/historial` con un
campo de `CONVERSATION_TEXT_FIELDS`, el sistema DEBE mostrar las últimas
`ADMIN_TEXT_HISTORY_LIMIT` versiones del campo en orden descendente con autor,
fecha y valor escapado con `html.escape`.

## R21
SI `GET /admin/texts/{field}/historial` recibe un campo que no está en
`CONVERSATION_TEXT_FIELDS` ENTONCES el sistema DEBE responder `404`.

## R22
CUANDO se guarda un texto en `/admin/texts`, el siguiente mensaje que lo use
DEBE emplear el valor nuevo sin reiniciar el proceso.

## R23
DONDE `closing_reply` no está vacío, el sistema DEBE enviarlo al cerrar un caso
(`close_case`) en lugar de `CASE_CLOSED_REPLY`.

## R24
DONDE `topics_list` no está vacío, el sistema DEBE enviar `active_welcome +
"\n\n" + topics_list` en cada envío de la bienvenida activa (login con
credencial vigente y renovación desde `no_access`).

## Plantillas de WhatsApp y su aprobación (orchestrator)

## R25
CUANDO un administrador solicita `GET /admin/plantillas`, el sistema DEBE
listar cada plantilla registrada con nombre, propósito, idioma, número de
variables, texto de referencia, estado, autor y fecha de aprobación.

## R26
CUANDO un administrador envía `POST /admin/plantillas` con nombre
`^[a-z0-9_]{1,64}$`, propósito en {`advisor_reply`, `suppression_result`,
`expiry_notice`}, idioma `^[a-z]{2}(_[A-Z]{2})?$`, variables 0–10 y texto de
referencia de 1–1024 caracteres, el sistema DEBE crear la plantilla en estado
`draft`.

## R27
SI `POST /admin/plantillas` trae un campo inválido según R26 ENTONCES el
sistema DEBE responder `422` sin crear la plantilla.

## R28
SI `POST /admin/plantillas` trae un nombre ya registrado ENTONCES el sistema
DEBE responder `409` con el código `template_exists`.

## R29
CUANDO un administrador envía `POST /admin/plantillas/{name}/estado` con una
transición permitida (`draft→pending`, `pending→approved`,
`pending→rejected`, `approved→paused`, `paused→approved`, `rejected→draft`),
el sistema DEBE aplicar el estado y, si el destino es `approved`, registrar el
`profile_id` del administrador y la fecha de aprobación.

## R30
SI la transición pedida en `POST /admin/plantillas/{name}/estado` no está en la
lista de R29 ENTONCES el sistema DEBE responder `409` con el código
`invalid_transition` sin cambiar la plantilla.

## R31
CUANDO un administrador modifica idioma, variables o texto de referencia de
una plantilla (`POST /admin/plantillas/{name}`), el sistema DEBE devolverla al
estado `draft` y borrar su autor y fecha de aprobación.

## R32
El sistema DEBE calcular las plantillas efectivas de los propósitos
`advisor_reply` y `suppression_result` así: si existe al menos una plantilla
registrada de ese propósito, solo las de estado `approved` ordenadas por
nombre; si no existe ninguna, la lista de entorno
(`ADVISOR_WHATSAPP_TEMPLATES` / `SUPPRESSION_RESULT_TEMPLATE`).

## R33
El sistema DEBE calcular las plantillas efectivas del propósito
`expiry_notice` como las registradas en estado `approved` ordenadas por
nombre, sin lista de entorno de respaldo.

## R34
CUANDO un asesor envía una plantilla desde el panel (`advisor_send_template`) o
abre la vista de caso, el sistema DEBE usar como lista de plantillas las
plantillas efectivas de `advisor_reply`.

## R72
SI la plantilla pedida en `advisor_send_template` no es una plantilla efectiva
de `advisor_reply` ENTONCES el sistema DEBE responder `422` sin llamar al
gateway.

## R35
CUANDO la ejecución de una supresión necesita plantilla (WhatsApp con ventana
cerrada), el sistema DEBE usar la primera plantilla efectiva de
`suppression_result`.

## R73
SI la ejecución de una supresión necesita plantilla y no hay ninguna plantilla
efectiva de `suppression_result` ENTONCES el sistema DEBE registrar
`notification_result = "skipped"` sin llamar al gateway.

## Ajustes operativos y horarios (orchestrator)

## R36
CUANDO un administrador solicita `GET /admin/ajustes`, el sistema DEBE mostrar
cada clave del registro de ajustes operativos con su valor efectivo, su valor
por defecto, su origen (`panel` o `entorno`) y su rango o formato permitido.

## R37
CUANDO un administrador envía `POST /admin/ajustes` con valores válidos, el
sistema DEBE guardarlos en `app_settings` en una sola transacción.

## R74
CUANDO `POST /admin/ajustes` trae una clave del registro con valor vacío, el
sistema DEBE eliminar esa clave de `app_settings` para que rija el valor por
defecto de entorno.

## R38
SI `POST /admin/ajustes` trae al menos un valor fuera de tipo o rango, una hora
que no sea `HH:MM`, `business_hours.days` vacío/con valores fuera de 1–7/con
duplicados, `business_hours.start == business_hours.end` o
`suppression.due_soon_business_days >= suppression.deadline_business_days`
efectivo resultante ENTONCES el sistema DEBE responder `422` sin guardar
ninguna clave.

## R39
SI `app_settings` contiene para una clave del registro un valor inválido
ENTONCES el sistema DEBE usar el valor por defecto de entorno y registrar un
`warning` con el nombre de la clave sin el valor.

## R40
CUANDO cambia el valor efectivo de un ajuste operativo, la siguiente operación
que lo use (renovación, estado de credencial, aviso, cola de supresión,
traspaso fuera de horario) DEBE aplicar el valor nuevo sin reiniciar el
proceso.

## R41
El sistema DEBE calcular «dentro de horario» con una función pura
`within_business_hours(now, hours)` según la definición del vocabulario,
incluido el rango que cruza medianoche.

## R42
MIENTRAS `business_hours.enabled` es verdadero y `now` está fuera de horario,
CUANDO un traspaso obtiene de handover el estado `notified` en un caso en el
que hoy se enviaría `HANDOVER_ACK_REPLY`, el sistema DEBE enviar
`out_of_hours_reply` (o `HANDOVER_ACK_REPLY` si está vacío) en su lugar y
registrar el evento `out_of_hours` con motivo `queued`, manteniendo la
creación del caso.

## R43
MIENTRAS `business_hours.enabled` es falso o `now` está dentro de horario, el
sistema DEBE conservar el acuse de traspaso actual sin cambios.

## R44
CUANDO un administrador guarda ajustes, textos, plantillas, ejecuta una
acción sobre un cliente o consulta las métricas, el sistema DEBE registrar una
fila en `panel_audit` con la acción (`settings_update`, `texts_update`,
`template_create`, `template_update`, `template_status`, `client_create`,
`client_renew`, `client_revoke`, `client_close_session`, `metrics_viewed`), el
destino (clave, campo, nombre de
plantilla o `profile_id`) y el resultado, sin contraseñas ni valores de textos.

## Aviso de vencimiento (orchestrator + contracts + scripts)

## R45
CUANDO el orquestador recibe `POST /credentials/expiry-notices` con
`X-Service-Token` válido y cuerpo `{}`, el sistema DEBE ejecutar una pasada de
avisos y responder `200` con `ExpiryNoticeRunResponse` (`enabled`,
`candidates`, `sent_text`, `sent_template`, `failed`, `skipped` por motivo).

## R46
El sistema DEBE considerar en cada pasada solo las credenciales candidatas a
aviso según `identity.expiry_notice_days` efectivo.

## R47
MIENTRAS `expiry_notice.enabled` es falso, la pasada NO DEBE enviar avisos ni
escribir en `credential_expiry_notices` y DEBE responder `enabled = false`.

## R48
MIENTRAS `business_hours.enabled` es verdadero y `now` está fuera de horario,
la pasada NO DEBE enviar ni reclamar avisos y DEBE contar las candidatas en
`skipped.out_of_hours`.

## R49
SI una candidata no tiene último chat o su contacto ya no existe ENTONCES la
pasada DEBE contarla en `skipped.no_chat` sin enviar ni escribir en
`credential_expiry_notices`.

## R50
CUANDO el último chat es Telegram o WhatsApp con ventana abierta
(`channel_window` de #41), el sistema DEBE enviar un `TextBlock` con
`expiry_notice` reemplazando `{dias}` por los días restantes y `{fecha}` por la
fecha local de vencimiento.

## R51
CUANDO el último chat es WhatsApp con la ventana cerrada, el sistema DEBE
enviar solo un `TemplateBlock` con la primera plantilla efectiva de
`expiry_notice` y `variables = [días restantes, fecha local]`, sin texto libre.

## R52
SI la rama de texto encuentra `expiry_notice` vacío o la rama de plantilla no
encuentra plantilla efectiva ENTONCES la pasada DEBE contar la candidata en
`skipped.no_text` o `skipped.no_template` sin enviar ni escribir en
`credential_expiry_notices`.

## R53
El sistema DEBE reclamar el periodo de vigencia en `credential_expiry_notices`
con una escritura atómica antes de enviar, y NO DEBE enviar si el periodo ya
tiene estado `sent` o `sending`, o estado `failed` con `attempts >=
EXPIRY_NOTICE_MAX_ATTEMPTS`.

## R54
CUANDO dos pasadas concurrentes procesan el mismo periodo de vigencia, el
sistema DEBE enviar como máximo un aviso.

## R55
CUANDO se ejecutan varias pasadas sobre el mismo periodo de vigencia con un
envío exitoso, el sistema DEBE enviar exactamente un aviso.

## R56
CUANDO un administrador renueva una credencial, el sistema DEBE tratar el nuevo
`valid_until` como un periodo nuevo: el aviso del periodo anterior no impide el
del nuevo y la credencial renovada no recibe aviso mientras no vuelva a ser
candidata.

## R57
CUANDO el envío de un aviso tiene éxito, el sistema DEBE marcar el periodo como
`sent` con el método (`text` o `template`) y registrar el evento
`expiry_notice` en el contacto y la acción `expiry_notice` en
`identity_audit`.

## R58
SI el envío falla (`ServiceUnavailable`, incluida `ChannelRejected`) ENTONCES
el sistema DEBE marcar el periodo como `failed`, incrementar `attempts`, contar
la candidata en `failed` y continuar con las demás candidatas.

## R59
El sistema NO DEBE guardar el aviso en `messages`, cambiar el estado de la
conversación ni actualizar la actividad de la sesión del cliente al enviar un
aviso.

## R60
CUANDO se ejecuta `scripts/avisar_vencimientos.py --intervalo`, el script DEBE
llamar a `POST {ORCHESTRATOR_URL}/credentials/expiry-notices` con
`X-Service-Token` cada `EXPIRY_NOTICE_INTERVAL_SECONDS` segundos, registrar el
resultado sin datos personales y seguir iterando ante errores.

## R61
SI al script le faltan `ORCHESTRATOR_URL` o `SERVICE_TOKEN`, o el intervalo o
el timeout no son números mayores que 0 ENTONCES el script DEBE terminar con
código distinto de 0 sin llamar a la red.

## Métricas (orchestrator, panel admin)

## R62
CUANDO un administrador solicita `GET /admin/metricas?dias=N` con `N` entero
entre 1 y 90 (por defecto 7), el sistema DEBE calcular las métricas de R63–R66
para el intervalo `[now - N días, now)`.

## R63
El sistema DEBE mostrar el tiempo de primera respuesta: casos creados en el
intervalo (`case_links.created_at`), casos con primer mensaje `advisor`
posterior a la creación, promedio y mediana en minutos de esa diferencia y
casos sin respuesta.

## R64
El sistema DEBE mostrar las conversaciones por asesor como el número de
contactos distintos con evento `advisor_reply` en el intervalo por asesor,
etiquetado con el usuario del perfil cuyo `telegram_user_id` coincide o con el
identificador si no hay perfil, en orden descendente.

## R65
El sistema DEBE mostrar los motivos de escalamiento como el conteo de eventos
`handover` del intervalo agrupados por motivo, en orden descendente.

## R66
El sistema DEBE mostrar las preguntas sin respuesta como el total de eventos
`no_results` e `invalid_answer` del intervalo y, para los últimos
`ADMIN_METRICS_UNANSWERED_LIMIT` eventos, el último mensaje `user` del contacto
anterior o igual al evento, truncado a 300 caracteres y escapado con
`html.escape`.

## R67
SI `dias` no es un entero entre 1 y 90 ENTONCES el sistema DEBE responder `422`
sin consultar el repositorio.

## R68
DONDE `ADMIN_METRICS_UNANSWERED_LIMIT` es `0`, el sistema DEBE mostrar solo el
total de preguntas sin respuesta, sin textos de mensajes.

## Configuración, navegación y compatibilidad

## R69
El sistema DEBE leer y validar en `config.py` las variables nuevas de
`design.md` (§Config) con sus rangos, y SI una está fuera de rango ENTONCES el
arranque DEBE fallar con un error de validación.

## R70
CUANDO un administrador abre cualquier página del panel, la navegación DEBE
incluir enlaces a `/admin/clientes`, `/admin/plantillas`, `/admin/ajustes` y
`/admin/metricas`.

## R71
El sistema DEBE mantener verdes las suites existentes de orchestrator,
contracts y scripts con los valores por defecto (`BUSINESS_HOURS_ENABLED=false`,
textos nuevos vacíos, registro de plantillas vacío).
