# #24 despliegue_produccion — Design

> El Blueprint es **preparación**: nada se despliega ni se crea en Render en
> esta feature. Sin planes, precios ni supuestos de coste: el campo `plan` se
> omite (R7) y lo elige el humano al crear el Blueprint.

## Archivos

| Archivo | Cambio |
|---|---|
| `render.yaml` (nuevo, raíz) | Blueprint (R1–R11). |
| `contracts/lazaro_contracts/production.py` (nuevo) | Utilidades puras de validación (R12–R20). |
| `services/*/*/config.py` | `app_env`, normalización de URL y validador de producción. |
| `services/*/Dockerfile` (4) | `CMD` en forma shell que respeta `${PORT:-8000}`. |
| `scripts/vencer_casos.py` | Normaliza `HANDOVER_URL` y valida `SERVICE_TOKEN` en producción. |
| `scripts/configurar_webhook.py` (nuevo) | Registro de webhook (R23–R27). |
| `.github/workflows/ci.yml` | Job `docker-build` en matriz (R22). |
| `.env.example` | `APP_ENV=development`, `PUBLIC_BASE_URL=`. |
| `requirements-dev.txt` | `PyYAML>=6,<7` (MIT) solo para tests del Blueprint. |
| `docs/despliegue.md` (nuevo) | Procedimiento (R28). |
| `scripts/tests/test_render_blueprint.py`, `scripts/tests/test_configurar_webhook.py`, `services/*/tests/test_production_config.py`, `contracts/tests/test_production.py` | Tests. `scripts/` ya está en `testpaths`. |
| `services/orchestrator/tests/test_public_exposure.py` (nuevo) | Tests de R29, R31 y R32 (no cambia el middleware). |
| `services/orchestrator/orchestrator/admin_routes.py` | `client_ip`: primer valor de `X-Forwarded-For` en vez del último (R32). |
| `services/orchestrator/tests/test_admin.py` | Actualizar `test_forwarded_for_is_used_with_trust` (hoy espera el último valor) al primero (R32). |
| `services/rag/tests/test_security.py`, `services/handover/tests/test_security.py` | Ampliar con R30 si falta alguna ruta. |

## Topología

| Servicio | Tipo Render | Público | Health check |
|---|---|---|---|
| `telegram-gateway` | `web` | Sí (webhook de Telegram) | `healthCheckPath: /health` |
| `orchestrator` | `web` | Sí (panel `/admin` para clientes) | `healthCheckPath: /health` |
| `rag` | `pserv` | No | TCP por defecto |
| `handover` | `pserv` | No | TCP por defecto |
| `timeouts-worker` | `worker` | No | — |
| `lazaro-postgres`, `lazaro-redis` | database / `keyvalue` | No (`ipAllowList: []`) | — |

Al ser `web`, el orchestrator recibe una URL `onrender.com` pública. Toda
su superficie no-admin ya está protegida por el middleware
`verify_service_token` (`orchestrator/main.py`), que deja pasar solo
`/health` y `/admin*`; el panel usa su propia sesión + CSRF (#12). R29–R31
fijan ese comportamiento con tests para que exponer el servicio no abra
las rutas internas. El gateway y handover siguen hablando con el
orchestrator por la red privada (`hostport`), nunca por la URL pública.

## Blueprint (`render.yaml`)

- `envVarGroups`: `lazaro-compartido` con `APP_ENV=production`, `PORT=8000`,
  `SERVICE_TOKEN` (`generateValue: true`) y valores no secretos comunes.
  Los env groups no admiten `sync: false` ni referencias a servicios, por eso
  allí solo van valores fijos y el token generado.
- `databases`: `lazaro-postgres`, `postgresMajorVersion: "16"`, `ipAllowList: []`.
- `services`:
  - `lazaro-redis` `keyvalue`, `ipAllowList: []` (campo obligatorio).
  - `telegram-gateway` `web`, `runtime: docker`, `dockerContext: .`,
    `healthCheckPath: /health`; `REDIS_URL` (fromService keyvalue
    connectionString), `ORCHESTRATOR_URL` (hostport), `TELEGRAM_BOT_TOKEN` y
    `TELEGRAM_WEBHOOK_SECRET` con `sync: false`.
  - `orchestrator` `web`, `runtime: docker`, `dockerContext: .`,
    `healthCheckPath: /health`: `DATABASE_URL` fromDatabase; `RAG_URL`,
    `HANDOVER_URL`, `TELEGRAM_GATEWAY_URL` hostport; `LLM_API_KEY`,
    `LLM_MODEL`, `TELEGRAM_BOT_USERNAME` `sync: false`;
    `ADMIN_TRUST_PROXY_HEADERS` con `value: "true"` (R32). Va en `envVars`
    del orchestrator, **no** en `lazaro-compartido`: solo el panel lo usa.
  - `rag` `pserv`: `DATABASE_URL`; `EMBEDDINGS_API_KEY`, `EMBEDDINGS_MODEL` `sync: false`.
  - `handover` `pserv`: `DATABASE_URL`, `TELEGRAM_GATEWAY_URL`; `ADVISOR_CHAT_IDS` `sync: false`.
  - `timeouts-worker` `worker`, Dockerfile de handover,
    `dockerCommand: python vencer_casos.py --intervalo`, `HANDOVER_URL` hostport.
- `region`: el mismo literal en todos (por defecto `virginia`, la más cercana a
  Colombia; editable en un solo cambio). Requisito de la red privada de Render.
- Health checks: Render solo hace checks HTTP en servicios `web`; los `pserv`
  usan el check TCP por defecto y los workers no tienen. Por eso solo
  gateway y orchestrator llevan `healthCheckPath` (ambos sin token, en
  `PUBLIC_PATHS`).
- Workers solo envían tráfico privado (no reciben), lo que encaja con
  `timeouts-worker` → `handover`.
- pgvector: Render Postgres soporta `CREATE EXTENSION vector`; `rag` ya lo
  ejecuta al iniciar (`rag/adapters/repository.py`). `scripts/db/init` no se
  usa en Render. El procedimiento indica verificarlo.
- `TELEGRAM_WEBHOOK_SECRET` **no** usa `generateValue`: produce base64 con
  `+ / =`, inválidos para `secret_token` de Telegram.

## Validación de producción

`lazaro_contracts/production.py` (sin IO; no cambia ningún contrato HTTP):

```python
PLACEHOLDERS: frozenset[str]
def normalize_service_url(value: str) -> str          # "h:p" -> "http://h:p"; vacío se conserva
def parse_app_env(value: str) -> Literal["development", "production"]  # ValueError si otro
def production_problems(values: Mapping[str, str], required: Iterable[str]) -> list[str]
    # nombres de variables vacías, placeholder, SERVICE_TOKEN < 32,
    # DATABASE_URL con "lazaro:lazaro@"; nunca valores
class ProductionConfigError(ValueError)                 # mensaje: "Configuración de producción inválida: A, B"
```

Cada `Settings` añade `app_env: str = "development"` y un `model_validator(mode="after")`
que aplica `normalize_service_url` a sus `*_url` internas y, si es
producción, lanza `ProductionConfigError`. Se usa `hide_input_in_errors=True`
para que Pydantic no repita valores (R20). Como `Settings()` se construye en
`create_app`, el arranque falla.

| Servicio | Obligatorias en producción | Extra |
|---|---|---|
| telegram_gateway | SERVICE_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, REDIS_URL, ORCHESTRATOR_URL | regex secret (R18) |
| orchestrator | SERVICE_TOKEN, DATABASE_URL, RAG_URL, HANDOVER_URL, TELEGRAM_GATEWAY_URL, LLM_API_KEY, LLM_MODEL | ADMIN_COOKIE_SECURE=true (R19) |
| rag | SERVICE_TOKEN, DATABASE_URL, EMBEDDINGS_API_KEY, EMBEDDINGS_MODEL | — |
| handover | SERVICE_TOKEN, DATABASE_URL, TELEGRAM_GATEWAY_URL | — |
| timeouts_worker | SERVICE_TOKEN, HANDOVER_URL | — |

`ADVISOR_CHAT_IDS` no es obligatoria: handover ya funciona sin asesores.

## Puerto

Dockerfiles: `CMD ["sh", "-c", "exec uvicorn <app> --host 0.0.0.0 --port ${PORT:-8000}"]`.
Compose sigue usando 8000; en Render el env group fija `PORT=8000`, así
`hostport` de los servicios `web` y `pserv` apunta a un puerto conocido.

## IP del cliente tras el proxy (R32)

En Render todas las peticiones llegan por su proxy, así que
`request.client.host` es la misma para todos: con el default `false`, 5 fallos
de cualquiera (`admin_login_max_attempts`) bloquearían el login de todos los
clientes 15 minutos. Render documenta que el **primer** valor de
`X-Forwarded-For` es la IP del cliente (artículo DDoS y hilo de soporte
citados en `requirements.md`); el último es un salto interno del proxy.

```python
def client_ip(request: Request, settings: Settings) -> str:
    if settings.admin_trust_proxy_headers:
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client is not None else ""
```

Fuera de Render (`compose`, tests) el default sigue en `false` y la cabecera se
ignora (comportamiento de #12, `test_forwarded_for_is_ignored_without_trust`).

## Script del webhook

`scripts/configurar_webhook.py [--solo-consultar] [--drop-pending]`:
lee `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_BASE_URL` del
entorno (nunca de argumentos, para no dejarlos en el historial); valida
https y regex; `POST setWebhook` con `allowed_updates=["message"]`; luego
`getWebhookInfo`. Toda excepción de `httpx` se captura y se imprime solo el
tipo y el código HTTP (la URL de la API contiene el token). Función
`main(argv, env, client)` inyectable para tests con `httpx.MockTransport`.

## CI

Job nuevo `docker-build` con `strategy.matrix.service: [telegram_gateway, orchestrator, rag, handover]`:
`docker build -f services/${{ matrix.service }}/Dockerfile .` (sin `push`, sin credenciales).

## Alternativas descartadas

- **Duplicar la validación en cada `config.py`**: cuatro copias divergentes;
  se usa un módulo puro en `lazaro_contracts`, el único código compartido permitido.
- **Orchestrator como `pserv` (solo gateway público)**: dejaría el panel
  `/admin` inaccesible para los clientes, que es un requisito de producto.
- **Servicio `web` separado solo para el panel**: duplicaría sesión, BD y
  despliegue del orchestrator; el middleware actual ya separa admin
  (sesión/CSRF) de rutas internas (`X-Service-Token`), verificado por R29–R31.
- **Copiar `SERVICE_TOKEN` con `fromService` + `envVarKey`**: no documentado
  para variables personalizadas; el env group con `generateValue` sí lo está.
- **Último valor de `X-Forwarded-For`** (comportamiento actual de #12): en
  Render es la IP del proxy, compartida por todos, y reproduciría el bloqueo
  global del login. Se usa el primero, que Render fija como cliente.
- **`ADMIN_TRUST_PROXY_HEADERS` en el env group compartido**: los demás
  servicios no lo leen; se limita al orchestrator.

## Dependencias nuevas

- `PyYAML>=6,<7` (MIT), solo en `requirements-dev.txt`. Lo instala el humano.

## Supuestos a confirmar

- `APP_ENV` (default `development`), `PUBLIC_BASE_URL` (vacío) en `.env.example`.
- Región `virginia` (configurable en `render.yaml`).
- Longitud mínima 32 para `SERVICE_TOKEN` y `TELEGRAM_WEBHOOK_SECRET`.
- `ADMIN_TRUST_PROXY_HEADERS=true` solo en Render; se toma el **primer** valor
  de `X-Forwarded-For` (IP del cliente según Render). Default `false` fuera de Render.
