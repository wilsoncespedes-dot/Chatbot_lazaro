# #21 panel_administracion — Requirements

Servicio: **orchestrator** (único). Rutas bajo `/admin`, HTML renderizado en el
servidor. Reutiliza perfiles, hash y token de vinculación de #20.

**Alcance reducido.** Para que esta feature quede compacta, el criterio 4 del
acceptance (manuales y fragmentos: cargar, listar, editar, activar/desactivar) y
su parte de tests se pasan a la feature nueva **#22 `panel_fragmentos`**. Esa
feature necesita rutas nuevas en el contrato del RAG (listar manuales/fragmentos,
activar/desactivar), y según `docs/architecture.md` §3.2 un cambio de contrato
va en su propia feature. #22 reutilizará la sesión, el control de rol y el CSRF
definidos aquí, más `PATCH /chunks/{id}` de #19.

## R1
CUANDO el orquestador recibe `POST /admin/login` con `username` y `password` de un
perfil con rol `admin` que pasan `verify_password`, el sistema DEBE crear una sesión
con expiración `ADMIN_SESSION_TTL_MINUTES` y responder `303` hacia `/admin` con una
cookie `admin_session` `HttpOnly`, `SameSite=Strict` y `Path=/admin`.

## R2
SI `POST /admin/login` trae un usuario inexistente, una contraseña incorrecta o un
perfil con rol distinto de `admin` ENTONCES el sistema DEBE responder `401` con la
misma página de login y el mismo mensaje en los tres casos, sin crear sesión.

## R3
MIENTRAS una petición a `/admin/*` (salvo `GET`/`POST /admin/login` y
`GET /admin/static/admin.css`, que se sirven sin sesión) no traiga una
cookie de sesión válida (ausente, desconocida, expirada o cerrada con
`POST /admin/logout`), el sistema DEBE responder `303` hacia `/admin/login` sin
ejecutar la operación pedida.

## R4
SI un `POST` a `/admin/*` con sesión válida llega sin el campo `csrf_token` o con
uno distinto al de su sesión ENTONCES el sistema DEBE responder `403` sin ejecutar
la operación pedida.

## R5
El sistema DEBE servir toda respuesta HTML de `/admin` con la cabecera
`Content-Security-Policy: default-src 'self'; form-action 'self'; frame-ancestors 'none'`
y sin ninguna etiqueta `<script>`, `<link>` ni `<img>` que apunte a un origen
externo (`http://`, `https://` o `//`).

## R6
El sistema NO DEBE incluir el valor de `SERVICE_TOKEN`, ninguna contraseña ni
ningún `password_hash` en el cuerpo, las cabeceras ni las cookies de las
respuestas de `/admin`.

## R7
CUANDO un administrador con sesión envía `POST /admin/profiles` con `username`,
`role` y `password` válidos según R1 de #20, el sistema DEBE crear el perfil
mediante `create_profile` y mostrarlo en `GET /admin/profiles` con su `username`,
su `role` y si está vinculado (los datos inválidos o un `username_taken` vuelven
a mostrar el formulario con `422`/`409`, sin crear el perfil).

## R8
CUANDO un administrador con sesión envía `POST /admin/profiles/{id}/role` con un
`role` ∈ {`admin`, `asesor`, `cliente`}, el sistema DEBE cambiar el rol de ese
perfil y redirigir con `303` a `/admin/profiles`, excepto cuando el cambio deje
sin ningún perfil `admin`: entonces el rol queda igual y la página muestra el
error `last_admin`.

## R9
CUANDO un administrador con sesión envía `POST /admin/profiles/{id}/link-token`
para un perfil existente, el sistema DEBE emitir el token con `issue_link_token`
y responder `200` con una página que muestra el enlace y su `expires_at` una sola
vez, con `Cache-Control: no-store`.

## R10
CUANDO un administrador con sesión pide `GET /admin/events`, el sistema DEBE
mostrar los últimos `ADMIN_EVENTS_LIMIT` eventos (más nuevos primero) con
`contact_id` reducido a sus 8 primeros caracteres y, en `reason`, los correos,
las secuencias de 6 o más dígitos y las cadenas URL-safe de 20 o más caracteres
reemplazados por `[redactado]`.

## R11
SI un mismo `username` normalizado, o una misma IP de cliente, acumula
`ADMIN_LOGIN_MAX_ATTEMPTS` logins fallidos (casos de R2) dentro de los últimos
`ADMIN_LOGIN_WINDOW_MINUTES` ENTONCES el sistema DEBE responder `429` a
`POST /admin/login` con la misma página y el mismo mensaje genérico de R2,
**antes** de llamar a `verify_password` y sin crear sesión, hasta que esos fallos
queden fuera de la ventana; y CUANDO un login de ese `username` es correcto, el
sistema DEBE reiniciar el contador de fallos de ese `username`.

## Cobertura del acceptance

| Criterio | Requirements |
|----------|--------------|
| 1. Login y vistas sin CDN externos | R1, R5 |
| 2. Solo admin; la credencial de servicio no llega al navegador | R2, R3, R6 |
| 3. Crear perfiles, cambiar roles, enlace de Telegram | R7, R8, R9 |
| 4. Eventos recientes redactados | R10 |
| 5. Límite persistente y configurable de intentos de login | R11 |
| 6. Tests: sesión, rol, CSRF, límite de intentos, perfiles, redacción | R1–R4, R6–R11 |

(Manuales y fragmentos pasan a #22 `panel_fragmentos`.)

Nota sobre R8: proteger al último `admin` es el default seguro que se eligió para
que el panel no pueda quedarse sin ningún administrador; es parte del mismo cambio
de rol y se prueba en el mismo test.
