# Spec review — feature #45 corregir_foreign_session_windows

**Veredicto:** APPROVED

- Trazabilidad: los 4 criterios de acceptance tienen R asignados (R1–R3 sin 42P18; R1/R2/R4/R5 semántica y memoria sin cambios; R6 endpoint sin 500; R1–R4 pruebas). Todos los R1–R6 están cubiertos por T1–T5; tasks en `[ ]` y en orden.
- Solución: el diseño elimina el parámetro NULL sin tipo con dos ramas SQL (`contact_id = %s` con `(contact_id,)` / `... AND profile_id <> %s` con `(contact_id, profile_id)`). Coincide con el código actual (`services/orchestrator/orchestrator/adapters/repository.py:2847-2859`, `(%s IS NULL OR profile_id <> %s)`). La semántica es equivalente a `FakeRepository` (líneas 904-918), que no se toca.
- Pruebas: T2 cubre `profile_id=None` (params `("c1",)`, sin `IS NULL`, sin `None`) y `profile_id="p1"` (params `("c1","p1")`, `profile_id <> %s`), con un cursor falso que emula el 42P18. T3 cubre el mapeo en las dos ramas.
- Diseño: un solo servicio y una sola capa (adapter), sin dependencias nuevas ni cambios de contrato o esquema. Incluye una alternativa descartada (cast `::text`).

Observación menor, no bloqueante: R3, R5 y R6 usan la forma «NO DEBE» o una justificación descriptiva en lugar de un patrón EARS puro. Siguen siendo verificables con los tests de T2 y T4.
