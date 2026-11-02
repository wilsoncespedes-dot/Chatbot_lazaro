# #23 bootstrap_administrador — Requirements

Servicio: **orchestrator** (único). Comando local/operativo
`python -m orchestrator.bootstrap_admin --username <nombre>`; se autentica
contra la base con las credenciales de `DATABASE_URL` (no hay endpoint HTTP).
Validación de `username` y longitud mínima de contraseña idénticas a #20
(`USERNAME_PATTERN`, `PROFILE_PASSWORD_MIN_LENGTH`).

## R1
CUANDO el comando se ejecuta sin ningún perfil `admin` existente, con un
`username` válido y una contraseña válida introducida dos veces igual, el
sistema DEBE crear un único perfil con `role` = `admin` mediante
`Repository.create_profile` y terminar con código `0`.

## R2
CUANDO el comando crea el administrador, el sistema DEBE guardar solo
`hash_password(clave, PASSWORD_HASH_ITERATIONS)` (formato
`pbkdf2_sha256$<iter>$<sal>$<hash>`), de modo que `verify_password(clave, hash)`
devuelva `True`.

## R3
El sistema DEBE leer la contraseña exclusivamente con `getpass.getpass`
(sin eco), pidiéndola dos veces.

## R4
SI el comando recibe una opción de contraseña en la línea de órdenes
(p. ej. `--password`) ENTONCES el sistema DEBE terminar con código `2` sin
crear perfiles; ninguna variable de entorno DEBE usarse como contraseña.

## R5
El sistema NO DEBE escribir la contraseña en claro en stdout, stderr ni logs,
en ningún resultado (éxito, rechazo o error).

## R6
SI ya existe al menos un perfil con `role` = `admin` ENTONCES el sistema DEBE
terminar con código `1` sin pedir la contraseña y sin crear ni modificar
perfiles.

## R7
SI el `username` es inválido, la contraseña es más corta que
`PROFILE_PASSWORD_MIN_LENGTH` o las dos entradas no coinciden ENTONCES el
sistema DEBE terminar con código `2` sin crear perfiles.

## R8
SI `create_profile` lanza `UsernameTaken` ENTONCES el sistema DEBE terminar
con código `2` con un mensaje fijo sin modificar el perfil existente.

## R9
SI `DATABASE_URL` está vacía ENTONCES el sistema DEBE terminar con código `2`
sin intentar conectar.

## R10
El sistema NO DEBE registrar ninguna ruta HTTP nueva para el bootstrap ni
crear credenciales por defecto (la app de `create_app` no expone rutas cuyo
path contenga `bootstrap`).

## Cobertura del acceptance
- Instalación vacía, comando autenticado al DB, contraseña solicitada sin
  imprimir ni guardar en claro → R1, R2, R3, R4, R5, R9, R10.
- Se niega si ya hay admin y no cambia datos → R6.
- Tests de hash, rol, unicidad y no exposición → R1, R2, R5, R6, R8.
