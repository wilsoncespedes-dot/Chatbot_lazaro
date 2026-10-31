# Design — orquestador_basico

## Archivos

Crear en `services/orchestrator/orchestrator/`:

- `adapters/repository.py` — `Repository` (Protocol), `PostgresRepository` (pg8000, SQL siempre parametrizado, `CREATE TABLE IF NOT EXISTS` en el primer uso, conexión perezosa), `FakeRepository` (listas/dicts en memoria; expone `contacts`, `messages`, `events`, `processed`).
- `adapters/rag.py` — `RagClient` (Protocol), `HttpRagClient` (httpx, `POST {RAG_URL}/search`), `FakeRagClient` (`results`, `fail`, `calls`).
- `adapters/llm.py` — `LLMClient` (Protocol), `HttpLLMClient` (httpx, endpoint compatible con chat completions de `LLM_BASE_URL`, sin SDK), `FakeLLM` (`reply`, `fail`, `calls`).
- `adapters/gateway.py` — `GatewayClient` (Protocol), `HttpGatewayClient` (`POST {TELEGRAM_GATEWAY_URL}/send`), `FakeGatewayClient` (`sent`, `fail`).
- `adapters/handover.py` — `HandoverClient` (Protocol), `HttpHandoverClient` (`POST {HANDOVER_URL}/handover`), `FakeHandoverClient` (`requests`, `status`, `fail`).

Modificar:

- `config.py` — añadir `database_url`, `rag_url`, `handover_url`, `telegram_gateway_url`, `llm_api_key`, `llm_model`, `llm_base_url`, `http_timeout_seconds=10`, `rag_top_k=5` (validado 1..20), `no_answer_reply`, `handover_ack_reply`, `error_reply`, `handover_keywords` (texto separado por comas) y la propiedad `handover_keyword_list`.
- `domain.py` — excepciones, funciones puras, `Adapters` y `process_message` (la lógica de decisión; todo el IO entra por los adaptadores inyectados, igual que en `telegram_gateway`).
- `main.py` — `create_app(settings=None, adapters=None)`, ruta `POST /messages`. Con `adapters=None` construye los adaptadores reales de forma perezosa (sin conectar al importar).
- `requirements.txt` — añadir `httpx` y `pg8000`.
- `/.env.example` — añadir `LLM_BASE_URL`, `NO_ANSWER_REPLY`, `HANDOVER_ACK_REPLY`, `ERROR_REPLY`, `HANDOVER_KEYWORDS` (el resto ya existe).
- `tests/test_orchestrator_app.py` — actualizar `test_requirements_txt_matches_design` (R5 del esqueleto) para aceptar las dependencias nuevas.
- Tests nuevos: `tests/fakes.py` (reexporta fakes), `tests/conftest.py`, `tests/test_messages.py`, `tests/test_decisions.py`, `tests/test_security.py`, `tests/test_adapters.py`, `tests/test_config.py`.

## Firmas

```python
# domain.py
class Contact(BaseModel): id: str; telegram_user_id: int; chat_id: int
class ServiceUnavailable(Exception): ...        # interna; la lanzan los adaptadores HTTP/LLM

@dataclass
class Adapters:  # repository, rag, llm, gateway, handover, clock, new_id
    ...

def normalize_text(text: str) -> str
    # minúsculas, sin tildes (NFKD), espacios colapsados
def is_handover_request(text: str, keywords: list[str]) -> bool
def build_llm_prompt(question: str, chunks: list[SearchResult]) -> tuple[str, str]
    # (system, user); cierra etiquetas: sustituye "</pregunta>" y "</fragmento" por texto inerte
def process_message(request: MessageRequest, settings: Settings, adapters: Adapters) -> None

# adaptadores
class Repository(Protocol):
    def mark_update_if_new(self, update_id: int) -> bool
    def get_or_create_contact(self, telegram_user_id: int, chat_id: int, now: datetime) -> Contact
    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None
    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]   # cronológico
    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None
class RagClient(Protocol):      def search(self, query: str, top_k: int) -> list[SearchResult]
class LLMClient(Protocol):      def complete(self, system: str, user: str) -> str
class GatewayClient(Protocol):  def send(self, chat_id: int, text: str) -> None
class HandoverClient(Protocol): def request(self, req: HandoverRequest) -> HandoverResponse
```

Los adaptadores HTTP lanzan `ServiceUnavailable` ante error de red, timeout o código no 2xx; `process_message` la captura. Las rutas se declaran con `def` (hilos de Starlette) porque httpx y pg8000 son síncronos.

## Flujo

`POST /messages` (síncrono): `repository.mark_update_if_new(update_id)`; si ya existía → `202 duplicate` (R2). Si es nuevo → `202 accepted` y `process_message` se ejecuta con `BackgroundTasks` tras enviar la respuesta (R1). Marcar antes de procesar es deliberado: ante un fallo no se reprocesa (mismo criterio que el gateway); el cliente recibe `ERROR_REPLY` donde es posible.

`process_message`:

1. `get_or_create_contact`; `add_message(user)` con `received_at` (R5-R7).
2. Si `is_handover_request` → traspaso `user_request` (R19, R20); fin.
3. `rag.search(text, RAG_TOP_K)`; fallo → `ERROR_REPLY` + evento `processing_error/rag_unavailable` (R23).
4. Lista vacía → evento `no_results`, `send(NO_ANSWER_REPLY)`, traspaso `no_relevant_chunks` (R10, R13-R15).
5. Con fragmentos → `llm.complete(*build_llm_prompt(...))`; vacío o fallo → `ERROR_REPLY` + evento `processing_error/llm_failed` (R24); si no, evento `rag_answer/chunks_found` y `send(answer)` (R9, R16-R18).
6. Traspaso: `add_event(handover)`, `last_messages(contact, 10)`, `handover.request(HandoverRequest(case_id=new_id(), ...))`. `notified` y motivo `user_request` → `send(HANDOVER_ACK_REPLY)`. `no_advisors` o fallo → evento `handover_failed` (R11, R21, R22, R25).
7. Cada `send` correcto → `add_message(bot)`; fallo → log y sigue (R8, R26).

Tipos de evento: `rag_answer`, `no_results`, `handover`, `handover_failed`, `processing_error`. Tabla `events(id, contact_id, type, reason, at)`; tablas `contacts`, `messages(contact_id, role, text, at)` y `processed_updates(update_id primary key)`. El rol `advisor` del contrato queda para la feature 7.

## Seguridad

- El LLM solo recibe `complete(system, user) -> str`; sin herramientas ni acceso a la base (R28). Prompt: instrucción de sistema que declara `<pregunta>` y `<fragmento>` como datos; el texto del usuario y de los fragmentos se escapa para no cerrar etiquetas (R17).
- Test estático que recorre los `.py` del paquete buscando `eval(`, `exec(`, `subprocess`, `pickle` (R29); test del `PostgresRepository` con una conexión DB-API falsa que comprueba que el texto del cliente solo aparece en los parámetros, nunca en la sentencia.
- Los logs usan `logger.error("...", extra)` con ids y códigos, nunca el texto (R30). Nota: R30 no viene del `acceptance` sino de `docs/architecture.md` §4 (datos personales mínimos); se mantiene como restricción derivada.

## Excepciones

Se reutiliza `DomainError`. Se añade `ServiceUnavailable` (interna, nunca llega al cliente). Los errores `401/422/500` los dan los handlers existentes de `main.py`.

## Alternativas descartadas

- **Procesar de forma síncrona antes de responder `202`.** Descartada: la búsqueda y el LLM pueden tardar segundos y el gateway tiene `HTTP_TIMEOUT_SECONDS`; `BackgroundTasks` basta. Una cola con worker y Redis queda en la feature «Agrupar mensajes con worker y caché» (`later`).
- **`psycopg` (v3) como driver.** Descartada: licencia LGPL-3.0, fuera de las permitidas en `docs/architecture.md` §2. `pg8000` (BSD-3, Python puro, síncrono) cumple.
- **SDK oficial del proveedor de IA.** Descartada: el proveedor no está decidido (`docs/proyecto.md` §12) y añade dependencia; se usa httpx contra un endpoint compatible con chat completions configurable.
- **ORM (SQLAlchemy).** Descartada por tamaño del esquema (4 tablas) y por mantener SQL parametrizado explícito y auditable.

## Dependencias nuevas (las instala el humano antes de implementar)

| Nombre | Versión | Licencia |
|---|---|---|
| httpx | `>=0.27,<1` | BSD-3 |
| pg8000 | `>=1.31,<2` | BSD-3 |

## Supuestos a confirmar

| Supuesto | Valor por defecto configurable |
|---|---|
| Número de fragmentos pedidos a RAG | `RAG_TOP_K=5` |
| Frases que piden una persona | `HANDOVER_KEYWORDS=hablar con una persona,hablar con un asesor,hablar con un humano,quiero un asesor,quiero un agente,agente humano` |
| Texto de rechazo (sin resultados) | `NO_ANSWER_REPLY=No encontré información sobre eso en los manuales. Te paso con un asesor.` (la feature 6 añade la oferta de asesor en rechazos por cita inválida) |
| Texto tras avisar al asesor por petición del cliente | `HANDOVER_ACK_REPLY=Avisé a un asesor; te responderá por aquí en cuanto pueda.` |
| Texto ante fallo de RAG o del LLM | `ERROR_REPLY=Tuve un problema para responderte. Inténtalo de nuevo en unos minutos.` |
| Proveedor del LLM compatible con chat completions | `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL`, `LLM_API_KEY` (quién paga la API es duda abierta) |
| Tiempo máximo de llamadas salientes | `HTTP_TIMEOUT_SECONDS=10` |
| Con `no_advisors` o handover caído no se avisa al cliente en esta feature (lo hace `NO_ADVISORS_REPLY` en la feature 7); queda evento `handover_failed` | — |
| Solo se guardan los roles `user` y `bot`; el rol `advisor` llega con la feature 7 | — |
| Un `update_id` se marca antes de procesar; si el proceso cae a mitad, no se reintenta | — |
| Las tablas se crean con `CREATE TABLE IF NOT EXISTS` al primer uso (sin herramienta de migraciones) | — |
| El mensaje que dispara el traspaso por `no_relevant_chunks` se contesta con `NO_ANSWER_REPLY` antes de llamar a handover (el fallo de handover no borra la respuesta) | — |
