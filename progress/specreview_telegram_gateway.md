# Spec review — telegram_gateway (feature #3), 2ª vuelta

**Veredicto:** SPEC_APPROVED

## Checklist
- [x] Cobertura: los 7 criterios de `acceptance` están cubiertos (tabla al final de requirements.md).
- [x] EARS estricto: R22 ya tiene un solo `DEBE`; la exigencia sobre `.env.example` pasó a R25 (un solo `DEBE`). El resto mantiene patrón EARS válido, sin verbos blandos.
- [x] Verificable: R4 y R13 fijan el caso de `text` vacío o solo espacios (tratado como sin texto). `extract_incoming` lo normaliza a `None` y T17 añade `test_empty_or_blank_text_treated_as_non_text`.
- [x] Sin invenciones: `HTTP_TIMEOUT_SECONDS` ya está trazado a R22, T1 y T20.
- [x] Diseño: respeta las 3 capas, usa adaptadores con Protocol y fake, y reutiliza los contratos de `lazaro_contracts`. Las dependencias httpx y redis llevan versión y licencia. Hay 3 alternativas descartadas y la sección «Supuestos a confirmar».
- [x] Tasks: todas en `[ ]`, en orden, con sus R<n>. Cubren R1-R25 (R25 en T2 y T20b).
- [x] Nada peligroso: sin borrados, sin red real en tests, sin archivos fuera del repo.

## Observación menor (no bloquea)
- En design.md, la lista de `config.py` (línea 14) no nombra `http_timeout_seconds`. La lista de `.env.example` (línea 18) tampoco nombra `HTTP_TIMEOUT_SECONDS`. T1, T2 y R22 sí los incluyen, así que prevalecen. El implementador debe seguir T1/T2.
