# Arquitectura — Qué significa "hacer un buen trabajo"

> Este documento define el estándar de calidad. El `reviewer` evalúa el
> código contra este archivo. Si no está aquí (o en `docs/conventions.md`),
> no es un requisito. El contexto de negocio está en `docs/proyecto.md`.

## 1. Mapa del monorepo

```
contracts/                 # Contratos entre servicios (feature 1)
├── CONTRATOS.md           # Documento legible: rutas, campos, errores
├── lazaro_contracts/      # Modelos Pydantic compartidos (request/response)
└── tests/
services/
├── telegram_gateway/      # Canal Telegram: recibe updates, envía mensajes
├── orchestrator/          # Cerebro: contacto, conversación, decide qué hacer
├── rag/                   # Manuales: ingesta, fragmentos, búsqueda pgvector
└── handover/              # Traspaso a asesor: casos, avisos, tiempo de espera
eval/                      # Evaluación con preguntas de ejemplo (feature 8)
scripts/                   # Utilidades (p. ej. cargar_manual.py)
docker-compose.yml         # Postgres (pgvector), Redis y los servicios
```

Cada servicio tiene la misma forma:

```
services/<servicio>/
├── <servicio>/            # Paquete Python (mismo nombre que la carpeta)
│   ├── main.py            # App FastAPI: rutas HTTP, sin lógica de negocio
│   ├── config.py          # Settings leídas de variables de entorno
│   ├── domain.py          # Lógica pura (sin red, sin base de datos)
│   └── adapters/          # Clientes externos: DB, Redis, Telegram, LLM, otros servicios
├── tests/
├── requirements.txt       # Dependencias de ejecución del servicio
└── Dockerfile
```

**No se añaden servicios, carpetas de primer nivel ni capas nuevas** sin que
una feature de `feature_list.json` lo pida y su `design.md` lo justifique.

## 2. Tecnología fijada

| Pieza              | Elección                                             |
|--------------------|------------------------------------------------------|
| Lenguaje           | Python 3.12 (mínimo 3.11)                            |
| Web                | FastAPI + Uvicorn                                    |
| Modelos de datos   | Pydantic v2                                          |
| Cliente HTTP       | httpx                                                |
| Base de datos      | PostgreSQL 16 con extensión pgvector                 |
| Caché / colas      | Redis                                                |
| Tests              | pytest (+ `fastapi.testclient`)                      |
| Contenedores       | Docker + Docker Compose                              |
| CI / despliegue    | GitHub Actions → Render (pruebas)                    |

Cualquier dependencia nueva (librería de PDF, de Word, driver de Postgres,
SDK del proveedor de IA…) se declara en el `design.md` de la feature que la
necesita, con versión acotada y licencia compatible (MIT, BSD, Apache 2.0,
PSF). El agente solo instala lo que está en `requirements.txt` y en el
`design.md` aprobado, siempre dentro del `.venv` del proyecto. Licencias GPL/AGPL: prohibidas.

## 3. Principios

1. **Microservicios que se hablan solo por HTTP + JSON.** Un servicio nunca
   importa código de otro servicio ni lee su base de datos. Lo único
   compartido es `contracts/lazaro_contracts` (modelos Pydantic).
2. **Contratos primero.** Toda ruta entre servicios está en
   `contracts/CONTRATOS.md` y tiene su modelo en `lazaro_contracts`. Cambiar
   un contrato es una feature propia, no un efecto colateral.
3. **Capas dentro de cada servicio.** `main.py` (HTTP) → `domain.py`
   (decisiones) → `adapters/` (mundo exterior). `domain.py` no hace IO.
4. **Todo lo externo detrás de una interfaz inyectable.** Telegram, el
   proveedor de IA (LLM y embeddings), Postgres, Redis y los demás servicios
   se usan a través de un adaptador con una versión falsa (`Fake…`) para
   tests. Así los tests no necesitan red, claves ni Docker.
5. **Configuración solo por variables de entorno** (`config.py` con
   Pydantic Settings o `os.environ`). Ningún valor secreto ni URL fija en el
   código. Toda variable nueva se añade a `.env.example`.
6. **Idempotencia.** Telegram reenvía mensajes (Render tarda en despertar):
   cada mensaje lleva un identificador único y se descartan los repetidos.
7. **Errores explícitos.** Respuestas de error siempre con forma
   `{"error": "<codigo>", "message": "<texto>"}` y el código HTTP adecuado.
   Nada de stack traces hacia el usuario ni hacia otros servicios.
8. **Autenticación entre servicios.** Toda ruta interna exige el encabezado
   `X-Service-Token` igual a `SERVICE_TOKEN`; sin él, `401`. Excepción:
   `GET /health` y el webhook de Telegram (que valida
   `TELEGRAM_WEBHOOK_SECRET`).
9. **Registro de eventos.** Las decisiones importantes (respuesta con RAG,
   rechazo, traspaso, aviso a asesor) se guardan como eventos con fecha,
   contacto y motivo.

## 4. Seguridad (no negociable)

- **El bot no inventa.** Solo responde con fragmentos que superen el umbral
  de similitud y con citas validadas; si no, rechazo fijo y oferta de asesor.
- **El texto es dato, nunca instrucción.** Mensajes de usuarios y fragmentos
  de manuales se pasan al modelo delimitados como datos. El modelo **no
  tiene herramientas** que escriban en la base de datos, ejecuten código o
  SQL, ni llamen a URLs arbitrarias.
- **Nadie ejecuta código a través del bot.** No se usa `eval`, `exec`,
  `subprocess`, `pickle` de datos externos ni SQL construido con texto del
  usuario (siempre parámetros).
- **Un cliente nunca consulta la base de datos.** (La consulta en lenguaje
  natural es una feature posterior; ver `docs/proyecto.md` §6.)
- **Secretos.** Solo en `.env` (ignorado por git). `.env.example` con nombres
  y valores vacíos o de ejemplo. Los agentes no leen `.env`.
- **Datos personales mínimos** (Ley 1581): guardar solo lo necesario para
  atender (ids de Telegram, mensajes de la conversación, casos).

## 5. Licencias y código de terceros

- Se puede copiar código solo de repos con licencia **MIT o Apache 2.0**
  (principal: rag-support-bot, MIT). Cada copia se anota en
  `THIRD_PARTY_NOTICES.md` y el archivo conserva el aviso original arriba.
- Repos **sin archivo de licencia** (crm_bot, dbchatbot, NURA…): solo
  inspiración, cero copia.
- **AGPL** (Helpdock): ni copia ni adaptación cercana.

## 6. Qué NO hacer

- No usar `print()` para registrar: usar `logging`.
- No mezclar IO con decisiones en `domain.py`.
- No llamar a servicios reales (Telegram, proveedor de IA) desde los tests.
- No añadir paneles web, clasificador, consulta a la base de datos ni
  edición de fragmentos hasta que su feature exista en `feature_list.json`.
- No resolver una duda abierta de `docs/proyecto.md` §12 inventando: se
  convierte en un supuesto configurable documentado en `design.md`.
