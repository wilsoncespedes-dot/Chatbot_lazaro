# Spec review — feature 1 `contratos_servicios` (vuelta 2)

**Veredicto:** SPEC_APPROVED

Segunda revisión, hecha contra `docs/specs.md`, `docs/architecture.md`,
`docs/conventions.md`, `docs/proyecto.md` §7 y §12, `.claude/nocturno.md` y los
7 criterios de `acceptance` de `feature_list.json`. Archivos revisados:
`specs/contratos_servicios/{requirements,design,tasks}.md`.

## Puntos de la vuelta 1

- [x] **Cambio requerido 1 (T12 sin `R<n>`).** Resuelto con la opción
  recomendada. Se eliminó la task de borrar `contracts/.gitkeep`. También se
  quitó la fila `borrar` de la tabla de `design.md` §2. Ahora `design.md` §8
  (líneas 340-341) y la cabecera de `tasks.md` (línea 6) dicen explícitamente
  que `.gitkeep` no se toca. Comprobado: `contracts/.gitkeep` sigue existiendo.
  Las tasks se renumeraron T1–T19. Los ids de requirement siguen estables y
  `docs/specs.md` solo exige ids estables para los `R<n>`, así que la
  renumeración es aceptable.
- [x] **Observación 1 (`requirements-dev.txt`).** Resuelta. T2 y `design.md` §8
  dicen que se conservan `pytest>=8,<9` y `httpx>=0.27,<1`, y coinciden con el
  archivo real.
- [x] **Observación 2 (instalación de pydantic).** Resuelta. T3 (línea 12) y
  `design.md` §8 (líneas 351-354) dicen: «Si la instalación se deniega por
  permisos o falla, la feature queda `blocked` con el error
  (`.claude/nocturno.md` §Dependencias); no buscar vías alternativas». La
  sección existe en `.claude/nocturno.md` (línea 88, «Dependencias y secretos
  en modo nocturno»).

## Checklist completo

### Cobertura de `acceptance`
- [x] AC1 → R1–R8 (8 rutas, Expone, Llama, Modelos, Request, Respuesta, Errores).
- [x] AC2 → R9–R12.
- [x] AC3 → R16, R17, R18, R20–R46, R52.
- [x] AC4 → R47–R49.
- [x] AC5 → R48, R19.
- [x] AC6 → R50, R51.
- [x] AC7 → R13, R14, R15, R33, R34, R37.

### EARS estricto
- [x] Cada R1–R52 tiene un solo `DEBE`/`NO DEBE`, sin verbos blandos. Patrones: ubicuo, no deseado (`SI … ENTONCES`) y evento (R52). No cambió nada respecto a la vuelta 1.
- [x] Ids R1–R52 estables y sin huecos.

### Verificable
- [x] Todos se pueden comprobar con tests concretos (`design.md` §5–§6; T12–T17).

### Sin invenciones
- [x] Lo que va más allá del literal está declarado como S1–S10 (`design.md` §9) y se copia a `CONTRATOS.md` (R13–R15). Esta vuelta no añadió comportamiento nuevo.
- [x] No resuelve en silencio ninguna duda de §12. Las cuatro que roza quedan listadas y se dejan a sus features. La ausencia de variables de entorno nuevas está razonada.

### Diseño
- [x] Respeta `architecture.md` §1 y §3.1: solo `contracts/` y una línea en `requirements-dev.txt`. Imports limitados a stdlib, pydantic y el propio paquete (R46).
- [x] Sin dependencias GPL/AGPL. `pydantic>=2.12,<3` está listada con su licencia (MIT).
- [x] 5 alternativas descartadas (§7) y sección «Supuestos a confirmar» (§9).
- [x] `conftest.py` raíz ya añade `contracts/` a `sys.path` (línea 7), como supone `design.md` §1.

### Tasks
- [x] Todas en `[ ]` (T1–T19).
- [x] Orden coherente: dependencias → paquete → ejemplos → documento → tests → cierre.
- [x] Cada task referencia al menos un `R<n>` (lo que falló en la vuelta 1 ya está corregido).
- [x] Entre todas cubren R1–R52. Ejemplos: R19 en T13, R49 en T12, R52 en T6 y T15, R17 en T3 y T17.

### Nada peligroso
- [x] No borra nada (ya no hay task de borrado).
- [x] No toca archivos fuera del repo.
- [x] Red: solo `pip install -r contracts/requirements.txt` en el `.venv`, para el único paquete declarado, con salida a `blocked` si falla.

## Observaciones (no bloquean)

1. El esbozo de `search.py` en `design.md` §3 (línea 110) usa `RootModel` sin
   mostrar su import. Es un esbozo de un módulo distinto de `common.py` y el
   implementer debe importar `RootModel` desde `pydantic`. Eso cumple R46.
