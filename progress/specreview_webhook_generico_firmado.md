# Spec review — #62 webhook_generico_firmado

**Veredicto:** SPEC_APPROVED

- Cobertura: los 8 criterios de `acceptance` están mapeados a R1–R52 (tabla de cobertura en requirements.md).
- EARS y verificabilidad: cada R tiene test concreto asignado en tasks.md; las 9 tasks están en `[ ]`, ordenadas, y cubren R1–R52.
- Diseño: respeta la arquitectura hexagonal de #61, sin dependencias nuevas, con 6 alternativas descartadas y sección de supuestos (S1–S6) con defaults seguros y configurables.
- Seguridad: anti-SSRF con IP fijada (sin rebinding), sin redirecciones, `WEBHOOK_ALLOW_PRIVATE_CALLBACKS` prohibido en producción, 404 uniforme, comparación en tiempo constante, sin secretos en logs.
- Notas no bloqueantes: R1 lista el orden `404, 413, 401, 422` y design §4 añade 503 por delante; es coherente (R29 y la fila 503 de R1). Los ejemplos firmados de `CONTRATOS.md` (líneas 281 y 331) existen, por lo que R2 es verificable.
