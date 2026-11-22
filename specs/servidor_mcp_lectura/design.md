# Design — #74 `servidor_mcp_lectura`

## 1. Resumen

```
cliente (cualquier canal) → orquestador (núcleo, mensaje normalizado)
   router elige `consultar_herramientas_mcp` (solo estado active, MCP_ENABLED)
        │  McpClient (SDK mcp, streamable-http, X-Service-Token + X-Cliente-Id)
        ▼
   mcp_lectura (red interna, sin puertos publicados)
        ├─ buscar_manuales → POST /search del RAG (X-Service-Token)
        └─ ofertas_demo    → SELECT en demo_ofertas (READ ONLY)
        └─ auditoría → tabla mcp_auditoria
   modelo (LLM_BASE_URL / LLM_MODEL: Ollama local o proveedor remoto)
```

El orquestador no deja que el modelo toque nada fuera de la lista que publica el
servidor MCP. El modelo nunca ve ni fija `cliente_id`.

## 2. Dependencias nuevas (las instala el humano antes de implementar)

- `mcp>=1.2,<2` — SDK oficial de Model Context Protocol, licencia **MIT**
  (https://github.com/modelcontextprotocol/python-sdk). Se añade a
  `services/mcp_lectura/requirements.txt` y a `services/orchestrator/requirements.txt`.
  No se copia código del SDK; solo se usa como librería. El implementer verifica la
  API de la versión instalada (`mcp.server.fastmcp.FastMCP`,
  `mcp.client.streamable_http.streamablehttp_client`, `mcp.ClientSession`) y la
  ajusta sin cambiar los requisitos.
- Imagen `ollama/ollama` (MIT) solo en el perfil opcional `ollama`.
- Sin otras dependencias: el servidor reutiliza `httpx`, `pg8000`, `uvicorn`.

## 3. Archivos

### Nuevo servicio `services/mcp_lectura/`

- `Dockerfile`, `requirements.txt` (patrón del orquestador; copia `lazaro_contracts`).
- `mcp_lectura/config.py` — `Settings` (pydantic-settings): `SERVICE_TOKEN`,
  `RAG_URL`, `MCP_DATABASE_URL` (por defecto `DATABASE_URL`), `MCP_DEMO_SEED`
  (por defecto `false`), `MCP_MAX_ROWS` (por defecto 20), `HTTP_TIMEOUT_SECONDS`.
- `mcp_lectura/tools.py` — lógica pura de las herramientas:
  ```python
  READ_ONLY_TOOLS: tuple[str, ...] = ("buscar_manuales", "ofertas_demo")
  FORBIDDEN_INPUT_FIELDS = frozenset({"cliente_id","user_id","contact_id","telegram_user_id"})
  DEMO_LABEL = "DEMOSTRACIÓN"
  class ToolResult(BaseModel): rows: list[dict]; demo: bool
  def buscar_manuales(consulta: str, rag: RagSearch, top_k: int) -> ToolResult
  def ofertas_demo(destino: str, desde: date | None, hasta: date | None,
                   store: DemoOffersStore, max_rows: int) -> ToolResult
  def args_sha256(args: Mapping[str, object]) -> str   # JSON canónico, sin valores
  ```
- `mcp_lectura/adapters.py` — `RagSearch` (Protocol) + `HttpRagSearch` (httpx,
  `POST /search`) + `FakeRagSearch`; `DemoOffersStore` (Protocol) +
  `PostgresDemoOffers` (cada consulta: `SET TRANSACTION READ ONLY`, `SELECT ...
  WHERE destino ILIKE %s AND valido_hasta >= %s AND valido_desde <= %s LIMIT %s`,
  parámetros, `ROLLBACK`) + `FakeDemoOffers`; `AuditSink` (Protocol) +
  `PostgresAuditSink` + `FakeAuditSink`.
- `mcp_lectura/schema.py` — DDL idempotente (`CREATE TABLE IF NOT EXISTS`):
  ```sql
  demo_ofertas(id TEXT PK, destino TEXT NOT NULL, titulo TEXT NOT NULL,
    precio_cop INTEGER NOT NULL, valido_desde DATE NOT NULL, valido_hasta DATE NOT NULL,
    es_demo BOOLEAN NOT NULL DEFAULT TRUE CHECK (es_demo),
    etiqueta TEXT NOT NULL DEFAULT 'DEMOSTRACIÓN')
  mcp_auditoria(id BIGSERIAL PK, herramienta TEXT NOT NULL, args_sha256 TEXT NOT NULL,
    filas INTEGER NOT NULL, estado TEXT NOT NULL, cliente_sha256 TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL)
  ```
  y `SEED_OFFERS` (3 ofertas ficticias, p. ej. Melgar) insertadas solo si
  `MCP_DEMO_SEED=true` (`ON CONFLICT DO NOTHING`). Las filas semilla dicen
  «Oferta de demostración» en el título; nunca datos de Lázaro.
- `mcp_lectura/server.py` — `build_mcp(deps) -> FastMCP` registra las dos
  herramientas con `annotations=ToolAnnotations(readOnlyHint=True)`; un decorador
  `audited(name)` calcula `args_sha256`, cuenta filas, escribe la auditoría
  (`finally`) y, si la auditoría falla, lanza `ToolError` sin devolver datos (R11).
  El `cliente_id` se lee del encabezado `X-Cliente-Id` de la petición MCP y solo se
  audita como `sha256` (no es un argumento de la herramienta).
- `mcp_lectura/main.py` — `create_app(settings, deps) -> Starlette`: monta
  `mcp.streamable_http_app()` y un middleware que exige `X-Service-Token`
  (`hmac.compare_digest`; si falta o no coincide: `401` con
  `{"error":"unauthorized","message":"Falta X-Service-Token o no es válido."}`).
  `GET /health` queda exento y no lista nada.
- `services/mcp_lectura/tests/` — ver `tasks.md`.

### Orquestador

- `orchestrator/harness.py`: añadir `"consultar_herramientas_mcp"` a `ToolName`,
  `TOOL_NAMES`, `TOOL_MATRIX[ACTIVE]` y `_TOOL_DESCRIPTIONS`; `build_router_prompt`
  recibe `mcp_enabled: bool = True` y excluye esa herramienta si es `False`
  (R15). `parse_router_answer` acepta `args == {}` para ella.
- `orchestrator/adapters/mcp.py`:
  ```python
  class McpToolSpec(BaseModel): name: str; description: str; input_schema: dict
  class McpUnavailable(ServiceUnavailable): ...
  class McpCallResult(BaseModel): rows: list[dict]; demo: bool
  class McpClient(Protocol):
      def list_tools(self) -> list[McpToolSpec]
      def call_tool(self, name: str, args: Mapping[str, object], cliente_id: str) -> McpCallResult
  class HttpMcpClient   # SDK mcp; una sesión corta por operación; headers
                        # X-Service-Token y X-Cliente-Id; asyncio.run en hilo sin loop
  class FakeMcpClient   # tools/resultados en memoria; fail=True; registra llamadas
  ```
  Cualquier error de red, protocolo o `isError` → `McpUnavailable`.
- `orchestrator/adapters/llm.py`: nuevo método
  `LLMClient.complete_with_tools(system, user, tools, call_tool, max_steps) -> str`:
  `HttpLLMClient` envía `tools` (formato OpenAI `function`) a
  `{LLM_BASE_URL}/chat/completions`, atiende `tool_calls` llamando a `call_tool(name,
  args) -> str` (JSON) hasta `max_steps`, y devuelve el texto final. `FakeLLM` y
  `ScriptedLLM` lo implementan con una cola de pasos (`ToolStep(name, args)` y texto
  final). Ollama y los proveedores remotos usan el mismo formato compatible.
- `orchestrator/domain.py`: `_tool_mcp(ctx, settings, adapters) -> tuple[str,str]`
  registrado en `_TOOL_EXECUTORS`:
  1. `cliente_id = active_client_id(...)`; sin sesión → flujo RAG.
  2. `tools = adapters.mcp.list_tools()`; `McpUnavailable` → `add_event(contact.id,
     "mcp_unavailable", ...)`, `logger.error`, `return _tool_rag(...)` (R21).
  3. `call_tool(name, args)`: rechaza nombres fuera de `tools` (R19); filtra `args`
     a las claves de `input_schema.properties` (R18); llama
     `adapters.mcp.call_tool(name, args, cliente_id)` (R17); cuenta pasos (R20) y
     acumula `rows` y `demo`.
  4. `adapters.llm.complete_with_tools(...)`; si no hubo ninguna llamada → `_tool_rag`
     (R22). Si hubo, envía el texto + `settings.mcp_demo_notice` cuando `demo` (R23)
     y devuelve `("ok", f"mcp_tools=a,b;rows=N")` (R24).
  5. Si el modelo devuelve texto vacío tras llamar herramientas → `_processing_error`
     como `_tool_rag`.
  El texto de usuario y las filas viajan al modelo como datos delimitados; el
  prompt de sistema reutiliza las reglas del router («no inventar, solo con los
  resultados, sin identidad»).
- `orchestrator/config.py`: `mcp_enabled=False`, `mcp_url="http://mcp_lectura:8000/mcp"`,
  `mcp_timeout_seconds=10`, `mcp_max_tool_steps=3` (1–6), `mcp_demo_notice` (texto
  por defecto «Ejemplo de DEMOSTRACIÓN: no son ofertas reales de Lázaro Software.»).
  `Adapters.mcp` (por defecto `FakeMcpClient()`); `build_default_adapters` usa
  `HttpMcpClient` si `MCP_ENABLED`. El router recibe `mcp_enabled`.
- `orchestrator/mcp_admin.py` + ruta en `admin_routes.py`: `GET /admin/mcp` (solo
  sesión admin, `_require_session`) llama `list_tools`/`call_tool("ofertas_demo",
  {})` y renderiza tabla con badge «DEMOSTRACIÓN» por fila; si `McpUnavailable`,
  muestra «no disponible» (R27–R29). El `cliente_id` de esta llamada es el literal
  `"admin-panel"` (la herramienta no lo usa para filtrar).

### Infraestructura y docs

- `docker-compose.yml`: servicio `mcp_lectura` (build propio, `env_file`, `expose:
  ["8000"]`, sin `ports`, healthcheck `/health`, `depends_on` postgres, rag) y
  servicio `ollama` (`profiles: ["ollama"]`, volumen `ollama_data`, sin `ports`).
- `.env.example`: `MCP_ENABLED=false`, `MCP_URL=http://mcp_lectura:8000/mcp`,
  `MCP_TIMEOUT_SECONDS=10`, `MCP_MAX_TOOL_STEPS=3`, `MCP_DEMO_NOTICE=...`,
  `MCP_DEMO_SEED=false`, `MCP_DATABASE_URL=` (vacío = `DATABASE_URL`); comentario
  Ollama: `LLM_BASE_URL=http://ollama:11434/v1`, `LLM_API_KEY=ollama`.
- `docs/mcp.md`: arquitectura, herramientas, seguridad, Ollama
  (`docker compose --profile ollama up -d ollama` + `ollama pull <modelo>`) y proveedor
  remoto. `docs/architecture.md` y `contracts/CONTRATOS.md`: una nota breve del
  servicio y de la herramienta (no hay modelos HTTP nuevos entre servicios: el
  protocolo es MCP).
- `render.yaml` NO cambia: `MCP_ENABLED=false` en pruebas desplegadas.

## 4. Excepciones

Reutiliza `ServiceUnavailable` (nueva subclase `McpUnavailable`), `ToolError` del SDK
en el servidor y `{"error","message"}` en `401`.

## 5. Alternativas descartadas

1. **Llamar a las herramientas MCP desde la herramienta existente `consultar_mis_datos`
   (#39)**: mezcla texto-a-SQL con MCP y rompe su contrato; se añade una herramienta
   propia en `TOOL_MATRIX`.
2. **Pasar `cliente_id` como argumento de herramienta y validarlo**: el modelo lo
   podría manipular; se envía por encabezado fuera del esquema y se descarta
   cualquier clave no declarada.
3. **Transporte stdio con subproceso**: obliga a `subprocess` en el orquestador
   (prohibido por `docs/architecture.md` §4) y no permite `X-Service-Token`; se usa
   streamable HTTP interno.
4. **Reusar la conexión de texto-a-SQL (#26) para las ofertas**: acopla vistas con
   demo; se usa una tabla `demo_ofertas` propia y marcada.

## 6. Supuestos a confirmar (valores por defecto configurables)

- S1 La herramienta MCP solo está disponible en `active` (cliente autenticado);
  configurable ampliando `TOOL_MATRIX` en una feature futura.
- S2 `MCP_ENABLED=false` por defecto; sin él el bot se comporta como hoy.
- S3 Ofertas de demostración fijas (tabla `demo_ofertas`, semilla opcional con
  `MCP_DEMO_SEED`); no hay API de Lázaro y nunca se simula como real.
- S4 Máximo 3 llamadas a herramientas por mensaje y 20 filas por herramienta.
- S5 Una sesión MCP por operación (sin pool): más simple y el `cliente_id` por
  encabezado nunca se comparte entre contactos.
- S6 La auditoría guarda `sha256` del `cliente_id`, no el valor.
- S7 Modelo local sugerido en docs: uno con soporte de `tools` en Ollama; el nombre
  es solo ejemplo, se fija con `LLM_MODEL`.
