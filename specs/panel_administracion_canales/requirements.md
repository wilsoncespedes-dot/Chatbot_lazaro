# Requirements — #66 `panel_administracion_canales`

Servicios: **contracts**, **gateway** (`services/telegram_gateway`) y
**orchestrator** (`services/orchestrator`, panel `/admin`). EARS según
`docs/specs.md`. El orquestador nunca lee `canales`: todo pasa por las rutas
`/channels…` del gateway (#61) con `X-Service-Token`.

## A. Contrato y gateway

## R1 (contracts)
El sistema DEBE incluir en `ChannelInfo` el campo `credential_hints`, un objeto
`nombre → pista` con valor por defecto `{}`, donde cada pista es `…` seguido de
los últimos 4 caracteres de la credencial si mide 8 o más, o solo `…` si mide menos.

## R2 (contracts)
El sistema DEBE exportar `CHANNEL_ICONS`, una lista cerrada `id → emoji` que
incluye al menos `chat`, `telegram` y `whatsapp`.

## R3 (gateway)
CUANDO se crea un canal o se reemplazan sus credenciales, el sistema DEBE
guardar las pistas de R1 junto al registro, nunca el valor completo.

## R4 (gateway)
CUANDO se reemplazan las credenciales con `{}`, el sistema DEBE dejar
`credential_hints` vacío.

## R5 (gateway)
El sistema DEBE aceptar la clave `consent_mode` en `config` del adaptador
`simulado` además de `capabilities`.

## R6 (contracts)
El sistema DEBE documentar `credential_hints` y `CHANNEL_ICONS` en
`contracts/CONTRATOS.md`.

## B. Acceso al panel

## R7 (orchestrator)
CUANDO una petición a `/admin/canales` o sus subrutas no trae sesión de `admin`,
el sistema DEBE redirigir al login sin llamar al gateway.

## R8 (orchestrator)
CUANDO un formulario POST de `/admin/canales…` trae un token CSRF ausente o
incorrecto, el sistema DEBE responder `403` sin llamar al gateway.

## R9 (orchestrator)
El sistema DEBE mostrar «Canales» en la navegación administrativa.

## C. Listar, crear y editar

## R10 (orchestrator)
CUANDO el admin abre `/admin/canales`, el sistema DEBE listar los canales de
`GET /channels` con nombre, id, tipo de adaptador, ícono, color, estado activo,
modo de consentimiento y pistas de credenciales.

## R11 (orchestrator)
El sistema DEBE ofrecer como tipo de adaptador para crear solo los
`adapter_types` que devuelve `GET /channels`.

## R12 (orchestrator)
CUANDO el admin envía el alta con datos válidos, el sistema DEBE llamar a
`POST /channels` con id, nombre, tipo, ícono, color, `config` (con
`consent_mode` y, si se informó, `callback_url`) y credenciales, y mostrar el
secreto del canal nuevo una sola vez con botón copiar.

## R13 (orchestrator)
CUANDO el admin edita un canal, el sistema DEBE llamar a `PATCH /channels/{id}`
con nombre, ícono, color y `config`; las credenciales solo se envían si el
campo de credenciales no está vacío.

## R14 (orchestrator)
CUANDO se edita un canal gestionado por el entorno, el sistema NO DEBE ofrecer
ni enviar credenciales, secreto ni URL de webhook.

## R15 (orchestrator)
SI el ícono no está en `CHANNEL_ICONS` ENTONCES el sistema DEBE responder `422`
con el formulario y un mensaje, sin llamar al gateway.

## R16 (orchestrator)
SI el color no es `#RRGGBB` o su contraste con texto blanco es menor que 4.5:1
ENTONCES el sistema DEBE responder `422` sin llamar al gateway.

## R17 (orchestrator)
SI las credenciales no tienen el formato `nombre=valor` por línea con nombres
`^[a-z][a-z0-9_]{0,63}$` ENTONCES el sistema DEBE responder `422` sin llamar al
gateway.

## R18 (orchestrator)
CUANDO el gateway rechaza una operación con `409` o `422`, el sistema DEBE
mostrar el formulario con el código del error y el mismo estado HTTP.

## R19 (orchestrator)
CUANDO el gateway no responde o responde `5xx`, el sistema DEBE responder `502`
`upstream_error`.

## D. Webhook y secreto

## R20 (orchestrator)
El sistema DEBE mostrar para cada canal no gestionado por el entorno la URL
`<GATEWAY_PUBLIC_BASE_URL>/webhooks/{id}` con un botón copiar; si la base no
está configurada, la ruta relativa `/webhooks/{id}` con un aviso.

## R21 (orchestrator)
El sistema NO DEBE incluir el secreto del canal en el listado ni en la edición.

## R22 (orchestrator)
CUANDO el admin pulsa «Ver secreto» (POST con CSRF), el sistema DEBE obtener el
secreto de `GET /channels/{id}/secret`, mostrarlo con botón copiar y registrar
la auditoría `channel_secret_reveal`.

## R23 (orchestrator)
CUANDO el admin pulsa «Regenerar secreto» (POST con CSRF y confirmación), el
sistema DEBE llamar a `POST /channels/{id}/secret`, mostrar el secreto nuevo y
registrar la auditoría `channel_secret_regenerate`.

## R24 (orchestrator)
El sistema NO DEBE escribir el secreto ni las credenciales en la auditoría ni en
los logs.

## R25 (orchestrator)
Las respuestas que muestran un secreto DEBEN llevar `Cache-Control: no-store`.

## E. Activar y desactivar

## R26 (orchestrator)
CUANDO el admin activa o desactiva un canal, el sistema DEBE llamar a
`PATCH /channels/{id}/active` y registrar la auditoría `channel_active`.

## R27 (gateway)
MIENTRAS un canal está inactivo, el sistema DEBE responder `404` en
`POST /webhooks/{id}` y rechazar `/send` hacia ese canal.

## R28 (orchestrator)
MIENTRAS un canal está inactivo, el sistema DEBE seguir mostrando sus
conversaciones en la bandeja del panel de asesores.

## R29 (orchestrator)
CUANDO una operación del panel cambia un canal, el sistema DEBE invalidar la
copia del directorio de canales del orquestador.

## F. Presentación

## R30 (orchestrator)
El sistema DEBE servir el script del botón copiar desde el mismo origen
(`/admin/static/canales.js`), sin CDN, sin scripts inline y sin cambiar la CSP.

## R31 (orchestrator)
El sistema DEBE mostrar el ícono como su emoji de `CHANNEL_ICONS` sobre el color
del canal con texto blanco.

## R32 (orchestrator)
El sistema DEBE registrar auditoría `channel_create`, `channel_update` y
`channel_active` con el id del canal como objetivo y el resultado.
