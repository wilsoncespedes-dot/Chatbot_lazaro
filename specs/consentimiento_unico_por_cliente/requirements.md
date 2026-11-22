# Requirements — #72 consentimiento_unico_por_cliente

Servicio afectado: **orchestrator** (repositorio, dominio, config, purga y supresión).
Documentación de contrato: `contracts/CONTRATOS.md` (sin modelos nuevos ni cambios
de rutas). Reutiliza #35 (consentimiento antes de datos), #37 (versión del aviso,
botón), #46 (frase de texto) e identidad de #38+ (login, sesiones, supresión).

Glosario: `cliente_id` es el `profile_id` del perfil con rol `cliente`. «Identidad»
es el par `(canal_id, id_externo)`. «Aviso vigente» es `notice_version` actual de
`conversation_texts`. «Cubierta» significa que existe aceptación por cliente de la
versión vigente para la identidad vinculada.

## Registro por cliente (acceptance 1)

### R1
CUANDO un cliente completa el login verificado y la identidad del enlace tiene una
aceptación `accepted` por botón o texto del aviso vigente, el sistema DEBE guardar en
`consentimientos_cliente` una fila con `cliente_id`, `notice_version`,
`notice_sha256`, `aceptado_en` y `canal_id` del canal donde se aceptó.

### R2
CUANDO se guarda la aceptación por cliente de R1, el sistema DEBE conservar sin
cambios la fila de evidencia por canal de `privacy_consents`.

### R3
CUANDO el login verificado ocurre y ya existe una fila de `consentimientos_cliente`
para `(cliente_id, notice_version)`, el sistema DEBE conservar la fila original sin
modificar `aceptado_en` ni `canal_id`.

## Cobertura entre canales (acceptance 2)

### R4
MIENTRAS una identidad esté vinculada a un cliente con aceptación por cliente de la
versión vigente, el sistema NO DEBE enviar el aviso de consentimiento al recibir un
texto de esa identidad aunque no tenga fila propia en `privacy_consents`.

### R5
MIENTRAS una identidad esté vinculada a un cliente con aceptación por cliente de la
versión vigente, el sistema DEBE enrutar el texto como mensaje con consentimiento
(incluido el flujo de login si no hay sesión activa) tras cerrar sesión.

### R6
MIENTRAS una identidad esté vinculada a un cliente con aceptación por cliente de la
versión vigente, el sistema DEBE tratar la petición `POST /messages` de esa identidad
como con consentimiento vigente al decidir la clave de deduplicación en `main.py`.

## Cambio de versión (acceptance 3)

### R7
CUANDO cambia la versión del aviso, el sistema DEBE pedir el aviso una sola vez a
una identidad vinculada, en el primer canal por el que escriba, porque la aceptación
por cliente de la versión anterior no cubre la nueva.

### R8
CUANDO una identidad vinculada acepta el aviso vigente por botón o por frase de
texto, el sistema DEBE guardar la aceptación por cliente de la versión vigente
con el `canal_id` donde aceptó.

### R9
CUANDO la aceptación por cliente de R8 queda guardada, el sistema NO DEBE pedir el
aviso vigente a ninguna otra identidad vinculada al mismo cliente.

## Identidad nunca vinculada (acceptance 4)

### R10
MIENTRAS una identidad no esté vinculada a ningún cliente, el sistema DEBE enviar el
aviso de consentimiento antes de guardar datos, con el comportamiento de #35, #37 y #46.

### R11
SI una identidad no vinculada recibe un texto sin aceptación propia ENTONCES el
sistema NO DEBE crear contacto, mensaje ni estado para esa identidad.

## Identidades vinculadas e historial (acceptance 5)

### R12
El sistema DEBE crear la tabla `identidades_cliente` con las columnas `cliente_id`,
`canal_id`, `id_externo` y `vinculado_en`, con clave única `(canal_id, id_externo)`.

### R13
CUANDO el login verificado concluye (sesión creada), el sistema DEBE insertar la
identidad `(canal_id, id_externo)` del enlace de login en `identidades_cliente`
asociada al `cliente_id`.

### R14
SI el login falla (credenciales inválidas, enlace inválido, credencial no habilitada,
bloqueo o conflicto de sesión) ENTONCES el sistema NO DEBE insertar ni modificar
filas de `identidades_cliente`.

### R15
CUANDO una identidad ya vinculada a otro cliente completa un login verificado, el
sistema DEBE reasignarla al cliente que inició sesión y actualizar `vinculado_en`.

### R16
CUANDO se consulta el historial de un cliente, el sistema DEBE devolver los mensajes
de los contactos de todas sus identidades vinculadas, ordenados por fecha, cada uno
con su `canal`.

### R17
SI falla la escritura de la vinculación o de la aceptación por cliente tras crear la
sesión ENTONCES el sistema DEBE completar el login, registrar un aviso de log sin
datos personales y volver a pedir el aviso en el siguiente mensaje.

## Login obligatorio (acceptance 6)

### R18
El sistema DEBE exigir login verificado para atender a un cliente aunque su
identidad esté vinculada y cubierta por aceptación por cliente.

### R19
El sistema NO DEBE crear ruta, comando ni campo de configuración que identifique a un
cliente sin credenciales ni sin enlace de login firmado, ni código de verificación por
canal.

## Conservación y supresión (acceptance 7)

### R20
DONDE `CLIENT_CONSENT_RETENTION_DAYS` esté vacía (valor por defecto), el sistema DEBE
conservar `consentimientos_cliente` e `identidades_cliente` hasta la supresión del
cliente, sin borrarlas en la purga por retención.

### R21
DONDE `CLIENT_CONSENT_RETENTION_DAYS` sea un entero mayor o igual a 1, el sistema DEBE
borrar en la purga por retención las filas de `consentimientos_cliente` con
`aceptado_en` anterior al plazo y NO DEBE contarlas como cobertura.

### R22
SI `CLIENT_CONSENT_RETENTION_DAYS` no es vacío ni un entero mayor o igual a 1
ENTONCES el sistema DEBE rechazar la configuración al arrancar.

### R23
CUANDO se ejecuta la supresión de un cliente, el sistema DEBE borrar de
`consentimientos_cliente` e `identidades_cliente` todas las filas de ese `cliente_id`
y reportar los conteos en `removed_counts` con las claves `consentimientos_cliente` e
`identidades_cliente`.

### R24
CUANDO se ejecuta la supresión de un cliente, el sistema DEBE borrar también la
evidencia `privacy_consents` de todas las identidades vinculadas al cliente, no solo
de los contactos de sus sesiones.

### R25
MIENTRAS el cliente suprimido vuelva a escribir desde una identidad antes vinculada,
el sistema DEBE tratarla como no vinculada y pedir el aviso (R10).

## Pruebas y regresión (acceptance 8)

### R26
El sistema DEBE superar las pruebas existentes de #35, #37 y #46
(`test_consent_before_data.py`, `test_text_consent_telegram.py`, `test_privacy.py`)
sin cambiar su intención, con el repositorio fake y el real alineados.

### R27
El sistema DEBE documentar en `contracts/CONTRATOS.md` las tablas nuevas, la clave
`CLIENT_CONSENT_RETENTION_DAYS`, las claves nuevas de `deleted`/`removed_counts` y
el supuesto pendiente de legal.

## Trazabilidad con el acceptance original

| Acceptance | Requirements |
|---|---|
| 1 registro por cliente + evidencia por canal | R1, R2, R3 |
| 2 no volver a pedir (otro canal / tras cerrar sesión) | R4, R5, R6 |
| 3 cambio de versión, una sola vez | R7, R8, R9 |
| 4 identidad nunca vinculada recibe aviso | R10, R11 |
| 5 tabla `identidades_cliente` e historial | R12, R13, R14, R15, R16, R17 |
| 6 login obligatorio, sin mecanismos alternativos | R18, R19 |
| 7 conservación configurable y supresión | R20, R21, R22, R23, R24, R25 |
| 8 pruebas y regresión | R26, R27 |
