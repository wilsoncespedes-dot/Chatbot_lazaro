# #25 clasificador_consultas — Requirements

Servicio: **orchestrator** (panel `/admin` de #21/#22 y `process_message`).
Sin rutas de contrato nuevas ni cambios en RAG, handover o gateway. El
clasificador es local y determinista (palabras clave por categoría); no usa LLM.

Definiciones usadas abajo:

- **Categoría**: `code` (`^[a-z][a-z0-9_]{0,15}$`, único e inmutable), `name`
  (1–60 caracteres tras `strip`), `keywords` (1–50 frases de 1–60 caracteres
  tras `normalize_text`, separadas por coma o salto de línea, sin duplicados
  normalizados) y `active`.
- **Acierto** de una categoría: una de sus keywords aparece como frase completa
  (límite de palabra) en `normalize_text(texto)`. Cada keyword cuenta como
  máximo una vez por mensaje.
- **Consulta elegible**: mensaje de cliente que llega al paso `rag.search` de
  `process_message` (no es `/start <token>`, ni comando de asesor, ni se reenvía
  a un caso abierto, ni pide asesor por palabra clave).
- `sin_clasificar`: valor de categoría cuando no hay clasificación fiable.

## Panel (orchestrator, `/admin/categories`)

## R1
CUANDO un admin con sesión válida pide `GET /admin/categories`, el sistema DEBE
responder `200` con todas las categorías (activas e inactivas) mostrando
`code`, `name`, `keywords` y estado, y el umbral vigente.

## R2
CUANDO un admin envía `POST /admin/categories` con `code`, `name` y `keywords`
válidos, el sistema DEBE crear la categoría activa y responder `303` a
`/admin/categories`.

## R3
CUANDO un admin envía `POST /admin/categories/{id}` con `name` y `keywords`
válidos para una categoría existente, el sistema DEBE reemplazar ese `name` y
esas `keywords` sin cambiar `code` ni `active`, y responder `303` a
`/admin/categories`.

## R4
CUANDO un admin envía `POST /admin/categories/{id}/active` con `active` igual a
`"true"` o `"false"` para una categoría existente, el sistema DEBE guardar ese
estado y responder `303` a `/admin/categories`.

## R5
SI un formulario de R2, R3 o R4 tiene un campo fuera de las definiciones (code,
name, keywords o `active` distinto de `"true"`/`"false"`) ENTONCES el sistema
DEBE responder `422` sin modificar ninguna categoría.

## R6
SI `POST /admin/categories` usa un `code` ya existente ENTONCES el sistema DEBE
responder `409` con el código `category_code_taken` sin modificar categorías.

## R7
SI R3 o R4 apuntan a un `{id}` inexistente ENTONCES el sistema DEBE responder
`404` con el código `category_not_found`.

## R8
CUANDO un admin envía `POST /admin/categories/threshold` con un decimal finito
entre `0` y `1` inclusive, el sistema DEBE guardar ese umbral y responder `303`
a `/admin/categories`.

## R9
SI el umbral enviado no es un decimal finito entre `0` y `1` (vacío, texto,
`nan`, `inf`, `-0.1`, `1.01`) ENTONCES el sistema DEBE responder `422` sin cambiar
el umbral guardado.

## R10
SI una ruta de `/admin/categories` llega sin sesión de admin válida ENTONCES el
sistema DEBE responder `303` a `/admin/login` sin leer ni modificar categorías
ni umbral.

## R11
SI un `POST` de `/admin/categories` llega con CSRF ausente o inválido ENTONCES
el sistema DEBE responder `403` sin modificar categorías ni umbral.

## R12
El sistema DEBE mostrar `name` y `keywords` escapados con `html.escape` y con
las cabeceras de seguridad de #21 en todas las páginas de `/admin/categories`.

## Clasificador (orchestrator, `classifier.py`, lógica pura)

## R13
El sistema DEBE calcular para cada categoría activa una puntuación en `[0, 1]`
igual a sus aciertos divididos por el total de aciertos de las categorías
activas, de modo que las puntuaciones sumen `1` cuando hay al menos un acierto.

## R14
El sistema NO DEBE contar aciertos ni puntuar categorías inactivas.

## R15
CUANDO la mayor puntuación es única y es mayor o igual que el umbral, el
sistema DEBE devolver el `code` de esa categoría y esa puntuación como
confianza.

## R16
SI la mayor puntuación es menor que el umbral ENTONCES el sistema DEBE devolver
`sin_clasificar` con esa puntuación como confianza.

## R17
SI no hay categorías activas o ninguna keyword acierta ENTONCES el sistema DEBE
devolver `sin_clasificar` con confianza `0`.

## R18
SI dos o más categorías empatan en la mayor puntuación ENTONCES el sistema DEBE
devolver `sin_clasificar` con esa puntuación como confianza.

## R19
El sistema DEBE contar un acierto solo cuando la keyword normalizada aparece
como frase completa (p. ej. `factura` no acierta en `facturacion`, y
`Facturación` acierta con `facturacion`).

## R20
El sistema DEBE tratar las keywords como texto literal, de modo que
metacaracteres de regex (`.*`, `|`, `(`) no amplíen la coincidencia ni
produzcan error.

## R21
El sistema DEBE contar cada keyword una sola vez por mensaje, de modo que
repetirla no aumente la puntuación.

## Flujo de mensajes (orchestrator, `process_message`)

## R22
CUANDO una consulta elegible llega al paso RAG, el sistema DEBE registrar un
evento `query_classified` con razón `<code>:<confianza con 2 decimales>` (o
`sin_clasificar:<confianza>`) antes de llamar a `rag.search`.

## R23
El sistema DEBE llamar a `rag.search` con los mismos argumentos y enviar la
misma respuesta al cliente sea cual sea el resultado de la clasificación
(categoría, `sin_clasificar` o sin categorías).

## R24
El sistema NO DEBE clasificar ni registrar `query_classified` para mensajes no
elegibles (`/start <token>`, comandos de asesor, reenvío a caso abierto o
petición de asesor por palabra clave), que siguen su flujo y permisos actuales.

## R25
SI leer categorías o umbral del repositorio lanza una excepción ENTONCES el
sistema DEBE registrar el log `classification_failed` y continuar al paso RAG
sin evento `query_classified`.

## R26
MIENTRAS no haya umbral guardado desde el panel, el sistema DEBE usar
`CLASSIFIER_DEFAULT_THRESHOLD` (default `0.6`, rango `0`–`1`).

## Persistencia (orchestrator, repositorio)

## R27
El esquema de `PostgresRepository` DEBE crear las tablas `query_categories`
(con `code` `UNIQUE`) y `app_settings`, y sus consultas de categorías y umbral
DEBEN usar SQL parametrizado.
