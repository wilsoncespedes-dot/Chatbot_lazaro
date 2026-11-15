# Spec review — #57 retencion_evidencia_y_privacidad_inicial

**Veredicto:** SPEC_APPROVED

- **Decisiones del dueño:** los valores del spec coinciden con las decisiones del dueño. Son aviso 1.0, ACEPTO / NO ACEPTO, 30 días, 15 días para casos activos y `MEMORY_ENABLED=true` con memoria hasta supresión, sin purga por retención (R1–R6, R9–R10). Los textos del aviso y de la respuesta son un default configurable, declarado como supuesto S1 y sin datos inventados (R2 prohíbe correo y razón social).
- **Supresión multicanal:** R11–R13 cubren el borrado por identidades `(channel, external_user_id)` de los contactos de las sesiones del perfil. Esto incluye varios canales y excluye otras identidades. R14 pide `removed_counts["privacy_consents"]`. R15–R17 cubren la misma transacción, el rollback y el reenvío del aviso.
- **Retención por `occurred_at`:** R18–R22 cubren el corte, el límite exacto (R19), los conteos en el retorno, en `PrivacyPurgeResponse` y en `privacy_purge_runs` (R20), contactos activos e inactivos (R21) y el respaldo con `accepted_at` (R22).
- **Fake y Postgres:** el diseño da SQL parametrizado en ambos repositorios, con `ANY(%s)` y `%s` y sin interpolar valores. T9, T14 y T15 prueban transacción, parametrización y paridad de conteos (R23).
- **Sin validación legal:** R8, R25, S4 y T22 impiden afirmar validación legal independiente. La política queda como decisión del dueño pendiente de esa validación.
- **Estructura:** los R cumplen EARS con un solo DEBE y son verificables. El diseño tiene alternativas descartadas, supuestos y trazabilidad, sin dependencias nuevas. Las tasks T1–T23 están en `[ ]`, en orden y cubren R1–R26.

Observación no bloqueante: en design §4 (Fake `execute_suppression`) las frases «antes de mutar nada» y «al final» son ligeramente ambiguas. El diseño las resuelve al decir que el fallo inyectado se evalúa antes de cualquier mutación y el borrado se aplica justo antes de marcar `executed`. El implementador debe respetar esa lectura.
