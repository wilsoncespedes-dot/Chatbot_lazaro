# #39 harness_ia_por_estado — Requirements

Servicio afectado: **orchestrator**. Ningún otro servicio cambia su código y
no se modifica ningún contrato de `contracts/` (ver design, alternativa
descartada "ampliar `HandoverReason`"). El gateway, RAG y handover se usan con
los contratos vigentes.

Vocabulario:

- **Herramienta**: acción que el harness ejecuta a partir de la interpretación
  del mensaje de un cliente con consentimiento vigente. Son exactamente seis
  (`ToolName`): `buscar_base_conocimiento`, `consultar_mis_datos`,
  `escalar_a_asesor`, `crear_solicitud_supresion`, `enviar_link_inicio_sesion`,
  `cerrar_sesion`.
- **Origen** de una invocación: `keyword` (palabra clave configurada en el
  texto del cliente), `router` (decisión JSON del LLM, opcional), `rule`
  (regla del código: herramienta por defecto del estado, umbral de fallos,
  recordatorio de login en `awaiting_login`).
- **Pasos obligatorios del código** (no son herramientas y no pasan por la
  matriz): compuerta de consentimiento (#35/#37), botones Aceptar/Rechazar,
  respuesta fija a contenido no textual, comandos de cierre fijos de #38
  (`IDENTITY_LOGOUT_COMMANDS`), expiración por inactividad, revocación y
  vencimiento detectados por `_apply_identity_rules`, reenvío al asesor en
  `with_advisor` y los comandos de personal (`/consultar`, `/responder`,
  `/cerrar`, `/start`).
- **cliente_id**: `profile_id` de la sesión activa del contacto
  (`active_client_id(contact.id)`, #38).
- **Matriz** (`TOOL_MATRIX`):

| Estado | Herramientas permitidas |
|---|---|
| `new` | ninguna |
| `awaiting_consent` | ninguna |
| `closed` | ninguna |
| `awaiting_login` | `enviar_link_inicio_sesion` |
| `active` | `buscar_base_conocimiento`, `consultar_mis_datos`, `escalar_a_asesor`, `crear_solicitud_supresion`, `cerrar_sesion` |
| `with_advisor` | ninguna |
| `no_access` | `escalar_a_asesor`, `crear_solicitud_supresion`, `cerrar_sesion` |

Trazabilidad con el acceptance de `feature_list.json` (#39):

| Acceptance | Requirements |
|---|---|
| A1 matriz explícita; autorización en código antes de ejecutar | R1–R10, R16–R20, R52, R53 |
| A2 identidad de la sesión; datos personales solo por vistas con RLS | R21–R35 |
| A3 supresión solo crea solicitud/caso; ninguna herramienta borra | R36–R43 |
| A4 RAG con fuentes y citas; escalamiento por solicitud, fallo repetido y frustración | R44–R51, R60 |
| A5 evaluación de ataques; `./init.sh` y reviewer | R54–R59, R61–R63 |
| Guardrails de entrada (detalle de `docs/especificacion.md`) | R11–R15 |

## Matriz y autorización

## R1
El orchestrator DEBE definir en `orchestrator/harness.py` una matriz inmutable
`TOOL_MATRIX` que asigna a cada uno de los siete `ConversationState`
exactamente el conjunto de herramientas de la tabla del vocabulario.

## R2
El tipo `ToolName` del orchestrator DEBE contener exactamente los seis nombres
de herramienta del vocabulario y ningún otro.

## R3
La función pura `authorize_tool(state, tool)` DEBE devolver `True` si y solo si
`tool` pertenece a `TOOL_MATRIX[state]`.

## R4
CUANDO el orchestrator va a ejecutar cualquier herramienta, sea cual sea su
origen, DEBE invocar `execute_tool`, que llama a `authorize_tool` con el estado
de conversación leído del repositorio en ese mismo turno antes de llamar al
ejecutor de la herramienta.

## R5
SI `authorize_tool` devuelve `False` ENTONCES el orchestrator NO DEBE llamar
al ejecutor de esa herramienta ni a los adaptadores que usa (`rag`, `llm` para
SQL, `client_data`, `handover`, escrituras de `suppression_requests` o cierre
de sesión).

## R6
SI se deniega una herramienta de origen `router` ENTONCES el orchestrator DEBE
responder al contacto con `HARNESS_TOOL_DENIED_REPLY`.

## R7
CUANDO `execute_tool` resuelve una invocación, el orchestrator DEBE insertar
una fila en `tool_calls` con `contact_id`, `profile_id` (o nulo), `state`,
`tool`, `origin`, `decision` (`allowed`, `denied` o `invalid`), `result`,
`args_sha256`, `detail` y `at`.

## R8
El orchestrator NO DEBE guardar en `tool_calls` el texto del mensaje, el SQL en
claro, filas de datos ni los argumentos en claro; los argumentos se guardan
solo como SHA-256 de su JSON canónico (`sort_keys=True`) y `detail` solo admite
nombres de vistas, número de filas, `sql_sha256` y códigos de resultado.

## R9
CUANDO se ejecuta la purga de retención (#27), el orchestrator DEBE borrar las
filas de `tool_calls` con `at < cutoff` y las de los contactos inactivos
purgados, e informar el número en `deleted["tool_calls"]`.

## R10
CUANDO la salida del router no es válida (R18), el orchestrator DEBE registrar
en `tool_calls` una fila con `decision = "invalid"` y `origin = "router"`.

## Guardrails de entrada

## R11
SI el texto de un cliente en `active` o `no_access` supera
`HARNESS_MAX_INPUT_CHARS` caracteres ENTONCES el orchestrator DEBE responder
`HARNESS_INPUT_TOO_LONG_REPLY` sin llamar a `rag`, `llm`, `client_data` ni
`handover`.

## R12
CUANDO un texto se rechaza por longitud (R11), el orchestrator DEBE registrar
el evento `guardrail` con motivo `input_too_long`.

## R13
CUANDO el texto normalizado (`normalize_text`) de un cliente contiene alguno de
los patrones de `HARNESS_INJECTION_PATTERNS`, el orchestrator DEBE registrar el
evento `guardrail` con motivo `prompt_injection`.

## R14
MIENTRAS un mensaje está marcado como intento de inyección (R13), el
orchestrator NO DEBE invocar el router; la herramienta se resuelve solo por
las rutas por palabra clave y la herramienta por defecto del estado (orden de
R20).

## R15
El orchestrator DEBE pasar al LLM el texto del cliente únicamente delimitado
como dato (`<pregunta>` en RAG y SQL, `<mensaje>` en el router) y neutralizado
contra el cierre de esas etiquetas.

## Router (opcional)

## R16
DONDE `HARNESS_ROUTER_ENABLED=true`, MIENTRAS el estado es `active` o
`no_access` y ninguna ruta por palabra clave aplicó, el orchestrator DEBE pedir
al LLM una decisión con el prompt de `build_router_prompt(state, text)`.

## R17
El prompt de router DEBE listar únicamente las herramientas de
`TOOL_MATRIX[state]` y NO DEBE contener `profile_id`, `username`, `cliente_id`,
tokens de enlace ni datos de credencial.

## R18
`parse_router_answer` DEBE aceptar solo un JSON `{"tool": <ToolName>, "args":
{...}}` cuyos `args` coinciden exactamente con el esquema de la herramienta
(`escalar_a_asesor`: `{"motivo": "user_request" | "frustration"}`; las otras
cinco: `{}`) y DEBE rechazar cualquier otra forma, herramienta desconocida o
clave adicional (p. ej. `cliente_id`, `sql`, `query`).

## R19
SI la salida del router es inválida o el LLM del router falla
(`ServiceUnavailable`) ENTONCES el orchestrator DEBE aplicar la herramienta por
defecto del estado (`active`: `buscar_base_conocimiento`; `no_access`:
ninguna, responde `suspended_reply` como #37).

## R20
DONDE `HARNESS_ROUTER_ENABLED=false` (valor por defecto), el orchestrator NO
DEBE llamar al LLM para enrutar y DEBE resolver la herramienta en este orden:
supresión por palabra clave, asesor por palabra clave, frustración por palabra
clave y herramienta por defecto del estado.

## Identidad y datos propios del cliente

## R21
CUANDO se ejecuta `consultar_mis_datos`, `crear_solicitud_supresion` o
`cerrar_sesion`, el orchestrator DEBE obtener el `cliente_id` exclusivamente de
`active_client_id(contact.id)`, ignorando el texto del cliente, los argumentos
del router y el SQL generado.

## R22
SI se ejecuta `consultar_mis_datos` sin sesión activa ENTONCES el orchestrator
DEBE responder `CLIENT_DATA_UNAVAILABLE_REPLY` con `result = "no_session"` sin
llamar al LLM ni a `client_data`.

## R23
SI `CLIENT_DATA_ENABLED=false` (valor por defecto) ENTONCES `consultar_mis_datos`
DEBE responder `CLIENT_DATA_DISABLED_REPLY` con `result = "disabled"` sin llamar
al LLM ni a `client_data`.

## R24
CUANDO se ejecuta `consultar_mis_datos` habilitado, el orchestrator DEBE generar
el SQL con `build_sql_prompt(texto, CLIENT_DATA_ALLOWLIST)` y validarlo con
`validate_sql(sql, CLIENT_DATA_ALLOWLIST, CLIENT_DATA_VIEWS_SCHEMA,
CLIENT_DATA_MAX_JOINS)`.

## R25
SI `validate_sql` rechaza el SQL (tabla no permitida, vista fuera de la
allowlist, columna no permitida, más de una sentencia u otra forma inválida)
ENTONCES el orchestrator DEBE responder `CLIENT_DATA_REJECTED_REPLY` con
`result = "rejected"` sin llamar a `client_data`.

## R26
CUANDO el SQL validado se ejecuta, el orchestrator DEBE llamar a
`client_data.run(query, cliente_id, max_rows, timeout_ms)` con el `cliente_id`
de R21.

## R27
`PostgresClientDataQuery.run` DEBE ejecutar, en este orden y en la misma
transacción, `SET TRANSACTION READ ONLY`, `SET LOCAL statement_timeout`,
`SELECT set_config(%s, %s, true)` con parámetros (`CLIENT_DATA_RLS_SETTING`,
`cliente_id`) y la consulta validada, y terminar siempre con `ROLLBACK`.

## R28
`PostgresClientDataQuery` NO DEBE interpolar el `cliente_id` en el texto de
ninguna sentencia SQL.

## R29
SI en el primer uso de `PostgresClientDataQuery` algún objeto de
`CLIENT_DATA_ALLOWLIST` no es en `pg_catalog` una vista (`relkind = 'v'`) con
exactamente sus columnas ENTONCES el adaptador DEBE lanzar
`DbQueryUnavailable` sin ejecutar la consulta.

## R30
SI en el primer uso el rol conectado es superusuario o tiene `BYPASSRLS`
ENTONCES `PostgresClientDataQuery` DEBE lanzar `DbQueryUnavailable` sin
ejecutar la consulta.

## R31
SI en el primer uso, con `CLIENT_DATA_RLS_SETTING` fijado a cadena vacía,
alguna vista de la allowlist devuelve al menos una fila ENTONCES
`PostgresClientDataQuery` DEBE lanzar `DbQueryUnavailable` sin ejecutar la
consulta (sonda de RLS, falla cerrado).

## R32
SI `client_data.run` lanza `DbQueryUnavailable` o el LLM de SQL falla ENTONCES
el orchestrator DEBE responder `CLIENT_DATA_UNAVAILABLE_REPLY` con
`result = "unavailable"`.

## R33
CUANDO la consulta devuelve resultado, el orchestrator DEBE responder al
cliente con `format_rows(result, CLIENT_DATA_MAX_REPLY_CHARS,
CLIENT_DATA_TRUNCATED_NOTE)`.

## R34
El orchestrator NO DEBE enviar al LLM filas, conteos ni valores devueltos por
`client_data`.

## R35
SI `CLIENT_DATA_ENABLED=true` y `CLIENT_DATA_DATABASE_URL` está vacío, coincide
con `DATABASE_URL` o con `DB_QUERY_DATABASE_URL`, o `CLIENT_DATA_ALLOWLIST` o
`CLIENT_DATA_RLS_SETTING` no son válidos ENTONCES `Settings` DEBE lanzar un
error de validación al arrancar.

## Supresión

## R36
CUANDO se ejecuta `crear_solicitud_supresion` con sesión activa, el
orchestrator DEBE crear una fila en `suppression_requests` con `id`,
`profile_id` (= `cliente_id`), `contact_id`, `channel`, `status = "pending"` y
`created_at`.

## R37
SI ya existe una solicitud `pending` para el mismo `profile_id` ENTONCES el
orchestrator NO DEBE crear otra y DEBE reutilizar su `id`.

## R38
CUANDO se registra (o reutiliza) la solicitud, el orchestrator DEBE pedir un
traspaso a handover con `reason = "user_request"` y guardar el `case_id`
devuelto en la solicitud.

## R39
CUANDO se registra (o reutiliza) la solicitud, el orchestrator DEBE responder
`SUPPRESSION_REQUEST_REPLY` con `{request_id}` sustituido por el `id` de la
solicitud, sin enviar además `handover_ack_reply`.

## R40
SI se ejecuta `crear_solicitud_supresion` sin sesión activa ENTONCES el
orchestrator NO DEBE crear filas en `suppression_requests` y DEBE escalar con
`escalar_a_asesor` (motivo `suppression`) para que una persona verifique.

## R41
El orchestrator NO DEBE disminuir el número de filas de ninguna tabla del
repositorio al ejecutar cualquiera de las seis herramientas.

## R42
La purga de retención (#27) NO DEBE borrar filas de `suppression_requests`.

## R43
CUANDO el texto normalizado de un cliente en `active` o `no_access` contiene
alguna frase de `HARNESS_SUPPRESSION_KEYWORDS`, el orchestrator DEBE invocar
`crear_solicitud_supresion` con origen `keyword`.

## RAG con fuentes

## R44
CUANDO se ejecuta `buscar_base_conocimiento`, el orchestrator DEBE usar como
consulta de RAG y como `<pregunta>` del LLM el texto original del cliente, no
un texto producido por el router.

## R45
CUANDO se ejecuta `buscar_base_conocimiento`, el orchestrator DEBE validar la
respuesta del LLM con `validate_llm_answer` contra los fragmentos devueltos
por RAG antes de enviarla.

## R60
SI la validación de R45 falla (JSON, forma, sin citas, `chunk_id` ajeno, cita
no literal o número no citado) ENTONCES el orchestrator DEBE responder
`no_answer_reply` y registrar el resultado `invalid_answer` como hoy (#6/#24).

## Escalamiento

## R46
CUANDO el texto de un cliente en `active` o `no_access` coincide con
`HANDOVER_KEYWORDS`, el orchestrator DEBE invocar `escalar_a_asesor` con origen
`keyword` y motivo `user_request`.

## R47
DONDE `HARNESS_FRUSTRATION_ESCALATION=true` (valor por defecto), CUANDO el
texto normalizado de un cliente en `active` contiene alguna frase de
`HARNESS_FRUSTRATION_KEYWORDS`, el orchestrator DEBE invocar `escalar_a_asesor`
con origen `keyword` y motivo `frustration`.

## R48
CUANDO `record_rag_outcome` indica que se alcanzó
`AUTO_HANDOVER_FAILURE_THRESHOLD`, el orchestrator DEBE invocar
`escalar_a_asesor` con origen `rule` y motivo `repeated_failure`.

## R49
CUANDO se ejecuta `escalar_a_asesor`, el orchestrator DEBE registrar el evento
`escalation` con el motivo (`user_request`, `frustration`, `repeated_failure` o
`suppression`).

## R50
CUANDO se ejecuta `escalar_a_asesor`, el orchestrator DEBE enviar a handover un
`HandoverRequest.reason` del contrato vigente: `user_request` para los motivos
`user_request`, `frustration` y `suppression`, y el motivo de fallo original
(`no_relevant_chunks` o `invalid_answer`) para `repeated_failure`.

## R51
CUANDO se ejecuta `escalar_a_asesor` en `no_access`, el orchestrator DEBE
aplicar `ESCALATION_REQUESTED` antes del traspaso, de modo que el estado pase a
`with_advisor` como en #37.

## Estados, consentimiento y sesión

## R52
MIENTRAS el estado es `awaiting_login`, CUANDO llega texto del cliente, el
orchestrator DEBE enviar el recordatorio con enlace invocando
`enviar_link_inicio_sesion` con origen `rule`, sin llamar a `rag`, `llm` ni
`client_data`.

## R53
CUANDO el router elige `cerrar_sesion` y está autorizada, el orchestrator DEBE
cerrar la sesión con `end_client_session(session, "logout", ...)` y responder
`session_closed_reply` con un enlace nuevo, como el comando fijo de #38.

## R54
SI un remitente no tiene consentimiento vigente para la versión actual
ENTONCES el orchestrator NO DEBE crear filas en `tool_calls` ni en
`suppression_requests` (las garantías de #35/#37 no cambian).

## R61
SI un remitente no tiene consentimiento vigente para la versión actual
ENTONCES el orchestrator NO DEBE llamar a `llm`, `rag` ni `client_data`
aunque su texto contenga palabras clave de supresión, asesor, frustración o
patrones de inyección.

## R55
MIENTRAS el estado es `with_advisor`, `new`, `awaiting_consent` o `closed`, el
orchestrator NO DEBE invocar el router ni ejecutar herramientas; se conserva el
comportamiento de #37.

## Evaluación y no regresión

## R56
El orchestrator DEBE incluir una suite de evaluación sin red
(`tests/test_harness_eval.py` con casos en `tests/data/harness_eval_cases.json`)
con al menos dos casos por cada categoría: acceso entre clientes, inyección,
herramienta prohibida por estado, consentimiento y fuentes inválidas.

## R62
Cada caso de la suite de R56 DEBE afirmar la respuesta enviada, la herramienta
y decisión registradas en `tool_calls` (o su ausencia) y qué adaptadores
fueron o no llamados.

## R57
SI un cliente A con sesión activa pide datos de otro cliente B (en el texto,
en los argumentos del router o en un `WHERE cliente_id = '<B>'` del SQL
generado) ENTONCES el orchestrator DEBE llamar a `client_data` solo con el
`cliente_id` de A y la respuesta NO DEBE contener filas de B.

## R58
CUANDO se ejecuta `./init.sh` con la feature implementada, todas las suites
existentes y nuevas DEBEN pasar (incluidas las de #35–#38 sin cambios de
comportamiento con `HARNESS_ROUTER_ENABLED=false` y `CLIENT_DATA_ENABLED=false`).

## Configuración

## R59
El orchestrator DEBE leer de variables de entorno todas las variables nuevas
de la tabla de `design.md`, declaradas en `.env.example` con sus valores por
defecto.

## R63
SI una variable numérica nueva de la tabla de `design.md` está fuera de su
rango ENTONCES `Settings` DEBE lanzar un error de validación al arrancar.
