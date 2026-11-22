# Spec review — #74 servidor_mcp_lectura

**Veredicto:** SPEC_APPROVED

- Cobertura: los 8 criterios de `acceptance` quedan cubiertos por R1–R32 (tabla de trazabilidad en `requirements.md`).
- EARS: cada R usa un patrón válido, con un solo DEBE o NO DEBE, y todos se pueden probar.
- Diseño: respeta las 3 capas y la red interna. La dependencia `mcp` (MIT) está listada con versión. Incluye 4 alternativas descartadas y la sección de supuestos. `cliente_id` va por encabezado y no por esquema. `render.yaml` no cambia.
- Tasks: las 23 están en `[ ]`, en orden y con sus R. Entre todas cubren R1–R32. Cada R tiene al menos un test nombrado.
- Seguridad: no se borran datos y la red solo es interna. Las ofertas son de demostración y están marcadas como tales.

Notas no bloqueantes para el implementer:
- Comprobar el paramstyle de `pg8000` (`%s` frente a `format`) al escribir `PostgresDemoOffers`.
- T7 debería cubrir R3 con un test que revise la sentencia y el modo `READ ONLY`, usando un fake de conexión.
