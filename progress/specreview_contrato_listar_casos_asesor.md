# Spec review — #33 contrato_listar_casos_asesor (2ª pasada)

**Veredicto:** SPEC_APPROVED

Segunda pasada limitada a los dos bloqueantes de la primera revisión.

## 1. `actions` reutiliza S12 — resuelto

- `design.md` §Handover (`list_advisor_cases`): `actions` se calcula con
  `can_act_on_case(case, advisor_id, a, settings)` sobre `reply`/`assign`/`close`,
  sin tabla propia. La firma coincide con `services/handover/handover/domain.py:162`.
- Se quita `assign` cuando `case.status == "assigned"` (no-op de S11, justificado en
  Alternativas descartadas).
- Los casos con `actions` vacía se descartan, y el design dice que ese es el único
  filtro en dominio. El filtro de huérfanos en SQL queda solo por eficiencia (R16).
- Con la implementación actual de `can_act_on_case` (`domain.py:169-175`), el resultado
  coincide con R11–R13: open/timed_out → reply,assign,close; asignado propio →
  reply,close; huérfano → close; closed y asignado a otro registrado → descartados (R14).
- Test comparativo: T10 tiene un punto de «igualdad con S12» (`actions` == comprensión
  con `can_act_on_case`, salvo `assign` en `assigned`) y un repo falso que devuelve
  closed y asignado a otro asesor, que deben salir descartados. T8 sigue el design.

## 2. Un solo `DEBE` por requirement — resuelto

- R6 (ejemplos) y R21 (validación de cada ejemplo) están separados.
- R17 (rango inválido → fallo) y R22 (default 50, ubicuo) están separados.
- R18 tiene un solo `DEBE`; el paréntesis aclara y no añade una segunda obligación.
- R1–R22 tienen cada uno una sola obligación `DEBE`/`NO DEBE`.
- Trazabilidad: R21 → T2 (registro en `EXAMPLES` de `test_examples.py`) y tabla de
  acceptance; R22 → T6 (sin variable → 50) y T10 (51 casos → 50); T11 cubre R1–R22.

No hay más blockers.
