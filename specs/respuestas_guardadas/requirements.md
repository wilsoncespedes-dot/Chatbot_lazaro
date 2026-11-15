# #51 respuestas_guardadas — Requirements

Servicio afectado: **orchestrator** (panel HTML sin JS, sesión, CSRF y `panel_audit`).
Gateway, handover y contracts no cambian.

## Administración

## R1
CUANDO un perfil con rol `admin` envía `POST /admin/respuestas` con título y texto válidos, el sistema DEBE crear una respuesta guardada activa y redirigir a `/admin/respuestas`.

## R2
CUANDO un perfil con rol `admin` envía `POST /admin/respuestas/{id}` con título y texto válidos, el sistema DEBE actualizar el título y el texto de esa respuesta.

## R3
CUANDO un perfil con rol `admin` envía `POST /admin/respuestas/{id}/activa` con `active` igual a `0` o `1`, el sistema DEBE desactivar o reactivar esa respuesta sin borrarla.

## R4
CUANDO se crea, edita o cambia el estado de una respuesta guardada, el sistema DEBE aplicar el cambio en la siguiente petición sin redeploy ni reinicio.

## R5
CUANDO se crea, edita o cambia el estado de una respuesta guardada (con éxito o con error), el sistema DEBE registrar en `panel_audit` la acción `saved_reply_created`, `saved_reply_updated` o `saved_reply_active_changed`, con el `id` de la respuesta como `target` y sin copiar título ni texto.

## R6
SI un perfil que no es `admin` (asesor, supervisor, responsable de datos o cliente) llama a cualquier ruta `/admin/respuestas…` ENTONCES el sistema DEBE responder `403` sin modificar datos y auditar el intento.

## R7
SI una petición `POST /admin/respuestas…` llega sin sesión válida o sin token CSRF válido ENTONCES el sistema DEBE rechazarla (redirección a login o `403`) sin modificar datos.

## R8
SI el título o el texto de una respuesta guardada está vacío tras `strip`, supera el máximo configurado o contiene caracteres de control (salvo saltos de línea en el texto) ENTONCES el sistema DEBE responder `422` sin guardar.

## R9
SI el título o el texto de una respuesta guardada contiene un marcador de variable (`{`, `}`, `${`, `%(`) ENTONCES el sistema DEBE responder `422` con el código `saved_reply_variables_not_allowed` sin guardar.

## R10
SI se intenta crear una respuesta guardada y ya existe el máximo configurado ENTONCES el sistema DEBE responder `422` sin guardar.

## R11
SI el `id` de `POST /admin/respuestas/{id}` o de `/activa` no existe ENTONCES el sistema DEBE responder `404` con el código `saved_reply_not_found`.

## R12
CUANDO el administrador abre `GET /admin/respuestas`, el sistema DEBE listar todas las respuestas (activas e inactivas) con título, texto y estado, y la navegación de admin DEBE incluir el enlace "Respuestas guardadas".

## Uso por el asesor

## R13
CUANDO un asesor con permiso sobre el caso abre `GET /asesor/cases/{id}` con la ventana abierta (o en un canal sin ventana), el sistema DEBE mostrar un selector con las respuestas guardadas activas (solo títulos).

## R14
CUANDO el asesor abre `GET /asesor/cases/{id}?respuesta=<saved_id>` con una respuesta activa y la ventana abierta, el sistema DEBE renderizar el texto de esa respuesta dentro del campo de respuesta (`textarea`) para que lo edite, sin enviarlo al cliente.

## R15
El sistema NO DEBE enviar nada al cliente al seleccionar o cargar una respuesta guardada; solo `POST /asesor/reply` con CSRF, enviado por el asesor, entrega el texto contenido en el formulario.

## R16
CUANDO el asesor modifica el texto cargado y envía `POST /asesor/reply`, el sistema DEBE enviar al cliente el texto editado y no el texto original guardado.

## R17
SI `respuesta` apunta a una respuesta desactivada o inexistente ENTONCES el sistema DEBE mostrar el campo de respuesta vacío con un aviso y no cargar texto alguno.

## R18
MIENTRAS el canal es WhatsApp y la ventana de 24 horas está cerrada, el sistema NO DEBE ofrecer el selector de respuestas guardadas ni cargar su texto (aunque se fuerce `?respuesta=`) y DEBE ofrecer solo las plantillas aprobadas.

## R19
CUANDO el asesor envía una respuesta cargada desde una respuesta guardada, el sistema DEBE aplicar las mismas reglas que a cualquier respuesta: autorización por caso con handover, adaptador del canal y verificación de la ventana de WhatsApp.

## R20
SI un asesor sin autorización sobre el caso abre el caso con `?respuesta=` ENTONCES el sistema DEBE negar el acceso con la misma respuesta de error que sin el parámetro y no revelar el texto guardado.

## Seguridad y presentación

## R21
El sistema DEBE escapar HTML en título y texto de las respuestas guardadas en el selector, en el `textarea` y en la página de administración.

## R22
El sistema NO DEBE sustituir ni interpolar datos del cliente (nombre, usuario, id, etc.) en el texto de una respuesta guardada; el texto cargado es idéntico al guardado.

## Configuración y esquema

## R23
El sistema DEBE leer `SAVED_REPLY_TITLE_MAX_CHARS` (por defecto 80, rango 1–200), `SAVED_REPLY_TEXT_MAX_CHARS` (1000, 1–4096) y `SAVED_REPLIES_MAX` (100, 1–500) del entorno, y DEBE fallar al arrancar si el valor está fuera de rango.

## R24
El sistema DEBE crear la tabla `saved_replies` de forma idempotente (`CREATE TABLE IF NOT EXISTS`) y NO DEBE incluirla en la supresión de datos personales ni en la purga de retención, porque no contiene datos del cliente.
