# Spec review — #55 evaluacion_ataques_y_preguntas_reales

**Veredicto:** APPROVED (segunda revisión)

El hallazgo bloqueante de la primera revisión está resuelto:

- **`--url` obligatorio y `--preguntas` repetible:** el nuevo R33 (`requirements.md`) los conserva. `--url` es la base del orquestador para preguntas y ataques. El mínimo de preguntas (R25, R26, R29) se cuenta sobre el total de todos los archivos `--preguntas`. R33 sigue el patrón EARS y tiene un solo `DEBE`.
- **Comando en `docs/verification.md`:** R30 exige un comando de ejemplo completo con `--url`, `--modo orquestador`, `--preguntas`, `--ataques` y `--minimo-preguntas`. T13 lo repite y cubre R30, R31 y R33.
- **Tests y tasks:**
  - T12 incluye varios `--preguntas` que suman para el mínimo y que `--url` sea obligatorio y se use en los ataques. Cubre R33.
  - T8 conserva `--url` y `--preguntas`. Cubre R33.
  - R32 incluye R33.
- **Alcance y status:** no hay cambios fuera de `specs/evaluacion_ataques_y_preguntas_reales/` y de este informe. El status en `feature_list.json` sigue siendo `spec_ready`, y las tasks T1–T14 siguen en `[ ]`, en orden y con sus R<n>.

## Nota no bloqueante
- `design.md` no menciona `--url` ni R33. No es bloqueante porque R33 y las tasks lo cubren. El implementador debe leer R33 y no asumir otro comportamiento.
- Sigue en pie la sugerencia anterior: `sin_respuesta` y `error` no se tratan como resistidos (R10 y R17 ya lo dicen).
