# Design — validacion_respuestas_flexible (#62)

- `_strip_code_fence(raw)`: si el texto (sin espacios) empieza por ```` ``` ````,
  quita la primera línea (```` ``` ```` o ```` ```json ````) y el ```` ``` ```` final.
- `_STEP_MARKER_RE = (?im)^\s*(?:paso\s+)?\d{1,2}\s*[.):-]\s+`; la respuesta se
  limpia con él antes de `extract_numbers`. Solo afecta al principio de línea:
  "Son 99 pasos" o "cuesta 2000" siguen comprobándose.
- `_loose_text(text)`: `normalize_quote` + quitar tildes (NFKD sin marcas) +
  sustituir todo lo que no sea letra o dígito por espacio y colapsar. La cita
  es válida si `_loose_text(quote)` no está vacío y es subcadena de
  `_loose_text(fragmento)`. Al comparar por palabras completas no se aceptan
  paráfrasis.
- `normalize_quote` se conserva (pública y probada).
- Prompt: "Puedes usar pasos numerados (1., 2., 3.); cualquier otra cifra de
  answer debe aparecer en los fragmentos citados."
- Pruebas antiguas de `test_no_inventar.py` R2/R8 que fijaban el rechazo de
  bloques de código, tildes y puntuación se actualizan a esta decisión.
