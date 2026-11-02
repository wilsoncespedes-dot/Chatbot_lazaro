# Review de spec — feature 31 (busqueda_hibrida_rag)

**Veredicto:** SPEC_APPROVED

- **Cobertura:** los criterios de aceptación están cubiertos por R1–R6: combinación/deduplicación (R1), RRF sin reemplazar score (R2–R3), filtros/límites/contrato (R4–R5) y evaluación comparable antes de habilitar por defecto (R6).
- **EARS y verificabilidad:** R1–R6 usan un patrón EARS, un solo `DEBE` por requisito y describen comportamiento comprobable. Las tareas enlazan esos requisitos con pruebas.
- **Diseño:** conserva `POST /search`, separación dominio/adaptador/evaluación, SQL parametrizado y dependencias existentes. Incluye alternativa descartada y resuelve la condición de mantener el modo apagado si la evaluación no cumple los criterios; no toca dudas abiertas de `docs/proyecto.md` §12.
- **Tasks:** T1–T5 siguen pendientes y en orden; sus referencias cubren R1–R6.
- **Seguridad/licencias:** no añade rutas, dependencias, copia de código ni acceso a datos externos.
