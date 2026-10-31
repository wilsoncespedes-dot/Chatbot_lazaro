# AGENTS.md — Mapa de navegación para agentes de IA

> Este archivo es el **punto de entrada** para cualquier agente que trabaje en este
> repositorio. NO es una biblia de reglas: es un **mapa**. Lee solo lo que
> necesites cuando lo necesites (divulgación progresiva).

---

## 1. Antes de empezar (obligatorio)

1. Ejecuta `./init.sh` y verifica que termina sin errores. Si falla, **para**
   y resuelve el entorno antes de tocar código.
2. Lee `progress/current.md` para entender en qué estado quedó la última sesión.
3. Lee `feature_list.json`. Toda feature nueva (`"sdd": true`) pasa por
   **Spec Driven Development** — ver `docs/specs.md` y §4 de este archivo.
4. Lee `docs/specs.md` antes de tocar cualquier spec o feature `sdd: true`.
5. Lee `docs/proyecto.md` para entender qué es el chatbot y qué dudas siguen
   abiertas (no las resuelvas inventando).

## 2. Mapa del repositorio

| Archivo / carpeta            | Qué contiene                                                                | Cuándo leerlo |
|------------------------------|-----------------------------------------------------------------------------|---------------|
| `feature_list.json`          | Lista de tareas con estado (`pending` / `spec_ready` / `in_progress` / `done` / `blocked`) | Siempre, al empezar |
| `progress/current.md`        | Estado de la sesión actual                                                  | Siempre, al empezar |
| `progress/history.md`        | Bitácora append-only de sesiones anteriores                                 | Si necesitas contexto histórico |
| `specs/<feature>/`           | `requirements.md` + `design.md` + `tasks.md` (Kiro-style)                   | Antes de implementar cualquier feature con `"sdd": true` |
| `docs/architecture.md`       | Qué significa "hacer un buen trabajo" en este proyecto                      | Antes de implementar |
| `docs/conventions.md`        | Reglas de estilo, nombres, estructura                                       | Antes de escribir código |
| `docs/specs.md`              | Proceso SDD: EARS notation, los 3 archivos, puerta de aprobación humana     | Antes de redactar o leer un spec |
| `docs/verification.md`       | Cómo verificar que tu trabajo funciona (incluye trazabilidad requirements)  | Antes de declarar una tarea como `done` |
| `CHECKPOINTS.md`             | Criterios objetivos de "estado final correcto"                              | Para auto-evaluarte |
| `.claude/agents/`            | Definiciones de subagentes (`leader`, `spec_author`, `implementer`, `reviewer`) | Si orquestas trabajo |
| `.claude/nocturno.md`        | Instrucciones del leader en modo nocturno                                   | Si trabajas sin humano |
| `.claude/hooks/`             | Verificación automática: tests tras cada edición, `init.sh` al terminar      | Si algo se ejecuta "solo" |
| `.claude/settings.json`      | Permisos y hooks activos: copia de `.claude/modes/<modo>.json` (la pone `./modo.sh`) | Si un comando pide permiso |
| `progress/nocturno_*.md`     | Informe de cada noche de trabajo autónomo                                   | Al volver de una noche |
| `docs/proyecto.md`           | Qué es el chatbot, decisiones, contratos, riesgos y dudas abiertas          | Siempre, antes de redactar o implementar un spec |
| `contracts/`                 | Contratos HTTP/JSON entre servicios (`CONTRATOS.md` + `lazaro_contracts`)   | Antes de tocar cualquier ruta entre servicios |
| `services/<servicio>/`       | Código y tests de cada microservicio                                        | Para implementar |
| `.env.example`               | Variables de entorno (nunca leas `.env`)                                    | Al añadir configuración |
| `THIRD_PARTY_NOTICES.md`     | Código copiado de otros repos y su licencia                                 | Si copias código |
| `referencias/`               | Repos de referencia clonados (solo lectura, fuera de git)                   | Si un spec reutiliza piezas de otro repo |

## 3. Reglas duras (no negociables)

- **Una sola feature a la vez.** No mezcles cambios de varias tareas en la misma sesión.
- **No declares una tarea `done` sin pruebas verdes.** Ejecuta `./init.sh` y
  asegúrate de que el bloque de tests pasa al 100%.
- **No saltes la fase de spec.** Toda feature con `"sdd": true` debe pasar
  por `spec_author` y obtener aprobación humana antes de tocar código.
- **No saltes la puerta de aprobación humana.** El leader detiene el flujo
  en `spec_ready` y espera. Única excepción: en **modo nocturno** (§7) la
  puerta la ocupa el `reviewer` y la feature queda con `"auto_approved": true`.
- **Documenta lo que haces** en `progress/current.md` mientras trabajas, no al final.
- **Deja el repositorio limpio** antes de cerrar la sesión (ver §5).
- **Si no sabes algo, busca en `docs/`** antes de inventarlo.

## 4. Flujo de trabajo (SDD)

```
pending → [spec_author] → spec_ready → ⏸ HUMANO → in_progress → [implementer → reviewer] → done
```

1. El leader detecta la primera feature `pending` con `"sdd": true`.
2. El leader lanza `spec_author`, que crea
   `specs/<name>/{requirements,design,tasks}.md` y marca el status como
   `spec_ready`.
3. **Pausa.** El humano lee el spec en `specs/<name>/` y aprueba (o pide cambios).
4. Una vez aprobado, el leader cambia el status a `in_progress` y lanza `implementer`.
5. El implementer ejecuta `tasks.md` una a una, marcándolas `[x]`.
6. El reviewer verifica trazabilidad `R<n>` ↔ test y tasks completas;
   aprueba o rechaza.
7. Si aprueba, el implementer marca `done` y mueve el resumen a
   `progress/history.md`.

## 5. Cierre de sesión (lifecycle)

Antes de terminar:

1. Ejecuta `./init.sh` — todo verde.
2. Si la tarea está acabada: marca `status: "done"` en `feature_list.json`.
3. Mueve el resumen de `progress/current.md` al final de `progress/history.md`.
4. Vacía `progress/current.md` dejando solo la plantilla.
5. No dejes archivos temporales, ni `print()` de debug, ni TODOs sin contexto.

## 6. Si te bloqueas

- Relee la sección relevante de `docs/`.
- Si la herramienta no hace lo que esperas, **no inventes un workaround**:
  documenta el bloqueo en `progress/current.md` y para la sesión.

## 7. Modos del arnés

| Modo          | Agente principal  | Puerta del spec            | Permisos de shell                         |
|---------------|-------------------|----------------------------|-------------------------------------------|
| `supervisado` | `leader` (CLAUDE.md) | El humano dice «aprobado»  | Todo permitido; pregunta antes de lo arriesgado (`git push`, `rm -rf`…) |
| `nocturno`    | `leader` + `.claude/nocturno.md` | `reviewer` (revisión de spec) | Todo permitido sin preguntar; lo arriesgado (`git push`, `rm -rf`, `sudo`…) se deniega |

- Cambiar de modo: `./modo.sh supervisado` o `./modo.sh nocturno` (y
  reiniciar Claude Code). `./modo.sh` muestra el modo actual.
- Trabajo autónomo continuo: `./nocturno.sh`. Lanza una sesión por
  feature, se para sola con frenos de seguridad y deja un informe en
  `progress/nocturno_<fecha>.md`.
- En modo nocturno, si te bloqueas **no pares toda la noche**: marca la
  feature `blocked`, explica el motivo en `progress/blocked_<name>.md`,
  deja `./init.sh` verde y termina la sesión. El script sigue con la
  siguiente.
