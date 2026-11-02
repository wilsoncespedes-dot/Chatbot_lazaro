# #22 panel_fragmentos — Requirements

Servicios: **contracts**, **rag** y **orchestrator** (panel `/admin` de #21).
Se reutilizan `POST /manuals` (#5) y `PATCH /chunks/{id}` (#19) sin cambios, y
la sesión, el control de rol y el CSRF de #21. Solo se añaden tres rutas de
contrato: `GET /manuals`, `GET /manuals/{id}/chunks` y
`PATCH /chunks/{id}/active`.

## Contrato (contracts)

## R1
El contrato DEBE documentar en `contracts/CONTRATOS.md` y en `lazaro_contracts`
las rutas `GET /manuals`, `GET /manuals/{id}/chunks` y `PATCH /chunks/{id}/active`,
con sus modelos, un ejemplo JSON válido para cada cuerpo y sus errores `401`,
`404` (solo las dos rutas con `{id}`), `422` (solo `PATCH`) y `500`.

## RAG (rag)

## R2
CUANDO RAG recibe `GET /manuals` con un `X-Service-Token` válido, el sistema DEBE
responder `200` con la lista de manuales, el más reciente primero, y para cada
uno su `manual_id`, `name` y número de fragmentos `chunks`.

## R3
CUANDO RAG recibe `GET /manuals/{id}/chunks` para un manual existente, el sistema
DEBE responder `200` con todos sus fragmentos, activos e inactivos, en orden
ascendente de `order`, cada uno con `chunk_id`, `manual_id`, `manual`, `order`,
`text` y `active`.

## R4
SI `GET /manuals/{id}/chunks` recibe un `{id}` que no existe ENTONCES RAG DEBE
responder `404` con `error` = `not_found`.

## R5
CUANDO RAG recibe `PATCH /chunks/{id}/active` con `{"active": <booleano>}` para un
fragmento existente, el sistema DEBE guardar ese estado y responder `200` con el
fragmento (mismos campos que R3), sin cambiar su texto, embedding, manual ni orden.

## R6
SI `PATCH /chunks/{id}/active` recibe un `{id}` que no existe ENTONCES RAG DEBE
responder `404` con `error` = `not_found` sin modificar ningún fragmento.

## R7
SI el cuerpo de `PATCH /chunks/{id}/active` no tiene `active`, trae un valor que
no es booleano JSON o trae campos extra ENTONCES RAG DEBE responder `422` con
`error` = `validation_error` sin modificar ningún fragmento.

## R8
SI una petición a cualquiera de las tres rutas nuevas llega sin un
`X-Service-Token` válido ENTONCES RAG DEBE responder `401` con
`error` = `unauthorized` sin leer ni modificar datos.

## Panel (orchestrator)

## R9
CUANDO un administrador con sesión pide `GET /admin/manuals`, el orquestador DEBE
mostrar los manuales devueltos por `GET /manuals` con su nombre, su número de
fragmentos y un enlace a `/admin/manuals/{manual_id}`, junto a un formulario de
carga (`name` y `file`).

## R10
CUANDO un administrador con sesión envía `POST /admin/manuals` (multipart) con
`name` y `file` válidos, el orquestador DEBE reenviarlos a `POST /manuals` del RAG
y responder `303` hacia `/admin/manuals/{manual_id}` del manual creado.

## R11
SI `POST /admin/manuals` trae un archivo de más de `ADMIN_MANUAL_MAX_BYTES` bytes,
le falta `name` o `file`, o `name` no valida contra `ManualUploadRequest`
ENTONCES el orquestador DEBE responder con la página de manuales y código `413`
(tamaño) o `422` (resto) sin llamar al RAG.

## R12
CUANDO un administrador con sesión pide `GET /admin/manuals/{manual_id}`, el
orquestador DEBE mostrar los fragmentos devueltos por `GET /manuals/{id}/chunks`
con su orden, su texto, su estado activo, un formulario de edición del texto y un
formulario para activarlo o desactivarlo.

## R13
CUANDO un administrador con sesión envía `POST /admin/chunks/{chunk_id}` con un
`text` que valida contra `ChunkUpdateRequest`, el orquestador DEBE llamar a
`PATCH /chunks/{id}` del RAG y responder `303` hacia
`/admin/manuals/{manual_id}` del fragmento.

## R14
SI `POST /admin/chunks/{chunk_id}` trae un `text` ausente, vacío o solo con
espacios ENTONCES el orquestador DEBE responder `422` sin llamar al RAG.

## R15
CUANDO un administrador con sesión envía `POST /admin/chunks/{chunk_id}/active`
con `active` = `true` o `false`, el orquestador DEBE llamar a
`PATCH /chunks/{id}/active` con ese booleano y responder `303` hacia
`/admin/manuals/{manual_id}` del fragmento.

## R16
SI `POST /admin/chunks/{chunk_id}/active` trae un `active` distinto de `true` o
`false` ENTONCES el orquestador DEBE responder `422` sin llamar al RAG.

## R17
SI el RAG responde `404`, `415` o `422` a una operación de las vistas nuevas
ENTONCES el orquestador DEBE responder una página HTML con ese mismo código y un
mensaje fijo por código de error, sin reproducir el cuerpo de la respuesta del RAG.

## R18
SI el RAG no responde, responde `401`, `5xx` o un cuerpo que no valida contra el
contrato ENTONCES el orquestador DEBE responder `502` con una página HTML de
mensaje fijo.

## R19
MIENTRAS una petición a las rutas nuevas de `/admin` no traiga una sesión admin
válida, el orquestador DEBE responder `303` hacia `/admin/login` sin llamar al RAG
(R3 de #21).

## R20
SI un `POST` a las rutas nuevas de `/admin` con sesión válida llega sin
`csrf_token` o con uno distinto al de su sesión ENTONCES el orquestador DEBE
responder `403` sin llamar al RAG (R4 de #21; en el multipart, `csrf_token` es una
parte del formulario).

## R21
El orquestador NO DEBE incluir el valor de `SERVICE_TOKEN` en el cuerpo, las
cabeceras ni las cookies de ninguna respuesta de las rutas nuevas de `/admin`,
incluidas las de error de R11, R14 y R16–R18.

## R22
El orquestador DEBE servir las respuestas HTML de las rutas nuevas con las
cabeceras de seguridad de #21 (CSP de R5, `nosniff`, `Cache-Control: no-store`) y
sin `<script>` ni recursos de origen externo.

## Cobertura del acceptance

| Criterio | Requirements |
|----------|--------------|
| 1. Cargar manuales, consultar fragmentos, editar y activar/desactivar | R2–R7, R9–R18 |
| 2. Rutas nuevas del RAG en `CONTRATOS.md` y `lazaro_contracts`, con ejemplos y `X-Service-Token` | R1, R8 |
| 3. Tests de manuales/fragmentos, sesión/CSRF de vistas nuevas y `SERVICE_TOKEN` fuera del navegador | R2–R22 |
