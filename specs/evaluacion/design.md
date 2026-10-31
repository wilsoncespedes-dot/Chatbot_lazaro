# Design — evaluacion

## Archivos a crear (solo en `eval/`; no se toca `services/` ni `contracts/`)

- `eval/manual_ejemplo/manual_ejemplo.md` — manual ficticio (p. ej. «Lázaro Facturador de ejemplo»: alta de usuarios, horarios de soporte, copias de seguridad, planes, límites). Cada dato es inventado; se redacta para que cada pregunta `responde` tenga una frase literal que la conteste.
- `eval/preguntas.json` — `{"manual": "manual_ejemplo", "preguntas": [...]}`. Elementos: `{id, pregunta, tipo, fragmento_esperado?, chunk_id_esperado?}`. Las `no_responde` cubren temas ajenos al manual, precios no escritos y una con instrucciones («ignora tus reglas…»).
- `eval/scoring.py` — lógica pura.
- `eval/run_eval.py` — CLI y capa de red.
- `eval/__init__.py` y `eval/tests/__init__.py` solo si el layout de imports de pytest lo exige (ver `services/*/tests` para el patrón).
- `eval/tests/test_preguntas.py`, `eval/tests/test_scoring.py`, `eval/tests/test_run_eval.py`.
- `.env.example` — añadir un bloque `# eval` con una sola variable nueva, `EVAL_SINK_PORT=8099` (puerto del receptor local). El resto se reutiliza: `RAG_URL`, `ORCHESTRATOR_URL`, `RAG_TOP_K`, `SERVICE_TOKEN`, `NO_ANSWER_REPLY`. No se crea `EVAL_TOP_K`.
- `eval/resultados_*.md` se añade a `.gitignore` (salida generada).

## Firmas

```python
# scoring.py (sin red, sin entorno)
Outcome = Literal["acierto_recuperacion","fallo_recuperacion","rechazo_correcto",
                  "respuesta_inventada","rechazo_indebido","sin_respuesta","error"]

@dataclass(frozen=True)
class Question: id: str; pregunta: str; tipo: Literal["responde","no_responde"]; fragmento_esperado: str|None; chunk_id_esperado: str|None

@dataclass(frozen=True)
class Observation:      # lo que devolvió el sistema para una pregunta
    results: list[dict] | None = None   # modo rag: SearchResult como dict
    reply: str | None = None            # modo orquestador: texto enviado al cliente
    error: str | None = None            # causa de fallo de red
    timed_out: bool = False

@dataclass(frozen=True)
class Scored: question: Question; outcome: Outcome; detail: str

@dataclass(frozen=True)
class Summary: total:int; recuperacion:tuple[int,int]; rechazos:tuple[int,int]; inventadas:int; fallos:list[Scored]
    # proporciones: properties tasa_recuperacion / tasa_rechazo -> float|None (R14)

def normalize(text: str) -> str                       # casefold + colapsa espacios; igual criterio que no_inventar
def load_questions(path: Path) -> list[Question]      # lanza ValueError (R6)
def score(q: Question, obs: Observation, *, mode: Literal["rag","orquestador"], refusal_text: str) -> Scored
def summarize(scored: list[Scored]) -> Summary
def render_report(summary: Summary, *, url: str, mode: str, date: date) -> str

# run_eval.py
def main(argv: list[str] | None = None) -> int          # código de salida (R19, R22, R23)
def query_rag(client, url, token, question, top_k) -> Observation
def query_orchestrator(client, url, token, question, sink, wait) -> Observation
class ReplySink:        # servidor http.server en hilo; captura POST /send {chat_id,text}; queue por chat_id
```

El cliente HTTP es `httpx` inyectable (`httpx.Client` con `MockTransport` en tests). El reloj/fecha del informe se inyecta (`date`) para tests deterministas.

## Decisiones clave

- **Dos modos.** `POST /messages` del orquestador devuelve solo `202` (feature 4): la respuesta al cliente sale por `POST /send` del gateway. Por eso el modo `rag` (por defecto, mide recuperación y umbral) no necesita nada más, y el modo `orquestador` levanta un `ReplySink` local con `http.server` de la biblioteca estándar. El orquestador debe tener `TELEGRAM_GATEWAY_URL` apuntando a ese receptor y `RAG_URL`/LLM reales; es una ejecución manual, no de CI. Cada pregunta usa un `chat_id` único para correlacionar respuestas.
- **Rechazo = texto exacto `NO_ANSWER_REPLY`** (misma variable que el orquestador; se puede cambiar con `--rechazo`). Es el texto fijo de las features 4 y 6, así que la comparación es directa y determinista.
- **«Respuesta inventada detectada».** En modo `rag` es una pregunta `no_responde` con resultados no vacíos (el umbral dejó pasar algo); en modo `orquestador` es una `no_responde` con texto distinto del rechazo. No se puntúa semántica con un LLM juez.
- **Acierto por fragmento, no por `chunk_id`.** Los `chunk_id` los genera RAG al ingerir (no se conocen de antemano); `fragmento_esperado` es estable ante cambios de `CHUNK_SIZE`. `chunk_id_esperado` queda opcional para ejecuciones sobre una ingesta fija.
- Se carga el manual con `scripts/cargar_manual.py` (feature 5); `run_eval.py` no ingiere nada, solo documenta el comando en su `--help`.
- **Puntuación en modo `orquestador` de `responde`.** Texto igual al rechazo -> `rechazo_indebido` (R12); texto no vacío distinto -> `acierto_recuperacion` (R29, no se mide el contenido); sin texto a tiempo -> `sin_respuesta`; fallo HTTP -> `error`. `sin_respuesta`, `error` y `rechazo_indebido` son fallos y cuentan en el denominador de su tipo (R30, R31). Para `no_responde`, `sin_respuesta`/`error` no son `rechazo_correcto` ni `respuesta_inventada`.
- **Validación de `--top-k`.** `main()` comprueba 1 <= top_k <= 20 y `0 <= umbral <= 1` antes de crear el cliente (R32, R33); salida != 0 sin red.
- Seguridad: el token solo viaja en el encabezado; nunca se imprime (R24). Preguntas de prueba son texto inventado.

## Excepciones

`ValueError` (preguntas inválidas, R6). Errores de red se capturan en `query_*` y se convierten en `Observation(error=...)`; no se propagan.

## Alternativa descartada

**Evaluar con un LLM juez la calidad de la respuesta.** Descartada: no determinista, de pago, y es la misma clase de componente que se evalúa. Se mide lo objetivo (¿llegó el fragmento? ¿se rechazó lo que no se sabe?), alineado con la barrera de la feature 6. También descartado: añadir un endpoint de depuración al orquestador para devolver la respuesta, porque amplía la superficie del servicio y rompe el contrato de la feature 4.

## Dependencias nuevas

Ninguna nueva en el proyecto: `httpx` ya lo usan los servicios y `pytest` ya está. Se usa `lazaro_contracts` para `MessageRequest`/`SearchRequest`. Si `eval/` necesita `requirements.txt`, solo `httpx` y `-e contracts` (el humano instala). Licencias: BSD-3 (httpx).

## Supuestos a confirmar

| Supuesto | Valor por defecto |
|---|---|
| Al llegar un manual real se añaden sus preguntas en otro archivo (`--preguntas`) y se recalibra `RAG_SIMILARITY_THRESHOLD` a mano mirando el informe | `--preguntas` repetible; sin recalibración automática |
| Mínimo de aciertos para considerar «verde» | sin umbral por defecto; opcional con `--umbral-minimo-aciertos` |
| Preguntas de ejemplo en español; 10 `responde` + 5 `no_responde` como mínimo | ver `eval/preguntas.json` |
| El modo `orquestador` es manual y requiere reconfigurar `TELEGRAM_GATEWAY_URL` | puerto del receptor `EVAL_SINK_PORT=8099`, espera `--espera 30` |
| Rechazo = texto exacto de `NO_ANSWER_REPLY` | configurable con `--rechazo` |
| En modo `orquestador`, una `responde` con texto distinto del rechazo se da por acierto (no se verifica contenido); alternativa: exigir que contenga `fragmento_esperado` | acierto si no es rechazo (R29) |
| No se mide la exactitud del texto generado por el LLM (solo recuperación y rechazo) | — |
