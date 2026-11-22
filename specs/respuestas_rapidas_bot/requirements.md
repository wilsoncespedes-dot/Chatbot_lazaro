# Requirements — #71 respuestas_rapidas_bot

Servicio: **orchestrator** (todo). El gateway no cambia: su degradación existente de bloques
(`degrade_blocks`) queda como respaldo. Las respuestas guardadas de asesores (#51, tabla
`saved_replies`) no se tocan.

## Modelo y administración

## R1
El sistema DEBE persistir las respuestas rápidas en la tabla `quick_replies` con id, nombre, disparadores, bloques de respuesta, `active`, `priority`, `created_at` y `updated_at`.

## R2
CUANDO un administrador autenticado envía el formulario de alta de `/admin/respuestas-rapidas` con datos válidos, el sistema DEBE crear la respuesta rápida y redirigir a la lista.

## R3
CUANDO un administrador autenticado envía el formulario de edición de una respuesta rápida existente con datos válidos, el sistema DEBE actualizar sus disparadores, bloques y prioridad.

## R4
CUANDO un administrador autenticado cambia el estado activa/inactiva de una respuesta rápida, el sistema DEBE guardar el nuevo valor de `active`.

## R5
SI el formulario de una respuesta rápida no tiene al menos un disparador válido, o no tiene al menos un bloque, ENTONCES el sistema DEBE responder `422` con el código `quick_reply_invalid` sin guardar nada.

## R6
SI un disparador normalizado tiene menos de 2 caracteres, más de 80, o la respuesta supera 20 disparadores, ENTONCES el sistema DEBE responder `422` con `quick_reply_invalid`.

## R7
SI el enlace de una respuesta rápida no empieza por `https://`, ENTONCES el sistema DEBE responder `422` con `quick_reply_invalid`.

## R8
SI la prioridad no es un entero entre 0 y 1000, ENTONCES el sistema DEBE responder `422` con `quick_reply_invalid`.

## R9
SI el usuario autenticado no tiene rol `admin` al pedir o modificar respuestas rápidas, ENTONCES el sistema DEBE responder `403` con `forbidden` y registrar la auditoría.

## R10
SI una petición a `/admin/respuestas-rapidas` no trae sesión válida, ENTONCES el sistema DEBE redirigir al inicio de sesión.

## R11
SI un POST de `/admin/respuestas-rapidas` no trae un token CSRF válido, ENTONCES el sistema DEBE rechazarlo con `403` sin modificar datos.

## R12
CUANDO una operación de administración de respuestas rápidas termina, el sistema DEBE registrar una entrada de auditoría del panel con la acción y su resultado.

## Coincidencia y prioridad (puro)

## R13
CUANDO se evalúa un texto, el sistema DEBE comparar texto y disparadores normalizados (minúsculas, sin tildes, sin puntuación, espacios colapsados) por coincidencia de palabras completas.

## R14
CUANDO varias respuestas activas coinciden con el texto, el sistema DEBE elegir la de mayor `priority`, y en empate la más antigua por `created_at` y luego por id.

## R15
El sistema NO DEBE considerar las respuestas con `active=false` al evaluar un texto.

## R16
SI ninguna respuesta activa coincide ENTONCES el sistema DEBE continuar el flujo normal sin enviar nada.

## Flujo del mensaje

## R17
MIENTRAS la conversación está en estado `active`, el sistema DEBE evaluar las respuestas rápidas después de los guardarraíles, supresión, traspaso y frustración, y antes del router y del RAG.

## R18
MIENTRAS la conversación está en `new`, `awaiting_consent`, `closed`, `awaiting_login`, `with_advisor` o `no_access`, el sistema NO DEBE evaluar respuestas rápidas.

## R19
CUANDO una respuesta rápida coincide, el sistema DEBE enviar sus bloques por el canal del contacto sin llamar al LLM, al RAG ni a SQL.

## R20
CUANDO una respuesta rápida coincide, el sistema DEBE registrar el evento `quick_reply` con el id de la respuesta como motivo.

## R21
CUANDO una respuesta rápida coincide, el sistema DEBE guardar el mensaje del bot en el historial con el texto de su primer bloque de texto, o el nombre de la respuesta si no hay bloque de texto.

## R22
CUANDO una respuesta rápida coincide tras una detección nueva de intención de compra, el sistema DEBE aplicar igualmente la creación opcional de caso de #70.

## R23
SI la lectura o el envío de una respuesta rápida falla ENTONCES el sistema DEBE registrar el error sin datos del cliente y continuar con el flujo normal (router/RAG).

## Imagen

## R24
CUANDO el administrador sube un archivo de imagen, el sistema DEBE aceptarlo solo si su contenido (firma binaria) es PNG, JPEG o WebP y su tamaño no supera `QUICK_REPLY_IMAGE_MAX_BYTES`.

## R25
SI el archivo subido no es PNG, JPEG ni WebP, o excede el tamaño máximo, o está vacío, ENTONCES el sistema DEBE responder `422` con `quick_reply_image_invalid` sin guardar nada, sin fiarse del nombre ni del `Content-Type` declarados.

## R26
CUANDO se guarda una imagen subida, el sistema DEBE servirla en `GET /media/respuestas/{id}` con el tipo detectado, `X-Content-Type-Options: nosniff` y sin autenticación, desde el mismo origen que el orquestador.

## R27
SI el id de `GET /media/respuestas/{id}` no existe o no tiene el formato esperado ENTONCES el sistema DEBE responder `404`.

## R28
DONDE se indica una URL de imagen en vez de un archivo, el sistema DEBE aceptarla solo si empieza por `https://` y rechazar con `422 quick_reply_image_invalid` en otro caso.

## R29
SI se envían a la vez archivo y URL de imagen, ENTONCES el sistema DEBE responder `422` con `quick_reply_image_invalid`.

## R30
SI se sube un archivo y `IDENTITY_PUBLIC_BASE_URL` no es una URL `https://`, ENTONCES el sistema DEBE responder `422` con `quick_reply_image_invalid`.

## R31
CUANDO se reemplaza o elimina la imagen subida de una respuesta, el sistema DEBE borrar el archivo anterior.

## R32
DONDE el canal del contacto informa `supports_images=true`, el sistema DEBE enviar la imagen como bloque `image` con URL absoluta https.

## R33
DONDE el canal del contacto no informa `supports_images=true` o no está en el directorio, el sistema DEBE enviar la imagen como bloque `link` con el texto alternativo como etiqueta.

## R34
SI la respuesta ya incluye un bloque `link` y el canal no admite imágenes ENTONCES el sistema DEBE enviar la imagen degradada como bloque de texto `"<alt>: <url>"`.

## R35
SI no se puede construir la URL absoluta de una imagen subida en el envío ENTONCES el sistema DEBE omitir ese bloque y enviar el resto.

## Sin contenido en código

## R36
El sistema NO DEBE incluir en el código ni sembrar en la base ninguna respuesta rápida: `quick_replies` arranca vacía.

## Verificación (mapa orientativo de pruebas)

- R13–R16: pruebas de `quick_replies.py` puro. R2–R12: rutas admin con repositorio fake.
- R17–R23: pruebas de flujo con LLM/RAG fakes que fallan si se llaman.
- R24–R31: pruebas de `validate_image`, subida y ruta de media. R32–R35: pruebas de construcción de bloques.
- R36: prueba que verifica repositorio vacío tras `init_schema` y ausencia de datos sembrados.
