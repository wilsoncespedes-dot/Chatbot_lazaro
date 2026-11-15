# #50 notas_internas_y_etiquetas — Requirements

Servicio: **orchestrator** (panel de asesores y administración). Handover,
gateway, contratos y RAG no cambian. "Personal con permiso sobre el caso" =
quien pasa `handover.authorize(case_id, profile_id, "reply")` (misma barrera que
la memoria del cliente en #41/#43). Los valores numéricos son configurables
(ver `design.md`).

## Notas internas

## R1
CUANDO un asesor con permiso sobre un caso envía `POST /asesor/cases/{case_id}/notes` con sesión y CSRF válidos y un texto válido, el sistema DEBE guardar una nota con autor, fecha y caso, y redirigir a la vista del caso.

## R2
CUANDO el sistema renderiza la vista de conversación de un caso, el sistema DEBE mostrar las notas del caso en una sección propia, separada del historial de mensajes, con autor (nombre de usuario) y fecha de cada nota.

## R3
SI un perfil sin permiso sobre el caso solicita ver, añadir o borrar una nota de ese caso ENTONCES el sistema DEBE rechazar con el mismo error de autorización que usa la vista de caso (403 o 404) sin leer ni modificar notas.

## R4
SI el asesor A tiene permiso sobre el caso X y no sobre el caso Y ENTONCES el sistema NO DEBE mostrar a A las notas de Y ni permitir que las modifique.

## R5
SI el texto de una nota queda vacío tras `strip()` o supera `CASE_NOTE_MAX_CHARS` ENTONCES el sistema DEBE responder 422 `validation_error` sin guardar nada.

## R6
SI un caso ya tiene `CASE_NOTES_MAX_PER_CASE` notas ENTONCES el sistema DEBE responder 422 `validation_error` al añadir otra, sin guardarla.

## R7
CUANDO el autor de una nota envía `POST /asesor/cases/{case_id}/notes/{note_id}/delete` con permiso sobre el caso, sesión y CSRF válidos, el sistema DEBE borrar esa nota.

## R8
SI quien intenta borrar una nota no es su autor ENTONCES el sistema DEBE rechazar con 403 `forbidden` sin borrarla.

## R9
SI la nota indicada no existe o pertenece a otro caso que el de la ruta ENTONCES el sistema DEBE responder 404 sin modificar nada.

## Aislamiento de las notas (seguridad)

## R10
El sistema DEBE guardar las notas internas fuera de la tabla `messages` y de cualquier estructura que alimente el historial del cliente, la memoria, los resúmenes o los prompts.

## R11
CUANDO un asesor añade una nota, el sistema NO DEBE invocar ningún adaptador de canal (gateway Telegram o WhatsApp) ni el cliente de handover con el texto de la nota.

## R12
MIENTRAS existen notas en un caso, el sistema NO DEBE incluir su texto en el contexto enviado a la IA, en la generación del resumen ni en la memoria permanente del cliente en ninguna interacción posterior.

## R13
MIENTRAS existen notas en un caso, el sistema NO DEBE incluir su texto en el historial `case_messages`, en el mensaje de respuesta del asesor al cliente (texto o plantilla) ni en eventos o filas de auditoría.

## Etiquetas

## R14
CUANDO un administrador autenticado envía `POST /admin/etiquetas` con CSRF válido y un nombre válido, el sistema DEBE crear una etiqueta activa.

## R15
CUANDO un administrador envía `POST /admin/etiquetas/{tag_id}` con un nombre válido, el sistema DEBE renombrar la etiqueta conservando su identificador y sus asignaciones.

## R16
CUANDO un administrador envía `POST /admin/etiquetas/{tag_id}/activa` con `active=0` (o `active=1`), el sistema DEBE desactivar (o reactivar) la etiqueta sin borrar sus asignaciones.

## R17
SI el nombre de etiqueta está vacío tras `strip()`, contiene caracteres de control o supera `CASE_TAG_NAME_MAX_CHARS` ENTONCES el sistema DEBE responder 422 sin crear ni renombrar.

## R18
SI el nombre coincide, sin distinguir mayúsculas, con otra etiqueta existente ENTONCES el sistema DEBE responder 409 `tag_name_taken` sin crear ni renombrar.

## R19
SI una cuenta que no es `admin` solicita crear, renombrar o desactivar etiquetas ENTONCES el sistema DEBE rechazar con 401/403 sin modificar etiquetas.

## R20
CUANDO un asesor con permiso sobre un caso envía `POST /asesor/cases/{case_id}/tags` con una etiqueta activa, sesión y CSRF válidos, el sistema DEBE asignar la etiqueta al caso (idempotente si ya la tiene).

## R21
CUANDO un asesor con permiso sobre un caso envía `POST /asesor/cases/{case_id}/tags/{tag_id}/remove`, el sistema DEBE quitar la etiqueta del caso, también si la etiqueta está desactivada.

## R22
SI la etiqueta a asignar está desactivada o no existe ENTONCES el sistema DEBE responder 422 `validation_error` sin asignarla.

## R23
SI el caso ya tiene `CASE_TAGS_MAX_PER_CASE` etiquetas ENTONCES el sistema DEBE responder 422 al asignar otra, sin asignarla.

## R24
SI un perfil sin permiso sobre el caso intenta asignar o quitar etiquetas ENTONCES el sistema DEBE rechazar con el error de autorización del caso sin modificar asignaciones.

## R25
CUANDO el sistema renderiza la vista del caso, el sistema DEBE mostrar las etiquetas asignadas (las desactivadas marcadas como tales) y, para asignar, solo las etiquetas activas aún no asignadas.

## Filtro en la bandeja

## R26
CUANDO `GET /asesor/cases` o `GET /asesor/todos` recibe `tag=<tag_id>` con una etiqueta activa, el sistema DEBE listar solo los casos que ya cumplen el resto de filtros (canal, asignación) y tienen esa etiqueta.

## R27
SI `tag` no es un identificador válido, no existe o está desactivada ENTONCES el sistema DEBE responder 422 `validation_error` antes de consultar los casos.

## R28
CUANDO el sistema renderiza una fila de la bandeja, el sistema DEBE mostrar las etiquetas activas del caso y el selector de etiqueta DEBE ofrecer solo etiquetas activas, conservando el filtro elegido.

## Seguridad web y auditoría

## R29
El sistema DEBE escapar HTML en el texto de notas, autores y nombres de etiqueta al renderizarlos.

## R30
SI una petición de notas o etiquetas llega sin sesión válida ENTONCES el sistema DEBE rechazarla (redirección a login o 401) sin leer ni modificar datos.

## R31
SI una petición `POST` de notas o etiquetas llega sin token CSRF válido ENTONCES el sistema DEBE responder 403 sin modificar datos.

## R32
CUANDO se crea o borra una nota, el sistema DEBE registrar en `panel_audit` las acciones `note_added` / `note_deleted` con actor, rol, `case_id`, resultado y `target` igual al id de la nota, sin copiar el texto de la nota.

## R33
CUANDO se crea, renombra, desactiva, reactiva, asigna o quita una etiqueta, el sistema DEBE registrar en `panel_audit` las acciones `tag_created`, `tag_renamed`, `tag_active_changed`, `tag_assigned` o `tag_removed` con `target` igual al id de la etiqueta y, si aplica, `case_id`.

## R34
SI una operación de notas o etiquetas falla por validación o autorización ENTONCES el sistema DEBE auditarla con el código del error como resultado.

## Supresión y retención

## R35
CUANDO una persona ejecuta una solicitud de supresión, el sistema DEBE borrar las notas internas de todos los casos vinculados a los contactos de las sesiones del cliente, en la misma transacción que el resto del borrado, y reportarlas en el conteo `removed_counts` como `case_notes`.

## R36
CUANDO se ejecuta la supresión, el sistema DEBE borrar las asignaciones de etiquetas de esos casos y conservar la definición de las etiquetas.

## R37
CUANDO se ejecuta la purga automática de retención, el sistema DEBE borrar las notas con `created_at` anterior al corte y las notas y asignaciones de etiquetas de los casos cuyo vínculo se borra por contacto inactivo, e incluir `case_notes` en el conteo `deleted`.

## R38
CUANDO se rechaza el aviso de privacidad y se borra el contenido del contacto, el sistema DEBE borrar sus notas y asignaciones de etiquetas.

## Esquema y configuración

## R39
El sistema DEBE crear las tablas `case_notes`, `case_tags` y `case_tag_assignments` de forma idempotente al arrancar el repositorio.

## R40
El sistema DEBE leer `CASE_NOTE_MAX_CHARS` (1–4000), `CASE_NOTES_MAX_PER_CASE` (1–500), `CASE_TAG_NAME_MAX_CHARS` (1–100) y `CASE_TAGS_MAX_PER_CASE` (1–50) desde el entorno con validación de rango y defaults, y rechazar el arranque con valores fuera de rango.
