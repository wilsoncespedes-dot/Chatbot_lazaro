# #54 segundo_factor_panel — Requirements

Todo en el servicio **orchestrator** (paneles `/admin` y `/asesor`). El login web
de clientes (`/acceso`, #38) no cambia. «Personal» = perfiles con rol `admin`,
`supervisor`, `asesor` o `responsable_datos`. Cuenta corporativa Google/Microsoft
queda fuera de alcance (supuesto S1 del design).

## TOTP (RFC 6238)

## R1
El sistema DEBE calcular y verificar códigos TOTP conforme a RFC 6238 (HMAC-SHA1, 30 s, 6 dígitos) con los vectores de prueba del Apéndice B del RFC.

## R2
CUANDO se verifica un código TOTP, el sistema DEBE aceptar solo los pasos de tiempo dentro de ±`PANEL_2FA_WINDOW_STEPS` (por defecto 1) del reloj del servidor.

## R3
SI un código TOTP corresponde a un paso fuera de la ventana configurada ENTONCES el sistema DEBE rechazarlo.

## R4
SI un código no tiene exactamente 6 dígitos ASCII ENTONCES el sistema DEBE rechazarlo sin lanzar excepción.

## Registro del segundo factor

## R5
CUANDO un perfil de personal con sesión pide iniciar el registro (`POST /admin/2fa/start` o `POST /asesor/2fa/start`) con CSRF válido, el sistema DEBE generar un secreto nuevo de 160 bits, guardarlo cifrado como pendiente y mostrar una sola vez el secreto en base32 y la URI `otpauth://totp/` con el emisor `PANEL_2FA_ISSUER`.

## R6
CUANDO el perfil envía un código TOTP válido contra su secreto pendiente (`POST …/2fa/confirm`), el sistema DEBE activar el segundo factor, generar los códigos de recuperación y mostrarlos una sola vez.

## R7
SI el código de confirmación es inválido ENTONCES el sistema DEBE dejar el segundo factor sin activar y mantener el secreto pendiente.

## R8
SI un perfil con el segundo factor ya activo pide iniciar el registro ENTONCES el sistema DEBE responder `409` con código `two_factor_already_enabled` sin cambiar su secreto.

## R9
SI un perfil con rol `cliente` o sin sesión pide cualquier ruta `…/2fa` ENTONCES el sistema DEBE negarla (redirigir al login o `403`) sin crear secreto.

## Inicio de sesión

## R10
MIENTRAS un perfil tiene el segundo factor activo, el sistema DEBE exigir en `POST /admin/login` y `POST /asesor/login` la contraseña y un código TOTP válido (o de recuperación) para crear la sesión.

## R11
SI un perfil con segundo factor activo envía la contraseña correcta sin código ENTONCES el sistema DEBE responder `401` con `two_factor_required` sin crear sesión y sin contar un intento fallido.

## R12
SI un perfil con segundo factor activo envía la contraseña correcta con un código incorrecto ENTONCES el sistema DEBE responder `401`, no crear sesión y registrar un intento fallido en `admin_login_attempts` con el mismo usuario e IP que las contraseñas erróneas.

## R13
CUANDO el número de intentos fallidos (contraseña o código) de un usuario o IP alcanza `ADMIN_LOGIN_MAX_ATTEMPTS` dentro de `ADMIN_LOGIN_WINDOW_MINUTES`, el sistema DEBE responder `429` aunque la contraseña y el código sean correctos.

## R14
CUANDO el código es válido, el sistema DEBE crear una sesión normal y limpiar los intentos fallidos del usuario.

## R15
SI el usuario no existe o la contraseña es incorrecta ENTONCES el sistema DEBE responder lo mismo (`401`, mismo mensaje) con y sin segundo factor activo en el perfil.

## R16
SI falta o es inválida la clave `PANEL_2FA_ENCRYPTION_KEY` y el perfil tiene segundo factor activo ENTONCES el sistema DEBE denegar el inicio de sesión sin crear sesión.

## Anti-replay

## R17
SI un código TOTP ya se aceptó para un perfil (mismo paso de tiempo) ENTONCES el sistema DEBE rechazarlo en cualquier intento posterior, también en otro panel.

## R18
SI un código corresponde a un paso de tiempo menor o igual al último paso aceptado del perfil ENTONCES el sistema DEBE rechazarlo.

## R19
CUANDO dos verificaciones concurrentes presentan el mismo código, el sistema DEBE aceptar como máximo una (actualización atómica condicionada del último paso).

## R20
CUANDO se confirma el registro, el sistema DEBE guardar como último paso usado el del código de confirmación para que no sirva de inmediato en el login.

## Obligatoriedad

## R21
DONDE `PANEL_2FA_REQUIRED` no está definido, el sistema DEBE tratarlo como `true` si `APP_ENV=production` y como `false` en los demás entornos.

## R22
DONDE `PANEL_2FA_REQUIRED` está definido, el sistema DEBE respetar su valor en cualquier entorno.

## R23
MIENTRAS el segundo factor es obligatorio y el perfil no lo tiene activo, el sistema DEBE crear tras la contraseña correcta una sesión restringida que solo permita las rutas `…/2fa`, el cierre de sesión y el CSS.

## R24
SI una sesión restringida a registro accede a cualquier otra ruta protegida de `/admin`, `/asesor` o al websocket del panel ENTONCES el sistema DEBE tratarla como no autenticada (redirigir al login o cerrar la conexión).

## R25
CUANDO se confirma el registro, el sistema DEBE borrar todas las demás sesiones del perfil conservando solo la sesión que confirmó, tanto si esta era restringida (que además se convierte en sesión normal) como si era una sesión normal.

## R26
MIENTRAS el segundo factor no es obligatorio y el perfil no lo tiene activo, el sistema DEBE permitir el login solo con contraseña.

## Secreto cifrado y confidencialidad

## R27
El sistema DEBE guardar el secreto TOTP únicamente cifrado con Fernet usando `PANEL_2FA_ENCRYPTION_KEY`; la base de datos NO DEBE contener el secreto en claro ni en base32.

## R28
CUANDO ya se mostró el secreto en el registro, el sistema NO DEBE incluirlo en ninguna respuesta posterior, log, fila de `panel_audit` ni evento de `panel_events`.

## R29
El sistema NO DEBE registrar en logs ni en auditoría códigos TOTP, códigos de recuperación ni la URI `otpauth`.

## R30
El sistema DEBE servir las páginas que muestran secreto o códigos de recuperación con `Cache-Control: no-store`.

## Códigos de recuperación

## R31
CUANDO se activa el segundo factor, el sistema DEBE generar `PANEL_2FA_RECOVERY_CODES` códigos (por defecto 8) de 80 bits aleatorios con formato `xxxx-xxxx-xxxx-xxxx` y guardar solo su hash SHA-256.

## R32
CUANDO el login recibe un código de recuperación válido y no usado, el sistema DEBE crear la sesión, marcar el código como usado en una operación atómica y registrar la acción `two_factor_recovery_used` en la auditoría del panel.

## R33
SI un código de recuperación ya se usó ENTONCES el sistema DEBE rechazarlo y contarlo como intento fallido.

## R34
CUANDO se compara un código de recuperación, el sistema DEBE ignorar mayúsculas, espacios y guiones.

## Restablecimiento por administrador

## R35
CUANDO un administrador con sesión y CSRF válido envía `POST /admin/profiles/{id}/2fa/reset` para otro perfil con segundo factor, el sistema DEBE borrar su secreto y sus códigos de recuperación, cerrar todas sus sesiones y registrar `two_factor_reset` con el perfil objetivo en la auditoría.

## R36
SI el objetivo del restablecimiento es el propio administrador ENTONCES el sistema DEBE rechazarlo con `400` sin cambios.

## R37
SI el perfil objetivo no existe o no tiene segundo factor ENTONCES el sistema DEBE responder `404` o `409` (`two_factor_not_enabled`) sin cambios.

## R38
SI la petición de restablecimiento no es de un administrador o no trae CSRF válido ENTONCES el sistema DEBE responder `403` sin cambios y auditar `forbidden` cuando se identifica al actor.

## R39
CUANDO un perfil restablecido inicia sesión, el sistema DEBE tratarlo como sin segundo factor (registro obligatorio si `PANEL_2FA_REQUIRED` lo exige).

## Seguridad web y configuración

## R40
El sistema DEBE exigir CSRF en `…/2fa/start`, `…/2fa/confirm` y en el restablecimiento, y escapar todo valor mostrado en las páginas de segundo factor.

## R41
SI `APP_ENV=production` y `PANEL_2FA_ENCRYPTION_KEY` falta o no es una clave Fernet válida (32 bytes en base64 urlsafe) ENTONCES el sistema DEBE abortar el arranque con `ProductionConfigError` que nombre `PANEL_2FA_ENCRYPTION_KEY` sin imprimir su valor.

## R42
DONDE `APP_ENV=production` con clave válida, el sistema DEBE arrancar con `PANEL_2FA_REQUIRED` efectivo `true` si la variable no está definida.

## R43
SI `PANEL_2FA_WINDOW_STEPS` está fuera de 0–2 o `PANEL_2FA_RECOVERY_CODES` fuera de 4–20 o `PANEL_2FA_ISSUER` está vacío o supera 64 caracteres ENTONCES el sistema DEBE rechazar la configuración.

## R44
El sistema DEBE listar `PANEL_2FA_REQUIRED`, `PANEL_2FA_ENCRYPTION_KEY`, `PANEL_2FA_ISSUER`, `PANEL_2FA_WINDOW_STEPS` y `PANEL_2FA_RECOVERY_CODES` en `.env.example`, `render.yaml` y `docs/despliegue.md` sin valores secretos.

## R45
El sistema NO DEBE alterar el login de clientes (`/acceso`) ni exigir segundo factor a perfiles `cliente`.

## Recuperación operativa (administrador único / pérdida de clave)

## R46
El sistema DEBE documentar en `docs/despliegue.md` un procedimiento SQL de recuperación que exija acceso operativo a la base de datos, apunte explícitamente a un perfil (`profiles.id`) y, en una sola transacción, registre una fila en `panel_audit` con `actor_profile_id` no nulo de la forma `ops:<operador>` y `action='two_factor_reset_ops'`, y borre las filas del perfil en `staff_recovery_codes`, `staff_two_factor` y `admin_sessions`.

## R47
El procedimiento de recuperación DEBE indicar que sirve para un administrador único que perdió su factor y sus códigos, y DEBE incluir la variante para todos los perfiles con segundo factor cuando se pierde o cambia `PANEL_2FA_ENCRYPTION_KEY`, indicando que esa clave no se rota sin ejecutarla.

## R48
El procedimiento de recuperación NO DEBE seleccionar, mostrar ni pedir `secret_ciphertext`, códigos de recuperación, hashes ni la clave `PANEL_2FA_ENCRYPTION_KEY`, y DEBE indicar que tras ejecutarlo el perfil inicia sesión sin segundo factor (R39).
