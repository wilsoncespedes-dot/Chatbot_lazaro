# Revisión de spec — feature 32 (traspaso_automatico_fallos)

**Veredicto:** SPEC_APPROVED

- **Acceptance:** [x] R1–R2 definen qué outcomes cuentan y excluyen infraestructura, comandos y solicitudes explícitas; R3 aplica umbral configurable. R4–R8 cubren persistencia, aislamiento, idempotencia, reset, umbral y no duplicación; R9–R11 cubren avisos, falta de asesores y retry; R12 cubre verificación/compatibilidad.
- **EARS/verificabilidad:** [x] R1–R14 usan patrones EARS y son comprobables. Cada task enlaza requirements; tasks están pendientes y ordenadas.
- **Política:** [x] Default configurable: threshold 3; allowlist `no_relevant_chunks,invalid_answer`; `invalid_answer` conserva el control existente `INVALID_ANSWER_HANDOVER`; errores de infraestructura no cuentan. Se deduce de la política configurable del acceptance y evita contar indisponibilidad como fallo de respuesta.
- **Persistencia/idempotencia:** [x] Design exige transición atómica por `contact_id`, deduplicación por `update_id`, reset con respuesta válida y estado retryable/completed. Reutiliza `/handover` existente, que ya reutiliza casos activos; sin cambios de contrato.
- **Diseño/seguridad:** [x] Capas, SQL parametrizado, sin dependencias ni código externo; no cambia contratos #14/#16 ni los flujos de comandos. No toca dudas abiertas de `docs/proyecto.md` §12; alternativa descartada documentada.
- **Nada peligroso:** [x] No hay borrado de datos, red desde tests ni archivos externos.

No hay cambios bloqueantes para el implementador.
