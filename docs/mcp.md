# Servidor MCP de solo lectura (#74)

El servicio `mcp_lectura` expone herramientas de **solo lectura** al modelo de IA
mediante el SDK oficial de Model Context Protocol (`mcp`, licencia MIT). El
orquestador actúa como cliente MCP y decide en código qué herramientas ofrece
según el estado de la conversación (`TOOL_MATRIX`).

```
cliente (cualquier canal) → orquestador → McpClient → mcp_lectura
                                                     ├─ buscar_manuales → POST /search (RAG)
                                                     └─ ofertas_demo    → SELECT READ ONLY
                                                     └─ auditoría       → mcp_auditoria
```

## Herramientas

| Herramienta | Qué hace | Solo lectura |
|---|---|---|
| `buscar_manuales` | Llama a `POST /search` del servicio RAG con `X-Service-Token`. | Sí (`readOnlyHint=true`) |
| `ofertas_demo` | Consulta `demo_ofertas` con un `SELECT` parametrizado en transacción `READ ONLY`. | Sí (`readOnlyHint=true`) |

No hay ninguna herramienta que cree, modifique o borre. El `cliente_id` no es un
argumento de herramienta: el orquestador lo envía en el encabezado
`X-Cliente-Id` desde la sesión autenticada y el servidor solo guarda su `sha256`
en la auditoría.

## Ofertas de DEMOSTRACIÓN

`demo_ofertas` es una tabla ficticia para demostrar el flujo (por ejemplo,
«¿tienes algo para Melgar esta semana?»). Toda fila lleva `es_demo=true` y
`etiqueta='DEMOSTRACIÓN'`; la restricción `CHECK (es_demo)` impide guardar
filas sin esa marca. No se presentan como datos reales de Lázaro Software.

La semilla de ejemplo solo se inserta con `MCP_DEMO_SEED=true` al arrancar el
servicio. Con `MCP_DEMO_SEED=false` la tabla queda vacía y el panel muestra que
no hay ofertas de demostración.

## Seguridad

- El servicio **no publica puertos**: en `docker-compose.yml` solo usa
  `expose: ["8000"]` y es accesible por la red interna de compose.
- Toda petición exige `X-Service-Token` igual a `SERVICE_TOKEN`; sin él,
  `401 {"error": "unauthorized"}` y no se ejecuta ninguna herramienta.
- `GET /health` es público y no lista herramientas ni datos.
- Cada llamada (con éxito o error) deja una fila en `mcp_auditoria` con
  herramienta, `sha256` de los argumentos, filas devueltas, estado, `sha256` del
  `cliente_id` y fecha. Nunca guarda los valores de los argumentos ni el
  contenido de las filas.
- Si la auditoría no se puede escribir, la herramienta devuelve un error y no
  entrega los datos consultados.
- Cualquier error de red, protocolo o `isError` del servidor MCP se trata como
  `mcp_unavailable`: el orquestador registra el evento y responde con el flujo
  normal de `buscar_base_conocimiento`.

## Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `MCP_ENABLED` | `false` | Ofrece la herramienta MCP al router y contacta al servidor. |
| `MCP_URL` | `http://mcp_lectura:8000/mcp` | Endpoint streamable HTTP del servidor MCP. |
| `MCP_TIMEOUT_SECONDS` | `10` | Timeout de las llamadas MCP. |
| `MCP_MAX_TOOL_STEPS` | `3` | Máximo de llamadas a herramientas por mensaje (1–6). |
| `MCP_DEMO_NOTICE` | texto de DEMOSTRACIÓN | Aviso añadido cuando se usan filas `es_demo=true`. |
| `MCP_DEMO_SEED` | `false` | Inserta las ofertas ficticias al arrancar `mcp_lectura`. |
| `MCP_DATABASE_URL` | vacío | DSN del servidor MCP; vacío usa `DATABASE_URL`. |
| `MCP_MAX_ROWS` | `20` | Filas máximas por herramienta. |

## Configuración del modelo

El modelo se configura con `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY`. El
cliente habla el formato de chat completions compatible con OpenAI y envía las
herramientas en el campo `tools`.

### Ollama en local

El servicio `ollama` está bajo el perfil opcional `ollama` y no arranca con un
`docker compose up` normal:

```bash
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull llama3.1
```

Ajusta en `.env`:

```
LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=llama3.1
LLM_API_KEY=ollama
```

Usa un modelo que soporte herramientas (`tools`) en Ollama. El nombre es solo
un ejemplo.

### Proveedor remoto

Cualquier proveedor compatible con chat completions funciona con el mismo
formato:

```
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=<modelo-del-proveedor>
LLM_API_KEY=<clave>
```
