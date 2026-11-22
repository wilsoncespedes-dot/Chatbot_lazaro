# Requirements — #76 `fuente_clientes_y_futuro_lazaro`

Servicio afectado: **orchestrator** (más documentación). No se toca gateway, handover ni contratos.

## Puerto FuenteDeClientes

## R1
El sistema DEBE definir en el orquestador el puerto `FuenteDeClientes` con las operaciones buscar por ID de cliente, listar, crear y actualizar.

## R2
El sistema DEBE ofrecer la implementación `FuenteClientesLocal`, que cumple el puerto sobre el repositorio actual de credenciales de cliente sin cambiar el esquema de datos.

## R3
CUANDO se invoca `buscar_por_id` de `FuenteClientesLocal` con un ID público existente, el sistema DEBE devolver el cliente con su credencial y contactos vinculados.

## R4
CUANDO se invoca `buscar_por_id` de `FuenteClientesLocal` con un ID público inexistente, el sistema DEBE devolver `None`.

## R5
CUANDO se invoca `listar` de `FuenteClientesLocal`, el sistema DEBE devolver todos los clientes con credencial en el mismo orden que el repositorio.

## R6
CUANDO se invoca `crear` de `FuenteClientesLocal`, el sistema DEBE crear el perfil `cliente` y su credencial y devolver el perfil creado con el ID público indicado.

## R7
SI `crear` recibe un ID público ya usado ENTONCES `FuenteClientesLocal` DEBE propagar `PublicIdTaken`.

## R8
SI `crear` recibe un usuario ya existente ENTONCES `FuenteClientesLocal` DEBE propagar `UsernameTaken`.

## R9
CUANDO se invoca `actualizar` con una nueva fecha de vencimiento sobre una credencial no revocada, el sistema DEBE guardar la nueva fecha y devolver `True`.

## R10
CUANDO se invoca `actualizar` con `revocar=True`, el sistema DEBE marcar la credencial como revocada y devolver `True`.

## R11
SI `actualizar` recibe un cliente inexistente o con credencial revocada para renovar ENTONCES `FuenteClientesLocal` DEBE devolver `False` sin modificar datos.

## Integración con el panel y la API

## R12
El sistema DEBE resolver la fuente de clientes desde `Adapters` y usar `FuenteClientesLocal` sobre el repositorio cuando no se inyecta otra.

## R13
CUANDO un administrador envía `POST /admin/clientes` con datos válidos, el sistema DEBE crear el cliente a través del puerto `FuenteDeClientes` y redirigir a `/admin/clientes` igual que antes.

## R14
CUANDO se llama `list_clients_admin`, el sistema DEBE obtener los clientes a través del puerto `FuenteDeClientes`.

## R15
CUANDO se renueva o revoca una credencial, el sistema DEBE leerla y modificarla a través del puerto `FuenteDeClientes`, conservando la auditoría, el cierre de sesión y los avisos actuales.

## R16
CUANDO se busca un cliente por ID público en el panel de asesores, el sistema DEBE consultarlo a través del puerto `FuenteDeClientes`.

## R17
CUANDO se llama `POST /clients` con datos válidos, el sistema DEBE crear el cliente a través del puerto `FuenteDeClientes` con la misma respuesta `201` de antes.

## Tarjeta «a futuro»

## R18
CUANDO un usuario autorizado abre `GET /admin/clientes`, el sistema DEBE mostrar una tarjeta visible con el texto exacto: «A futuro, esta sección podría conectarse a la API de Lazaro para traer los clientes automáticamente y mantenerlos sincronizados (evitando clientes creados o eliminados solo en un sistema). El bot podría identificar al cliente por el ID que entrega en el chat y buscarlo en los datos de Lazaro.»

## R19
CUANDO `GET /admin/clientes` responde con error de validación (422/404/409 desde el mismo formulario), el sistema DEBE seguir mostrando la tarjeta «a futuro».

## R20
La tarjeta «a futuro» NO DEBE contener formularios, botones, enlaces ni campos de entrada.

## Sin conexión simulada

## R21
El sistema NO DEBE contener en `services/`, `contracts/` ni `scripts/` una clase, configuración, variable de entorno, ruta o botón llamados `LazaroClientSource` ni relacionados con una conexión a la API de Lázaro.

## R22
El sistema NO DEBE mostrar en `/admin/clientes` texto que afirme que la conexión con Lázaro funciona, está disponible o sincroniza datos, salvo la tarjeta de R18.

## Documentación

## R23
La documentación (`docs/architecture.md`) DEBE describir el adaptador `LazaroClientSource` solo como posibilidad a futuro, con buscar por ID, listar y sincronizar.

## R24
La documentación DEBE describir cómo la sincronización manejaría duplicados y borrados, indicando que no está implementada.

## R25
La documentación NO DEBE presentar `LazaroClientSource` como implementado ni como compromiso.

## Regresión y calidad

## R26
CUANDO `./init.sh` se ejecuta tras la implementación, el sistema DEBE pasar todas las pruebas existentes sin modificar su comportamiento observable.
