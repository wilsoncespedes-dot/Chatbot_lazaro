# Spec review — feature #39 harness_ia_por_estado

**Veredicto:** APPROVED

## Comprobaciones
- Cobertura acceptance A1–A5: cubierta por R1–R63 (tabla de trazabilidad en requirements.md, verificada).
- Tasks: T0–T21 todas en `[ ]`, ordenadas; entre todas cubren R1–R63 (R1–R3 T2; R4–R8 T9; R9/R36/R37/R42 T5; R10/R16/R19/R55 T11; R11–R14/R20 T10; R15/R17/R18 T3; R21–R26/R32–R34 T13; R27–R31 T7; R35/R59/R63 T4; R36–R40/R43 T15; R41 T17; R44/R45/R60 T12; R46–R51 T14; R52/R53 T16; R54/R61 T18; R56/R57/R62 T19; R58 T21).
- Diseño: solo orchestrator, sin contratos ni dependencias nuevas; alternativas descartadas (6) y «Supuestos a confirmar» (S1–S12) presentes. Mapeo de motivos al `HandoverReason` vigente evita cambio de contrato.
- Referencias a código existente verificadas: `active_client_id`, `end_client_session`, `_send_login_reminder`, `_send_session_closed_reply`, `_auto_handover`, `_is_suppression_request`, `_apply_identity_rules`, `validate_sql`, `format_rows`, `_parse_db_query_allowlist` y los tests citados de #6/#37 existen.
- Seguridad: ninguna herramienta borra datos (R41, R42); identidad solo de la sesión (R21, R28, RLS + sonda fail-closed R29–R31); router y datos de cliente apagados por defecto; sin red ni archivos fuera del repo.

## Observaciones no bloqueantes
- R20, R37, R40 y R57 combinan dos `DEBE`/`NO DEBE` (docs/specs.md pide partirlos). Son verificables tal cual; el implementer puede testear cada mitad por separado.
- Nota de numeración: R60–R63 están intercalados fuera de orden; sin impacto.
