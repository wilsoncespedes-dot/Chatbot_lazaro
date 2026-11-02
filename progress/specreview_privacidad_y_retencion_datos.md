# Spec review — #27 privacidad_y_retencion_datos (re-revisión final)

**Veredicto:** APPROVED

Se cerraron los dos bloqueantes de la revisión anterior.

## Comprobaciones

1. **Ningún caso activo queda retenido sin límite.** `PRIVACY_ACTIVE_CASE_MAX_DAYS` no tiene
   valor por defecto, es obligatorio en producción (R29), debe ser un entero ≥ 1 (R30) y
   estrictamente menor que `PRIVACY_RETENTION_DAYS` (R31). La purga de handover cierra y borra en
   una sola transacción los casos `open`/`assigned`/`timed_out` cuyo `created_at` es anterior al
   corte de casos activos, junto con sus `handover_requests` (R35, R36, T30). Se eliminó
   `retained_active` (design §5).
2. **No quedan huérfanos.** El script llama primero a handover y después al orchestrator
   (R41, R42). Si handover falla, el orchestrator no se llama (R43, T33). Si la purga de handover
   falla, se hace rollback completo (design §4). La demostración de §2.1
   (`case.created_at ≤ link.created_at`, `A < R` estricto) es correcta.
3. **EARS.** Los 52 requirements tienen exactamente un `DEBE`/`NO DEBE` (verificado uno por
   uno). R4, R11, R15 y R39 se partieron (R4–R6, R9–R11, R17–R18, R47–R48). La tabla de cobertura
   y los «Cubre:» de `tasks.md` cubren R1–R52.
4. **Datos recientes y registros operativos.** Los datos con fecha en el corte o posterior se
   conservan (R22, R23, R25, R37). Las tablas operativas, `privacy_consents`,
   `handover_notifications` y `handover_denials` no se tocan, y la decisión está justificada en
   design §2 (R26, R39, T22, T31).
5. **Valores del dueño.** S1–S6 siguen pendientes. `.env.example` deja vacías las 6 variables
   (R50). Mientras falten, el sistema falla cerrado: R1, R4–R6, R21, R29 y R32.
6. **Las 3 decisiones son seguras y están cubiertas:**
   - límite menor que la retención general: R31 y T28;
   - no llamar al orchestrator si falla handover: R43 y T33;
   - cerrar el caso sin notificar: S6 y design §2.1. Es un borrado directo en el repositorio, sin
     pasar por la ruta de notificación.

## No bloqueante (para el implementer)

- La demostración de §2.1 supone que orchestrator y handover usan el **mismo**
  `PRIVACY_RETENTION_DAYS`. En compose se garantiza porque ambos leen el mismo `.env`, pero en
  despliegues con variables separadas (Render) no. Hay que indicarlo en el comentario de
  `.env.example` y en `CONTRATOS.md` (T2, T34).
- En R35, «cerrar y borrar» equivale en la práctica a borrar, sin estado `closed` intermedio
  (design §2.1). Hay que seguir el design.
- Conviene que T30 compruebe que no se llama a ningún notificador al borrar casos activos.
