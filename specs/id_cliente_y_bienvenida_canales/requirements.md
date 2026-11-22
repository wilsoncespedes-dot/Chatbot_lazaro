# Requirements — id_cliente_y_bienvenida_canales (#73)

Servicio: todo en `orchestrator` (repositorio, dominio, panel, config); sin cambios de
contrato HTTP entre servicios. Términos: «ID de cliente» = `public_id` de un perfil con rol
`cliente`; «canal público» = canal de `canales` con `config.public == true`.

## ID de cliente (orchestrator: dominio y repositorio)

## R1
El sistema DEBE generar el ID de cliente con el formato `XXXX-XXXX`, con caracteres del alfabeto `23456789ABCDEFGHJKMNPQRSTVWXYZ` (sin `0 O 1 I L U`).

## R2
El sistema DEBE generar el ID de cliente con `secrets` y sin recibir ningún dato del cliente (ni usuario, ni `profile_id`, ni teléfono, ni orden de creación).

## R3
CUANDO el administrador crea un cliente, el sistema DEBE guardar su ID en `profiles.public_id` con restricción de unicidad.

## R4
SI el ID generado ya existe al crear un cliente ENTONCES el sistema DEBE generar otro y reintentar hasta 5 veces.

## R5
SI los 5 intentos de generación chocan con IDs existentes ENTONCES el sistema DEBE lanzar `PublicIdGenerationError` y no crear el perfil ni la credencial.

## R6
CUANDO el administrador renueva, revoca o cierra la sesión de un cliente, el sistema NO DEBE modificar su ID.

## R7
CUANDO el orquestador inicia el esquema y existen clientes sin ID, el sistema DEBE asignar un ID único a cada uno sin alterar los que ya tienen.

## R8
CUANDO se suprime a un cliente, el sistema DEBE borrar su ID junto con su perfil.

## ID en el chat (orchestrator: dominio)

## R9
CUANDO un cliente inicia sesión con éxito (acceso o sin acceso por credencial vencida), el sistema DEBE enviar, después del mensaje de bienvenida o de suspensión, un mensaje propio cuyo texto sea exactamente su ID.

## R10
CUANDO un cliente con sesión activa escribe un comando de `IDENTITY_CLIENT_ID_COMMANDS`, el sistema DEBE responder con un texto introductorio y, en un mensaje aparte, solo su ID.

## R11
El sistema DEBE comparar el comando de ID por igualdad exacta normalizada (como `/salir`), de modo que `mi id 5` no sea un comando.

## R12
SI un contacto sin sesión activa escribe un comando de ID ENTONCES el sistema NO DEBE enviar ningún ID y DEBE seguir el flujo normal de su estado (aviso de login).

## R13
SI un mensaje de chat contiene un ID de cliente válido ENTONCES el sistema NO DEBE cambiar el estado de conversación ni vincular la identidad del canal a ningún cliente.

## R14
SI un mensaje de chat contiene un ID de cliente válido ENTONCES el sistema NO DEBE consultar el repositorio por `public_id` ni pasar al harness o a sus herramientas datos del cliente dueño de ese ID.

## ID en el panel (orchestrator: advisor_panel, admin, rutas)

## R15
El sistema DEBE mostrar el ID del cliente con botón «Copiar» en la ficha del cliente del detalle del caso.

## R16
El sistema DEBE mostrar el ID del cliente con botón «Copiar» en cada fila de la bandeja de casos y de conversaciones que tenga cliente autenticado.

## R17
El sistema DEBE mostrar el ID del cliente con botón «Copiar» en el encabezado del detalle de la conversación y en la lista de Clientes del administrador.

## R18
El sistema DEBE implementar el botón «Copiar» como `<button type="button" data-copy="<ID>">` servido con un script del mismo origen (`/panel/copiar.js`) que usa `navigator.clipboard` con alternativa de selección, sin scripts en línea ni cambios de CSP.

## R19
CUANDO un asesor o supervisor consulta `GET /asesor/clientes?q=<ID>`, el sistema DEBE mostrar al cliente con ese ID, su usuario, estado de credencial y enlaces a sus conversaciones.

## R20
CUANDO un administrador consulta `GET /admin/clientes?q=<ID>`, el sistema DEBE filtrar la lista a ese cliente.

## R21
El sistema DEBE normalizar `q` (mayúsculas, sin espacios ni guiones) antes de buscar, de modo que `ab3k-7mnp` y `AB3K 7MNP` encuentren el mismo cliente.

## R22
SI `q` no tiene formato válido de ID ENTONCES el sistema DEBE responder `200` con el mensaje «ID no válido» sin consultar el repositorio.

## R23
SI no existe cliente con el ID buscado ENTONCES el sistema DEBE responder `200` con «Sin resultados».

## R24
SI quien busca no tiene sesión de panel con rol permitido ENTONCES el sistema DEBE negar la búsqueda con la misma respuesta que ya dan las rutas `/asesor/*` y `/admin/*`.

## R25
El sistema NO DEBE mostrar en el resultado de búsqueda la contraseña, su hash ni el id externo sin enmascarar.

## Bienvenida con canales (orchestrator: dominio, config, admin de canales)

## R26
CUANDO se envía el aviso de primer contacto con saludo, el sistema DEBE añadir al saludo la lista de canales activos con `config.public == true`.

## R27
El sistema DEBE listar de cada canal su nombre, el glifo de su ícono y, si tiene `config.contact_url`, ese enlace.

## R28
El sistema NO DEBE listar canales inactivos ni canales sin `config.public == true`.

## R29
MIENTRAS `CHANNELS_WELCOME_INCLUDE_SIMULATED` sea `false` (por defecto), el sistema NO DEBE listar canales de tipo `simulado`.

## R30
DONDE `CHANNELS_WELCOME_INCLUDE_SIMULATED` sea `true`, el sistema DEBE listar también los canales simulados públicos y activos.

## R31
SI ningún canal cumple las condiciones ENTONCES el sistema NO DEBE añadir bloque de canales al saludo.

## R32
SI el directorio de canales no está disponible ENTONCES el sistema DEBE enviar el saludo sin la lista y registrar el fallo sin datos personales.

## R33
El sistema DEBE listar como máximo 10 canales, en orden alfabético por nombre.

## R34
El formulario de canales del panel admin DEBE permitir marcar un canal como público y guardar `contact_url`.

## R35
SI `contact_url` no empieza por `https://` o supera 200 caracteres ENTONCES el formulario DEBE rechazarlo con `ChannelFormError`.

## R36
SI un `contact_url` guardado no es `https://` al renderizar la bienvenida ENTONCES el sistema DEBE listar el canal sin enlace.

## Documentación

## R37
El sistema DEBE dejar en `docs/especificacion.md` una subsección que describa el login configurable según la empresa como posibilidad no implementada, junto con el ID de cliente y la bienvenida con canales.
