# Design — #59 `saludos_y_mensajes_sociales`

Feature local del orquestador. No cambia contratos HTTP, modelos compartidos,
estados de conversación ni la matriz de herramientas. No añade dependencias,
excepciones, servicios ni carpetas. No ingiere documentos: el corpus de PDFs
sigue congelado por decisión del dueño (coste).

## Decisión central

Resolver la intención **antes** de llamar a RAG o al LLM, con una comparación
exacta de texto normalizado. El bot «lo hace por sí mismo» en el sentido
acordado: decide con reglas locales (`harness.py`, sin IO), sin llamadas de pago
y sin conocimiento general del modelo.

No se añade una herramienta nueva a `TOOL_NAMES`/`TOOL_MATRIX`: el test existente
`test_r1_r2_matrix_is_complete_immutable_and_has_six_tools` exige exactamente
seis herramientas y `default_tool(ACTIVE) == buscar_base_conocimiento`. La
respuesta social es una rama de decisión, no una herramienta del modelo.

## Punto de inserción

En `domain.py::_resolve_and_run` (L2087-2199), después de los bloques de
supresión, petición de asesor y frustración (L2115-2160) y antes del router
(L2162) y de `default_tool` (L2190):

```python
if state == ConversationState.ACTIVE and is_social_message(
    text, settings.social_message_list
):
    _send(contact, settings.social_reply, adapters)
    return
```

Así se cumplen R1-R6 sin tocar `_tool_rag`, y R9 porque las keywords ya se
ejecutaron arriba. El estado `ACTIVE` se comprueba explícitamente: en `NEW`,
`AWAITING_CONSENT` y `AWAITING_LOGIN` el flujo de consentimiento/identidad no se
modifica.

## Archivos a modificar

### `services/orchestrator/orchestrator/harness.py`

Añadir la función pura junto a `matches_any` (L174):

```python
def _social_key(text: str) -> str:
    """Normaliza para comparación exacta: sin tildes, sin puntuación."""

def is_social_message(
    text: str, phrases: list[str] | tuple[str, ...]
) -> bool:
    """True solo si el texto normalizado es igual a alguna frase configurada."""
```

- `_social_key` aplica `normalize_text` (ya importada de `.classifier`) y
  sustituye con `re.sub(r"[^a-z0-9]+", " ", ...)` los caracteres que no sean
  letra ASCII o dígito; luego colapsa espacios con `.strip()`. `re` ya está
  importado en el módulo.
- `is_social_message` compara **igualdad**, no contención (a diferencia de
  `matches_any`). Eso implementa R8 sin reglas adicionales: «hola, ¿cómo creo un
  usuario?» produce `hola como creo un usuario`, que no es igual a `hola`.
- Sin IO, sin adaptadores, sin `Settings` (R11).

### `services/orchestrator/orchestrator/config.py`

- Constante nueva junto a `DEFAULT_HANDOVER_KEYWORDS` (L20):

  ```python
  DEFAULT_SOCIAL_MESSAGES = (
      "hola,buenos días,buenas tardes,buenas noches,gracias,muchas gracias,"
      "ok,perfecto,de acuerdo,cómo estás,cómo va"
  )
  DEFAULT_SOCIAL_REPLY = (
      "¡Hola! Gracias por escribirnos. ¿En qué puedo ayudarte?"
  )
  ```

- Campos nuevos en `Settings`, junto a `handover_keywords` (L119):

  ```python
  social_messages: str = DEFAULT_SOCIAL_MESSAGES
  social_reply: str = DEFAULT_SOCIAL_REPLY
  ```

- Property nueva junto a `handover_keyword_list` (L579):

  ```python
  @property
  def social_message_list(self) -> list[str]:
      return [p.strip() for p in self.social_messages.split(",") if p.strip()]
  ```

Misma normalización separada por coma que las keywords ya existentes: no se
añade validador nuevo y no se toca `REQUIRED_IN_PRODUCTION`.

### `.env.example`

Bajo el bloque «harness de IA por estado (#39)», añadir:

```env
# respuesta social determinista (#59): sin RAG, sin LLM, sin coste
SOCIAL_MESSAGES=hola,buenos días,buenas tardes,buenas noches,gracias,muchas gracias,ok,perfecto,de acuerdo,cómo estás,cómo va
SOCIAL_REPLY=¡Hola! Gracias por escribirnos. ¿En qué puedo ayudarte?
```

### `services/orchestrator/orchestrator/domain.py`

- Añadir `is_social_message` al import de `.harness` (L80-91).
- Insertar la rama descrita en «Punto de inserción».

### `services/orchestrator/tests/test_social_messages.py` (nuevo)

Un solo archivo con ocho tests; usa el fixture `env` de `tests/conftest.py`.
`env.post(text=...)` simula un mensaje de Telegram con consentimiento y estado
`ACTIVE`. Los fakes del fixture exponen `env.rag.calls`, `env.llm.calls`,
`env.handover.requests`, `env.gateway.sent`, `env.repo.events` y
`env.repo.rag_outcomes`.

| Test | Afirmación | Requirement |
|---|---|---|
| `test_is_social_message_is_pure_and_exact` | Parametrizado: social `hola`, `¡Hola!`, `¿Cómo estás?`, `gracias`; no social `hola como creo un usuario`, `hola asesor`, `¿cuánto cuesta?`, `""`. Comprueba también que no se muta la lista de frases | R11, R8 |
| `test_social_settings_are_read_from_env` | `monkeypatch.setenv("SOCIAL_MESSAGES", "hola, gracias")` y `SOCIAL_REPLY`; `Settings().social_message_list == ["hola", "gracias"]` y `social_reply` igual al valor | R10 |
| `test_social_reply_is_sent` | `env.post(text="hola")` → `env.gateway.sent == [(100, settings.social_reply)]` | R1 |
| `test_social_reply_does_not_call_rag_or_llm` | En el mismo caso, `env.rag.calls == []` y `env.llm.calls == []` | R2, R3 |
| `test_social_reply_does_not_record_failure_or_handover` | `("no_results", "no_relevant_chunks") not in env.events`; `env.repo.rag_outcomes == set()`; `env.handover.requests == []` | R4, R5, R6 |
| `test_non_social_message_keeps_existing_flow` | `env.post()` con pregunta por defecto → `env.rag.calls == [("¿Cómo instalo el módulo?", 7)]` y una llamada al LLM | R7 |
| `test_greeting_with_question_goes_to_rag_with_full_text` | `env.post(text="hola, ¿cómo instalo el módulo?")` → `env.rag.calls[0][0] == "hola, ¿cómo instalo el módulo?"`; la respuesta no es `social_reply` | R8 |
| `test_handover_keyword_wins_over_social` | `env.post(text="hola, quiero un asesor")` → `len(env.handover.requests) == 1` | R9 |

La medición de coste (R2, R3) se hace con los fakes del fixture, sin red.
Ningún test existente se edita.

## Excepciones

No se añade ninguna. Se reutiliza `DomainError` si hiciera falta en el futuro,
pero esta feature no levanta excepciones nuevas.

## Alternativas descartadas

- **Añadir `responder_social` a `TOOL_MATRIX`.** Rompería el test de las seis
  herramientas y permitiría al router elegirla si se activa; innecesario para
  una respuesta fija.
- **Activar `HARNESS_ROUTER_ENABLED`.** Añade una llamada al LLM por mensaje
  (coste) y hace la conducta no determinista; el dueño eligió autonomía local.
- **Subir el umbral/ajustar RAG para que «hola» coincida con un fragmento.**
  Degradaría las respuestas reales y mezclaría conversación con documentación.
- **Generar la respuesta social con el LLM.** Coste por mensaje y riesgo de
  inventar; el dueño eligió rechazo/repuesta fija.
- **Meter los textos en el panel administrativo.** Requiere ampliar
  `ConversationTexts`, formularios y tests; no aporta aquí y G1 eligió
  variables de entorno.
- **Detección por subcadena (`matches_any`).** «hola» dentro de una pregunta
  larga la convertiría en social y se comería la pregunta (rompe R8).

## Dependencias nuevas

Ninguna. `re` ya está en `harness.py`; no se instala nada.

## Supuestos a confirmar

Ninguno pendiente. El dueño confirmó el 2026-11-21: (1) autonomía mediante
decisiones locales sin LLM extra, (2) preguntas fuera del corpus → rechazo útil
con asesor, nunca conocimiento general del modelo, (3) corpus cerrado de PDFs
por coste, (4) configuración por variables de entorno. El texto por defecto
de `SOCIAL_REPLY` es un valor configurable, no una decisión de producto fija.
