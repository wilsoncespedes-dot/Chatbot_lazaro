# Spec review — feature #18 candado_repositorio_orquestador

**Veredicto:** APPROVED

- Cobertura: los 3 criterios de `acceptance` quedan cubiertos (R1-R4, R5-R7, tests T3-T6).
- Diseño coherente con el código actual: `_run` (repository.py:146) es el único punto que toca la
  conexión y `_connection()` (l.136) solo se llama desde ahí; `_new_id()` se evalúa fuera de `_run`.
  Sin dependencias nuevas, sin tocar `contracts/`, alternativa descartada presente, mismo patrón
  que la #14 en handover.
- Tasks T1-T6 en `[ ]`, ordenadas, cubren R1-R7.
- Nada peligroso (sin red, sin borrado de datos, solo `services/orchestrator/`).

## Observaciones no bloqueantes
1. `requirements.md` R6 contiene dos «DEBE» («NO DEBE abrir…; DEBE abrirla…»). El sentido es
   inequívoco y lo verifica un test existente; se puede dejar o partir en dos R en una edición futura.
2. T3: el `fetchall` falso debe devolver filas con la forma esperada por cada SELECT
   (`mark_update_if_new`, `last_messages`, `get_or_create_contact`); el implementador debe
   distinguirlas por el SQL recibido.
