# Requirements — consulta_bd_lenguaje_natural (feature #26)

> Feature: «Consultas de datos autorizadas en lenguaje natural». Servicio único: **orchestrator**.
> Fuentes: acceptance de la #26, `docs/proyecto.md` §6, §11, §12. Depende de la #20 (perfil
> vinculado a Telegram), la #23 y la #24 (validación de configuración de producción).
> No toca `contracts/` ni otros servicios. Notación EARS estricta (`docs/specs.md`).
>
> Cobertura del acceptance: A1 → R1-R6 · A2 → R10-R20, R34-R36 · A3 → R21-R26, R32 · A4 → R27-R30.
> R31 y R32 son las mitades `NO DEBE` de R1 y R23; R33 preserva la deduplicación de `update_id`.

## Entrada y habilitación

## R1
CUANDO el orchestrator recibe en `POST /messages` un texto cuyo primer token es exactamente
`/consultar`, el sistema DEBE tratarlo como solicitud de consulta.

## R31
CUANDO el orchestrator recibe en `POST /messages` un texto cuyo primer token es exactamente
`/consultar`, el sistema NO DEBE guardarlo como mensaje, reenviarlo a un asesor, abrir traspaso
ni pasarlo por el RAG.

## R33
CUANDO `POST /messages` recibe un `/consultar` con un `update_id` ya registrado por
`mark_update_if_new`, el sistema DEBE descartarlo (respuesta `duplicate`) sin llamar al LLM, a
la conexión de lectura ni escribir auditoría.

## R2
SI el texto es `/consultar` sin pregunta, o la pregunta (tras `strip`) supera
`DB_QUERY_MAX_QUESTION_LENGTH` caracteres, ENTONCES el sistema DEBE responder al remitente con
`DB_QUERY_HELP_REPLY` sin llamar al LLM ni a la base de datos.

## R3
MIENTRAS `DB_QUERY_ENABLED` sea `false` (valor por defecto), el sistema DEBE responder a toda
solicitud `/consultar` autorizada con `DB_QUERY_DISABLED_REPLY` sin llamar al LLM ni abrir la
conexión de lectura.

## Autorización

## R4
CUANDO llega una solicitud `/consultar`, el sistema DEBE autorizarla solo si existe un perfil con
`role == "asesor"` cuyo `telegram_user_id` vinculado (feature #20) es igual al
`telegram_user_id` del remitente y este es mayor que 0.

## R5
SI el remitente no tiene perfil vinculado, o su perfil tiene rol `admin` o `cliente`, ENTONCES el
sistema DEBE responder con `DB_QUERY_FORBIDDEN_REPLY` sin llamar al LLM ni a la conexión de
lectura.

## R6
SI la solicitud llega desde un chat cuyo `chat_id` es distinto del `telegram_user_id` del
remitente (chat no privado) ENTONCES el sistema DEBE responder con `DB_QUERY_FORBIDDEN_REPLY`
sin llamar al LLM ni a la conexión de lectura.

## R7
El sistema DEBE evaluar la autorización (R4-R6) antes que el flag de habilitación (R3) y antes
que la validación de la pregunta (R2), de modo que un no autorizado reciba siempre
`DB_QUERY_FORBIDDEN_REPLY`.

## Configuración

## R8
DONDE `DB_QUERY_ENABLED` es `true`, el sistema DEBE rechazar la construcción de `Settings` si
`DB_QUERY_DATABASE_URL` está vacío o es igual a `DATABASE_URL`.

## R9
DONDE `DB_QUERY_ENABLED` es `true`, el sistema DEBE rechazar la construcción de `Settings` si
`DB_QUERY_ALLOWLIST` está vacío o contiene un nombre de vista fuera del esquema
`DB_QUERY_VIEWS_SCHEMA` o un identificador que no cumpla `^[a-z_][a-z0-9_]{0,62}$`.

## Generación de SQL con el LLM

## R10
CUANDO una solicitud autorizada y habilitada pide SQL al LLM, el sistema DEBE enviar como
esquema únicamente los nombres de vista y columnas de `DB_QUERY_ALLOWLIST` (texto estático
derivado de la configuración) y la pregunta neutralizada.

## R11
El sistema NO DEBE enviar al LLM filas, valores devueltos por la base de datos, conteos de
resultados ni metadatos leídos de la base de datos.

## R12
SI la respuesta del LLM no es un JSON `{"sql": "<texto>"}` con `sql` de tipo cadena no vacía
ENTONCES el sistema DEBE responder con `DB_QUERY_REJECTED_REPLY` sin abrir la conexión de
lectura.

## Validación del SQL (antes de ejecutar)

## R13
El sistema DEBE aceptar solo SQL que sea una única sentencia `SELECT` (se tolera un `;` final) y
rechazar cualquier otro `;`, los comentarios `--` y `/*`, las comillas dobles, `$` y `::`.

## R14
El sistema DEBE rechazar todo SQL que contenga una palabra clave fuera de la lista fija
`ALLOWED_KEYWORDS` o una palabra cuyo siguiente token (ignorando espacios, p. ej.
`pg_sleep (1)`) sea `(` y que no esté en la lista fija `ALLOWED_FUNCTIONS` de `db_query.py`
(en particular
`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `GRANT`, `COPY`,
`SET`, `WITH`, `INTO`, `CALL`, `DO`).

## R15
El sistema DEBE rechazar todo SQL que referencie, tras `FROM` o `JOIN`, un objeto que no sea un
nombre calificado `<DB_QUERY_VIEWS_SCHEMA>.<vista>` presente en `DB_QUERY_ALLOWLIST`.

## R16
El sistema DEBE rechazar todo SQL que use un identificador de columna no presente en las columnas
allowlisted de las vistas referenciadas (los alias solo se aceptan en las posiciones de R35 y
R36), o que use `*` fuera de `count(*)` o de una multiplicación entre dos operandos (en
particular `SELECT *`, `SELECT <vista>.*` y `SELECT <alias>.*`).

## R35
El sistema DEBE rechazar todo SQL en el que un alias de tabla (declarado con `AS` tras una vista
en `FROM`/`JOIN`) o un nombre de vista aparezca fuera de su declaración y no como calificador
seguido inmediatamente de `.` y de una columna allowlisted de esa vista (en particular
`SELECT t FROM <vista> AS t`, `SELECT count(t) ...`, `max(t)` o `WHERE t IS NOT NULL`).

## R36
El sistema DEBE rechazar todo SQL en el que un alias de columna (declarado con `AS` en la lista
`SELECT`) aparezca fuera de su declaración salvo como elemento directo de `ORDER BY`
(opcionalmente seguido de `ASC`/`DESC`); en particular dentro de una función o expresión, en
`WHERE`, `GROUP BY`, `HAVING`, `ON` o como calificador.

## R34
El sistema DEBE rechazar todo SQL que declare con `AS` un alias igual, sin distinguir
mayúsculas, a una palabra de `ALLOWED_KEYWORDS`, a una palabra prohibida de R14, a una función
de `ALLOWED_FUNCTIONS`, a un nombre de vista allowlisted, a una columna de cualquier vista
allowlisted o a otro alias ya declarado. Como R20 garantiza que las columnas reales de cada
vista coinciden exactamente con su allowlist, esto rechaza también colisiones con columnas
reales no permitidas (p. ej. `SELECT lower(secreto) AS secreto`).

## R17
El sistema DEBE rechazar todo SQL con más `JOIN` que `DB_QUERY_MAX_JOINS`.

## Ejecución

## R18
CUANDO el SQL pasa la validación, el sistema DEBE ejecutarlo solo por la conexión de
`DB_QUERY_DATABASE_URL`, dentro de una transacción `READ ONLY` con `statement_timeout` igual a
`DB_QUERY_TIMEOUT_MS`, terminada siempre con `ROLLBACK`.

## R19
El sistema DEBE devolver como máximo `DB_QUERY_MAX_ROWS` filas, pidiendo a la base como mucho
`DB_QUERY_MAX_ROWS + 1` filas y avisando en la respuesta cuando hubo truncado.

## R20
SI algún objeto de `DB_QUERY_ALLOWLIST` no es una vista (`pg_class.relkind <> 'v'`) en la
conexión de lectura, o el conjunto de columnas reales de esa vista en `pg_attribute`
(`attnum > 0 AND NOT attisdropped`) no es exactamente igual al conjunto de sus columnas
allowlisted (sobra o falta alguna), ENTONCES el sistema DEBE negarse a ejecutar consultas y
responder con `DB_QUERY_UNAVAILABLE_REPLY`.

## Auditoría y errores

## R21
CUANDO termina una solicitud `/consultar` de un remitente autorizado o denegado, el sistema DEBE
guardar una fila en `db_query_audit` mediante el repositorio de aplicación (nunca por la
conexión de lectura) con `profile_id`, `telegram_user_id`, `status`, `views`, `row_count`,
`sql_sha256` y `at`.

## R22
El sistema NO DEBE guardar en la auditoría ni en los logs la pregunta, el SQL en claro, filas de
resultado, `DB_QUERY_DATABASE_URL` ni credenciales.

## R23
SI falla la escritura de la auditoría ENTONCES el sistema DEBE responder con
`DB_QUERY_UNAVAILABLE_REPLY`.

## R32
SI falla la escritura de la auditoría ENTONCES el sistema NO DEBE enviar los resultados de la
consulta.

## R24
SI la ejecución falla (error de base de datos, timeout o conexión) ENTONCES el sistema DEBE
responder con `DB_QUERY_UNAVAILABLE_REPLY`, cuyo texto no incluye SQL, nombres de vistas,
columnas ni el mensaje de la excepción.

## R25
SI el SQL es rechazado por la validación (R13-R17, R34-R36) ENTONCES el sistema DEBE responder con
`DB_QUERY_REJECTED_REPLY` sin incluir el SQL ni el motivo técnico.

## R26
CUANDO la consulta tiene éxito, el sistema DEBE responder con las filas formateadas como texto,
recortado a `DB_QUERY_MAX_REPLY_CHARS` caracteres.

## Pruebas negativas obligatorias

## R27
SI el LLM propone SQL de escritura (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `COPY`,
`SET`) ENTONCES el sistema NO DEBE invocar la conexión de lectura.

## R28
SI el LLM propone varias sentencias (`SELECT ...; DELETE ...`) ENTONCES el sistema NO DEBE
invocar la conexión de lectura.

## R29
SI el LLM propone SQL sobre una tabla directa (p. ej. `profiles`, `public.contacts`), un esquema
de sistema (`pg_catalog`, `information_schema`) o una vista fuera de la allowlist ENTONCES el
sistema NO DEBE invocar la conexión de lectura.

## R30
SI un remitente admin, cliente, sin perfil o en chat no privado envía `/consultar` con
`DB_QUERY_ENABLED=true` ENTONCES el sistema NO DEBE invocar el LLM ni la conexión de lectura.
