# Requirements — #74 `servidor_mcp_lectura`

Servicios: **mcp_lectura** (nuevo), **orchestrator**, **rag** (solo consumido).
Cada `R<n>` indica su servicio. Todas las herramientas MCP de esta feature son de
solo lectura.

## Servidor MCP (mcp_lectura)

## R1
El servidor MCP DEBE exponer exactamente las herramientas `buscar_manuales` y
`ofertas_demo`, y ninguna otra.

## R2
El servidor MCP DEBE declarar cada herramienta con la anotación `readOnlyHint=true`.

## R3
CUANDO se ejecuta `ofertas_demo`, el servidor MCP DEBE consultar la base solo con
sentencias `SELECT` parametrizadas dentro de una transacción `READ ONLY`.

## R4
CUANDO se ejecuta `buscar_manuales`, el servidor MCP DEBE limitarse a llamar a
`POST /search` del servicio RAG con `X-Service-Token`, sin ninguna otra ruta.

## R5
El servidor MCP NO DEBE declarar en el esquema de entrada de ninguna herramienta
un campo de identidad (`cliente_id`, `user_id`, `contact_id`, `telegram_user_id`).

## R6
SI una petición al servidor MCP llega sin un `X-Service-Token` válido ENTONCES el
servidor MCP DEBE responder `401` con `{"error": "unauthorized", ...}` sin ejecutar
ninguna herramienta.

## R7
CUANDO llega `GET /health` sin token, el servidor MCP DEBE responder `200` sin
listar herramientas ni datos.

## R8
`docker-compose.yml` NO DEBE publicar ningún puerto (`ports`) del servicio
`mcp_lectura`; solo es accesible por la red interna de compose.

## R9
CUANDO una herramienta termina (con éxito o con error), el servidor MCP DEBE
registrar una fila de auditoría con herramienta, `sha256` de los argumentos, número
de filas devueltas, estado y fecha.

## R10
El registro de auditoría del servidor MCP NO DEBE contener los valores de los
argumentos ni el contenido de las filas devueltas.

## R11
SI falla la escritura de la auditoría ENTONCES el servidor MCP DEBE devolver un
error de herramienta sin entregar los datos consultados.

## R12
CUANDO `ofertas_demo` devuelve filas, el servidor MCP DEBE incluir en cada fila
`es_demo=true` y `etiqueta="DEMOSTRACIÓN"`.

## R13
El esquema de la tabla de ofertas de demostración DEBE declarar `es_demo BOOLEAN
NOT NULL DEFAULT TRUE` con `CHECK (es_demo)` y `etiqueta TEXT NOT NULL`, de modo que
toda fila quede marcada como demostración en los datos.

## Orquestador como cliente MCP (orchestrator)

## R14
`TOOL_MATRIX` DEBE incluir `consultar_herramientas_mcp` únicamente en el estado
`active`.

## R15
MIENTRAS `MCP_ENABLED` es `false`, el orquestador NO DEBE ofrecer
`consultar_herramientas_mcp` en el prompt del router ni contactar al servidor MCP.

## R16
SI el estado del contacto no autoriza `consultar_herramientas_mcp` ENTONCES
`execute_tool` DEBE denegarla, auditarla como `denied` y no contactar al servidor
MCP.

## R17
CUANDO el modelo solicita una herramienta MCP, el orquestador DEBE enviar al
servidor MCP el `cliente_id` de la sesión autenticada del contacto.

## R18
SI los argumentos que propone el modelo incluyen claves que no están en el esquema
de la herramienta (incluido `cliente_id`) ENTONCES el orquestador DEBE descartarlas
antes de llamar al servidor MCP.

## R19
SI el modelo solicita una herramienta que el servidor MCP no listó ENTONCES el
orquestador DEBE rechazar la llamada sin contactar al servidor MCP.

## R20
El orquestador NO DEBE superar `MCP_MAX_TOOL_STEPS` llamadas a herramientas por
mensaje del cliente.

## R21
SI el servidor MCP no está disponible ENTONCES el orquestador DEBE registrar el
evento `mcp_unavailable` y responder con el flujo de `buscar_base_conocimiento`.

## R22
SI el modelo responde sin solicitar ninguna herramienta MCP ENTONCES el orquestador
DEBE responder con el flujo de `buscar_base_conocimiento`.

## R23
CUANDO alguna fila usada para responder trae `es_demo=true`, el orquestador DEBE
añadir a la respuesta el aviso configurable `MCP_DEMO_NOTICE`.

## R24
CUANDO termina `consultar_herramientas_mcp`, el orquestador DEBE auditarla en
`tool_calls` con las herramientas MCP usadas y el total de filas en `detail`, sin
valores de argumentos.

## R25
CUANDO el orquestador consulta al modelo con herramientas, el cliente LLM DEBE usar
`LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY` y enviar las herramientas en el campo
`tools` del endpoint de chat completions.

## R26
CUANDO el contacto pertenece al canal `telegram` o al canal simulado, el
orquestador DEBE producir la misma respuesta para el mismo texto y la misma
sesión de cliente.

## R27
CUANDO un administrador autenticado abre `GET /admin/mcp`, el orquestador DEBE
listar las ofertas de demostración con la etiqueta «DEMOSTRACIÓN» visible en cada
fila.

## R28
SI el servidor MCP no responde ENTONCES `GET /admin/mcp` DEBE mostrar el estado
«no disponible» con `200`, sin trazas.

## R29
SI una persona sin sesión de administrador abre `GET /admin/mcp` ENTONCES el
orquestador DEBE redirigir al inicio de sesión del panel.

## Configuración y documentación

## R30
`.env.example` DEBE declarar `MCP_ENABLED`, `MCP_URL`, `MCP_TIMEOUT_SECONDS`,
`MCP_MAX_TOOL_STEPS`, `MCP_DEMO_NOTICE`, `MCP_DEMO_SEED` y `MCP_DATABASE_URL`.

## R31
`docker-compose.yml` DEBE definir un servicio `ollama` bajo el perfil `ollama`, que
no arranca sin ese perfil.

## R32
`docs/mcp.md` DEBE documentar la configuración del modelo con Ollama local y con
un proveedor remoto usando `LLM_BASE_URL` y `LLM_MODEL`.

## Trazabilidad con el acceptance

| Acceptance | R |
|---|---|
| 1 servidor MCP solo lectura | R1–R5, R12, R13 |
| 2 cliente MCP, TOOL_MATRIX, cliente_id de sesión | R14–R20 |
| 3 no expuesto, token, auditoría | R6–R11 |
| 4 modelo configurable, Ollama | R25, R30–R32 |
| 5 independiente del canal | R26 |
| 6 demostración marcada en datos y panel | R12, R13, R23, R27 |
| 7 MCP caído = como hoy | R21, R22, R28 |
| 8 pruebas con MCP falso, init verde | R1–R29 (pruebas con `FakeMcpClient` y servidor con fakes) |
