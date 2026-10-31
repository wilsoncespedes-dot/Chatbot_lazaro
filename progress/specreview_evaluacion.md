# Spec review — evaluacion (#8), segunda vuelta

**Veredicto:** SPEC_APPROVED

## Comprobaciones
- [x] Cobertura de acceptance: los 5 criterios están cubiertos (trazabilidad al final de requirements.md: R1-R6, R4-R5, R15-R20 y R25-R33, R7-R14 y R29-R31, R21 y «Supuestos»).
- [x] EARS estricto: R19 (solo `error` y causa), R27 (salida != 0) y R28 (continuar) ya están separados. Cada R tiene un único DEBE y no usa verbos blandos.
- [x] Verificable: R29 define la puntuación de `responde` en modo `orquestador` (acierto si no es rechazo, con el límite declarado). Junto con R12, R18 y R19 cierra el vacío anterior. R30 y R31 fijan qué cuenta como fallo y cuál es el denominador. Cada R tiene un test posible, y T11 y T12 los nombran.
- [x] Sin invenciones: R25-R33 salen de contratos (`X-Service-Token`, `/send`, rango de `top_k`) o del acceptance. El límite de R29 está en «Supuestos a confirmar».
- [x] Diseño: respeta la arquitectura (solo `eval/`, sin servicios nuevos, sin GPL/AGPL). La dependencia `httpx` está listada con licencia BSD-3. Tiene alternativa descartada y tabla «Supuestos a confirmar». La línea de `.env.example` está corregida (solo `EVAL_SINK_PORT`). La validación de `--top-k` y del umbral va en el design y en R32/R33.
- [x] Tasks: todas en `[ ]`, ordenadas, cada una con sus R. La unión cubre R1-R33. T14 cita R1-R33.
- [x] Nada peligroso: tests sin red real, sin borrado de datos, nada fuera del repo. El token no se imprime (R24, T12).

## Observaciones menores (no bloquean)
- R30 agrupa varias consecuencias en un solo DEBE. Es aceptable porque todas se derivan de un único cálculo del resumen.
- Para `no_responde`, `sin_respuesta` y `error` quedan fuera de `rechazo_correcto` y de `respuesta_inventada`. Esto está en design.md y lo cubre R30. El implementador debe probarlo en T7.
