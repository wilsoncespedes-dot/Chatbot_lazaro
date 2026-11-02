# Spec Driven Development (SDD)

> Este proyecto usa un flujo ligero: requirements → design → tasks → code.
> Un reviewer valida el spec antes de implementar; no requiere aprobación humana rutinaria.

## Estructura

Cada feature nueva (`"sdd": true` en `feature_list.json`) tiene una carpeta
dedicada en cuanto deja `pending`:

```
specs/<feature-name>/
├── requirements.md   # QUÉ se necesita (EARS notation)
├── design.md         # CÓMO se construirá (decisiones técnicas)
└── tasks.md          # PASOS concretos a implementar
```

El `feature-name` coincide con el campo `name` de `feature_list.json`.

## Estados de una feature

| Estado         | Significado                                                    |
|----------------|----------------------------------------------------------------|
| `pending`      | Sin spec. El `spec_author` es el primero en actuar.            |
| `spec_ready`   | Spec listo para revisión breve. Aún no se toca código.          |
| `in_progress`  | Spec aprobado. `implementer` trabajando.                       |
| `done`         | Código verde, `reviewer` aprobó, sesión cerrada.               |
| `blocked`      | Atascado. Razón en `progress/current.md`.                      |

## Revisión rápida del spec

Al terminar el `spec_author`, el `reviewer` hace una sola revisión enfocada
en aceptación, coherencia, dependencias y decisiones ya registradas. Si
aprueba, el leader pasa directamente a `in_progress`. Si pide cambios, el
autor corrige exclusivamente esos puntos y se hace una última revisión. No
se pide aprobación humana rutinaria ni se repiten revisiones completas.

Solo se bloquea ante una decisión de producto material que no esté en
`docs/proyecto.md`, el acceptance, decisiones anteriores o un default seguro
configurable. El blocker debe incluir la pregunta concreta y la opción
recomendada; se continúa con otras tareas independientes si existen.

```
pending → [spec_author] → spec_ready → [reviewer: spec] → in_progress → [implementer → reviewer: código] → done
```

## requirements.md — EARS estricto

Las requirements se redactan en **EARS** (Easy Approach to Requirements
Syntax). Cada requirement es un párrafo numerado con uno de estos cinco
patrones:

| Patrón         | Plantilla                                                   |
|----------------|-------------------------------------------------------------|
| **Ubicuo**     | `El sistema DEBE <acción>.`                                 |
| **Evento**     | `CUANDO <disparador>, el sistema DEBE <acción>.`            |
| **Estado**     | `MIENTRAS <estado>, el sistema DEBE <acción>.`              |
| **Opcional**   | `DONDE <feature opcional>, el sistema DEBE <acción>.`       |
| **No deseado** | `SI <evento no deseado> ENTONCES el sistema DEBE <acción>.` |

Reglas duras:

- Cada requirement tiene un id estable: `R1`, `R2`, ...
- Cada requirement DEBE ser verificable por al menos un test concreto.
- No mezcles varios `DEBE` en un mismo requirement. Si hay más de uno, parte.
- No uses verbos blandos ("podría", "puede", "soporta"). Solo `DEBE` / `NO DEBE`.

Ejemplo:

```markdown
## R1
CUANDO el orquestador recibe `POST /messages` con un `update_id` ya
procesado, el sistema DEBE responder `202` sin volver a procesar el mensaje.

## R2
SI una petición a `POST /messages` llega sin un `X-Service-Token` válido
ENTONCES el sistema DEBE responder `401` con `{"error": "unauthorized"}`.
```

Indica siempre **qué servicio** cumple cada requirement (en el texto o en un
encabezado por servicio) cuando la feature toca más de uno.

## design.md — decisiones técnicas

Captura **antes** de tocar código:

- Qué archivos se crean / modifican.
- Qué firmas nuevas aparecen (funciones, clases, comandos).
- Qué excepciones se reutilizan o se añaden.
- Qué alternativa se descartó y por qué (mínimo una).
- Qué dependencias nuevas hacen falta (nombre, versión acotada, licencia).
  El agente no las instala: el humano lo hace antes de implementar.
- **Supuestos a confirmar:** toda duda abierta de `docs/proyecto.md` §12 que
  la feature toque se resuelve como valor por defecto configurable (variable
  de entorno en `.env.example`) y se lista aquí. Nunca se decide en silencio.

NO es ingeniería desde primeros principios — apóyate en
`docs/architecture.md` y `docs/conventions.md`. El `design.md` documenta los
puntos donde tu feature roza la frontera de esas reglas.

## tasks.md — checklist ejecutable

Pasos discretos en orden, cada uno con checkbox. Cada task referencia al
menos un `R<n>` que cubre.

Ejemplo:

```markdown
- [ ] T1 — Añadir `is_duplicate(update_id)` en `services/orchestrator/orchestrator/domain.py`. Cubre: R1.
- [ ] T2 — Registrar `POST /messages` en `main.py` con verificación de token. Cubre: R1, R2.
- [ ] T3 — Añadir `test_duplicate_update_is_ignored` en `services/orchestrator/tests/test_messages.py`. Cubre: R1.
- [ ] T4 — Añadir `test_missing_token_returns_401` en el mismo archivo. Cubre: R2.
```

El `implementer` marca `[x]` cada task al completarla. El `reviewer`
rechaza si queda alguna `[ ]` sin justificación documentada.

## Trazabilidad (regla dura)

- Cada test en `services/*/tests/`, `contracts/tests/` o `eval/` debe poder mapearse a un `R<n>` de su spec.
- Cada `R<n>` debe tener al menos un test concreto.
- El `reviewer` comprueba esta correspondencia explícitamente y rechaza
  si falta.

El `implementer` documenta el mapa en `progress/impl_<name>.md`:

```markdown
## Trazabilidad
- R1 → `services/orchestrator/tests/test_messages.py::test_duplicate_update_is_ignored`
- R2 → `services/orchestrator/tests/test_messages.py::test_missing_token_returns_401`
```

## Cuándo NO aplica SDD

Todas las features de este proyecto llevan `"sdd": true`. Solo los cambios
del propio arnés (docs, `progress/`, configuración) se hacen sin spec.
