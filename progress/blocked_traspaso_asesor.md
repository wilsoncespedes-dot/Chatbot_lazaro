# Bloqueada: traspaso_asesor (#7)

**Qué se hizo:** spec redactado (`specs/traspaso_asesor/`) y aprobado por el reviewer en la 2.ª vuelta
(`progress/specreview_traspaso_asesor.md`). No se escribió código.

**Por qué se bloquea:** el spec consume `POST /cases/{id}/assign` (handover), cuyos modelos
`CaseAssignRequest` y `CaseAssignResponse` no existen en `contracts/lazaro_contracts/cases.py`. El spec
no puede tocar `contracts/` y el implementer se detiene si faltan (tasks.md, precondición).

**Decisión que necesita el humano:**
1. Crear una feature previa de contrato (añadir la ruta `assign` a `contracts/CONTRATOS.md`, los dos
   modelos, ejemplos y tests) y completarla, o ampliar el alcance de la #1.
2. Después, pasar la #7 a `in_progress`. El spec ya está aprobado por el reviewer (`auto_approved`
   pendiente de revisión humana: usar `/revisado`).
3. Confirmar los supuestos marcados "CONFIRMABLE" en `design.md` (p. ej. `timed_out` → `assigned`).

`./init.sh` queda verde (no hay cambios de código).
