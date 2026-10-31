# Design — no_inventar

## Archivos

Modificar en `services/orchestrator/`:

- `orchestrator/domain.py`
  - Añadir modelos `Citation` y `LLMAnswer` (Pydantic v2, solo internos del orquestador; no son contrato entre servicios).
  - Añadir `InvalidAnswer(Exception)` con atributo `reason`, y `ValidatedAnswer` (dataclass: `answer: str`, `citations: list[Citation]`).
  - Añadir `extract_numbers`, `normalize_quote`, `validate_llm_answer`.
  - Cambiar `LLM_SYSTEM_PROMPT` para exigir el JSON de R1 (conservando que `<pregunta>` y `<fragmento>` son datos).
  - En `process_message`, paso 5: tras `llm.complete`, llamar a `validate_llm_answer`; si lanza `InvalidAnswer`, ejecutar `_reject_invalid_answer`.
  - Añadir `_reject_invalid_answer(contact, reason, settings, adapters)`.
- `orchestrator/config.py` — añadir `invalid_answer_handover: bool = True`.
- `/.env.example` — añadir `INVALID_ANSWER_HANDOVER=true`.
- `THIRD_PARTY_NOTICES.md` — solo si el implementer copia código de rag-support-bot (ver «Código de terceros»).

Tests (en `services/orchestrator/tests/`): nuevo `test_no_inventar.py`; actualizar los tests de la feature 4 que usan `FakeLLM` con respuesta de texto libre (`test_messages.py`, `test_decisions.py`, `test_security.py`) para que el LLM falso devuelva JSON válido con cita; añadir una prueba de `THIRD_PARTY_NOTICES.md` (R23).

No se modifican `contracts/`, `adapters/llm.py` ni `main.py`: `LLMClient.complete(system, user) -> str` sigue igual; el JSON se pide por prompt, no por una función del proveedor (R1). Tampoco el repositorio: `add_event` ya acepta cualquier tipo y motivo.

## Firmas

```python
# domain.py
class Citation(BaseModel):  chunk_id: str; quote: str
class LLMAnswer(BaseModel): answer: str; citations: list[Citation]   # answer no vacío (strip)

class InvalidAnswer(Exception):
    reason: str   # uno de INVALID_REASONS

INVALID_REASONS = (
    "invalid_json", "invalid_shape", "no_citations",
    "foreign_chunk_id", "quote_not_literal", "number_not_in_citations",
)

def normalize_quote(text: str) -> str
    # casefold + colapsa espacios en blanco; NO quita tildes ni puntuación (R7, R8)
def extract_numbers(text: str) -> set[str]
    # regex r"\d+(?:[.,]\d+)*" ; compara el texto tal cual (R10)
def validate_llm_answer(raw: str, chunks: list[SearchResult]) -> LLMAnswer
    # pura; lanza InvalidAnswer(reason) (R2-R10, R21)
def _reject_invalid_answer(contact, reason, settings, adapters) -> None
```

## Flujo de `validate_llm_answer`

Orden fijo, el primer fallo gana (así cada test aísla un solo motivo):

1. `json.loads(raw)`; `ValueError` → `invalid_json` (R2). No se intenta limpiar bloques de código markdown.
2. `LLMAnswer.model_validate(data)`; `ValidationError` → `invalid_shape` (R3). Claves extra se ignoran.
3. `citations` vacía → `no_citations` (R4).
4. Para cada cita: `chunk_id` fuera de `{c.chunk_id for c in chunks}` → `foreign_chunk_id` (R5).
5. Para cada cita: `normalize_quote(quote)` no vacío y contenido en `normalize_quote(fragmento.text)` → si no, `quote_not_literal` (R6, R7, R8). Un `quote` vacío se rechaza con este mismo motivo.
6. `extract_numbers(answer)` debe estar contenido en la unión de `extract_numbers(texto)` de los **fragmentos citados** (texto completo del fragmento, no solo el `quote`) → si no, `number_not_in_citations` (R9, R10).

`_reject_invalid_answer` (R13-R18):
1. `repo.add_event(contact.id, "invalid_answer", reason, clock())`.
2. `_send(contact, settings.no_answer_reply, adapters)`.
3. Si `settings.invalid_answer_handover`: `_handover(contact, "invalid_answer", settings, adapters)`.

Respuesta válida: `repo.add_event(contact.id, "rag_answer", "chunks_found", ...)` y `_send(contact, validated.answer, ...)` (R11, R12). El caso `llm_failed` (LLM caído o salida vacía) de la feature 4 NO cambia: sigue siendo `processing_error` + `ERROR_REPLY`, porque es un fallo de infraestructura, no una respuesta inválida. Una salida vacía devuelta con éxito no ocurre en la práctica; se mantiene la rama existente antes de validar.

Logs: solo `contact_id` y `reason` (R22), nunca el texto del modelo.

Tipos de evento tras esta feature: `rag_answer`, `no_results`, `invalid_answer`, `handover`, `handover_failed`, `processing_error`. La función de traspaso ya registra `handover` con el motivo `invalid_answer`; el campo `HandoverReason` ya lo admite.

## Código de terceros (rag-support-bot, MIT)

El patrón (JSON con `chunk_id` y cita textual; validación de citas y de números) viene de rag-support-bot según `docs/proyecto.md` §4. Este spec se redacta sin haber leído su código; el diseño de arriba es propio e independiente. Si el implementer copia o adapta código de ese repo, DEBE: (a) conservar el aviso de copyright MIT al inicio del archivo, (b) añadir una fila a `THIRD_PARTY_NOTICES.md` con archivo, repo, archivo de origen, commit, licencia y copyright (R23). Si no copia nada, deja `THIRD_PARTY_NOTICES.md` intacto y lo anota en `progress/impl_no_inventar.md`. Idea tomada como inspiración (sin copia): el formato `{answer, citations}` y la validación de números.

## Excepciones

Se añade `InvalidAnswer` (interna; nunca sale por HTTP, `process_message` la captura). Se reutilizan `DomainError` y `ServiceUnavailable` sin cambios.

## Alternativas descartadas

- **Validar con otro LLM (juez) en lugar de reglas literales.** Descartada: es no determinista, cuesta una segunda llamada y es la misma clase de componente que se quiere vigilar; las comprobaciones literales son baratas, deterministas y testeables.
- **Usar salida estructurada/`response_format` del proveedor.** Descartada: el proveedor no está decidido (`docs/proyecto.md` §12) y ata `LLMClient` a una API concreta. El JSON se pide por prompt y se valida siempre del lado nuestro, que es la barrera real.
- **Comparar números por valor (`1.500` = `1500`).** Descartada: interpretar formatos locales (punto/coma) es ambiguo y abre la puerta a falsos válidos; la comparación textual es más estricta, y si falla se rechaza (el lado seguro).
- **Quitar tildes al comparar citas.** Descartada: el criterio pide ignorar solo mayúsculas y espacios; ser más laxo debilita la barrera.

## Dependencias nuevas

Ninguna (`json`, `re` y Pydantic ya presentes).

## Supuestos a confirmar

| Supuesto | Valor por defecto configurable |
|---|---|
| Ante respuesta inválida, además del rechazo se abre traspaso a asesor con motivo `invalid_answer` (el `acceptance` solo pide «oferta de hablar con un asesor»; el texto fijo ya la contiene y el contrato reserva el motivo) | `INVALID_ANSWER_HANDOVER=true` |
| Texto de rechazo: se reutiliza `NO_ANSWER_REPLY`, que ya contiene la oferta de asesor | `NO_ANSWER_REPLY` (sin variable nueva) |
| Números = secuencias de dígitos con separadores `.`/`,`, comparados como texto; no se detectan números escritos con palabras («tres») | — |
| No se acepta JSON envuelto en bloques markdown (` ```json `); se rechaza como `invalid_json` y puede subir la tasa de rechazos con ciertos modelos | — |
| Claves extra en el JSON del LLM se ignoran | — |
| Si el manual cita una cifra que el modelo reescribe (`1.500` → `1500`), se rechaza; se prefiere falso rechazo a falsa respuesta | — |
