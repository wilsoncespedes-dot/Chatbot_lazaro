# Requirements — #77 `importacion_clientes`

Servicio: `orchestrator` (único servicio tocado). Solo CSV; sin Excel y sin
dependencias nuevas. Encabezados documentados (en minúsculas, sin tildes):
`id`, `usuario`, `correo`, `telefono`. `usuario` es el único campo de nombre que
tiene hoy el cliente («nombre» del acceptance se mapea a `usuario`, ver S1 en
`design.md`). `usuario` es obligatorio; `id`, `correo` y `telefono` son opcionales.

## Acceso y entrada

## R1
El sistema DEBE mostrar, en `GET /admin/clientes`, un enlace «Importar clientes» hacia `GET /admin/clientes/importar` cuando la sesión es de rol admin.

## R2
SI una sesión de rol distinto de admin (o sin sesión) solicita cualquier ruta de `/admin/clientes/importar*` ENTONCES el sistema DEBE responder igual que las demás rutas de `/admin/clientes` para ese caso (403 o redirección a login) sin leer el cuerpo.

## R3
SI un `POST /admin/clientes/importar/*` llega sin un `csrf_token` válido de la sesión ENTONCES el sistema DEBE responder `403`, auditar `forbidden` y no procesar el archivo.

## R4
CUANDO el admin sube un CSV UTF-8 (con o sin BOM) con separador coma, el sistema DEBE leer sus filas usando la primera línea como encabezado.

## R5
CUANDO el admin sube un CSV UTF-8 con separador punto y coma, el sistema DEBE leer sus filas igual que con coma.

## R6
SI el archivo no decodifica como UTF-8 ENTONCES el sistema DEBE rechazarlo con un error `archivo_no_utf8` y no crear vista previa.

## R7
SI al encabezado le falta la columna `usuario` o contiene una columna no documentada ENTONCES el sistema DEBE rechazar el archivo con el error `encabezado_invalido` indicando la columna.

## Límites y privacidad del archivo

## R8
SI el archivo supera `CLIENT_IMPORT_MAX_BYTES` (defecto 1048576) ENTONCES el sistema DEBE rechazarlo con `archivo_demasiado_grande` sin parsearlo.

## R9
SI el archivo tiene más de `CLIENT_IMPORT_MAX_ROWS` filas de datos (defecto 1000) ENTONCES el sistema DEBE rechazarlo con `demasiadas_filas` sin crear vista previa.

## R10
El sistema NO DEBE escribir el archivo subido en disco ni en base de datos en ningún paso del flujo.

## R11
El sistema NO DEBE aceptar ni leer una columna de contraseña: un encabezado `password`, `contrasena` o similar DEBE rechazarse por R7 y nunca llegar a la base.

## Vista previa y validación

## R12
CUANDO el archivo es válido en estructura, el sistema DEBE mostrar una vista previa con cada fila leída (número de fila y valores) sin crear ni modificar ningún cliente.

## R13
SI el valor de `usuario` de una fila no cumple `USERNAME_PATTERN` ENTONCES el sistema DEBE marcar la fila con el error `usuario_invalido` en el campo `usuario`.

## R14
SI el valor de `id` de una fila no vacía no cumple el formato de ID público (`normalize_public_id`) ENTONCES el sistema DEBE marcar la fila con el error `id_invalido` en el campo `id`.

## R15
SI el valor de `correo` de una fila no vacía no tiene formato de correo válido o excede 254 caracteres ENTONCES el sistema DEBE marcar la fila con el error `correo_invalido` en el campo `correo`.

## R16
SI el valor de `telefono` de una fila no vacía no tiene entre 7 y 15 dígitos (admitiendo `+`, espacios, guiones y paréntesis) ENTONCES el sistema DEBE marcar la fila con el error `telefono_invalido` en el campo `telefono`.

## R17
El sistema DEBE mostrar en la vista previa, por cada fila con errores, todos sus errores con el nombre del campo y el código.

## R18
El sistema DEBE normalizar `id` a `XXXX-XXXX`, `correo` a minúsculas y `telefono` a `+` opcional más dígitos antes de comparar o guardar.

## Duplicados

## R19
CUANDO una fila válida coincide por `id` con un cliente existente, el sistema DEBE marcarla como duplicado de base con el motivo `id`.

## R20
CUANDO una fila válida coincide por `correo` con un cliente existente, el sistema DEBE marcarla como duplicado de base con el motivo `correo`.

## R21
CUANDO una fila válida coincide por `telefono` con un cliente existente, el sistema DEBE marcarla como duplicado de base con el motivo `telefono`.

## R22
CUANDO una fila válida repite el `id`, el `correo`, el `telefono` o el `usuario` de una fila anterior válida del mismo archivo, el sistema DEBE marcarla como duplicado en archivo con el motivo y la fila de origen.

## R23
SI una fila coincide con dos clientes existentes distintos (por claves diferentes) ENTONCES el sistema DEBE marcarla como `conflicto_multiple` y no actualizarla aunque se elija actualizar.

## R24
El sistema DEBE ofrecer en la vista previa una única elección de política para duplicados de base, «Actualizar» o «Saltar», con «Saltar» preseleccionado.

## Ejecución y resumen

## R25
CUANDO el admin confirma la importación con una vista previa vigente, el sistema DEBE crear un cliente por cada fila válida sin duplicados.

## R26
CUANDO la política es «Actualizar», el sistema DEBE actualizar solo `correo` y `telefono` (los que vengan no vacíos) del cliente existente por cada duplicado de base sin conflicto.

## R27
CUANDO la política es «Saltar», el sistema DEBE dejar intactos los clientes existentes y contar cada duplicado de base como saltado.

## R28
El sistema DEBE contar como saltada y no importar toda fila duplicada en archivo (R22), sin importar la política.

## R29
El sistema DEBE contar como fallida, con su motivo, toda fila con errores de validación, con `usuario` ya tomado por un cliente no coincidente, o cuya escritura lance una excepción.

## R30
CUANDO termina la importación, el sistema DEBE mostrar un resumen con los totales de creados, actualizados, saltados y fallidos y el motivo de cada fila saltada o fallida.

## R31
SI una fila falla al escribirse ENTONCES el sistema DEBE continuar con las filas restantes y reflejar la falla en el resumen.

## R32
CUANDO el admin confirma con un token de vista previa ausente, caducado, ya usado o de otra sesión, el sistema DEBE responder `409` con `vista_previa_expirada` sin escribir clientes.

## R33
El sistema DEBE conservar la vista previa solo en memoria durante `CLIENT_IMPORT_PREVIEW_TTL_SECONDS` (defecto 900) y descartarla al confirmar o caducar.

## R34
CUANDO el admin descarga el resumen en CSV, el sistema DEBE prefijar con `'` toda celda que empiece por `=`, `+`, `-`, `@`, tabulador o retorno de carro.

## R35
El sistema NO DEBE incluir correo ni teléfono en el CSV del resumen ni en los eventos de auditoría.

## Fuente, credencial y esquema

## R36
El sistema DEBE crear y actualizar clientes importados exclusivamente mediante métodos del puerto `FuenteDeClientes`.

## R37
CUANDO se crea un cliente importado, el sistema DEBE asignarle una credencial inactiva: hash no verificable por `verify_password` y vigencia ya vencida.

## R38
El sistema NO DEBE crear un cliente importado con una contraseña utilizable ni con credencial activa.

## R39
El sistema DEBE guardar `correo` y `telefono` como columnas opcionales del perfil (`email`, `phone`) con migración idempotente `ADD COLUMN IF NOT EXISTS`.

## R40
CUANDO se ejecuta una supresión de datos personales de un cliente, el sistema DEBE dejar `email` y `phone` de ese perfil en nulo.

## R41
CUANDO se ejecuta la purga por retención con un `cutoff`, el sistema DEBE dejar en nulo `email` y `phone` de los clientes cuya fecha de contacto sea anterior a `cutoff`.

## R42
CUANDO se confirma una importación, el sistema DEBE auditar `client_import` con el resultado y los totales, y la vista previa DEBE auditar `client_import_preview`.

## Trazabilidad con el acceptance

| Acceptance | Requirements |
|---|---|
| 1 Botón, solo admin, CSV coma/; | R1-R7 |
| 2 Vista previa y errores por fila y campo | R12-R18 |
| 3 Duplicados base/archivo y elegir | R19-R24, R26-R28 |
| 4 Resumen | R25, R29-R32 |
| 5 Vía `FuenteDeClientes` | R36 |
| 6 Sin contraseñas / sin credencial activa | R11, R37, R38 |
| 7 Límites, sin guardar archivo, fórmulas | R8-R10, R33-R35 |
| 8 Correo/teléfono, retención y supresión | R39-R41 |
| 9 Pruebas, CSRF, permisos | R2, R3, R42 y tasks |
