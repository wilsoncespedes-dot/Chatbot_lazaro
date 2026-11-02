# AGENTS.md — Mapa de navegación para agentes de IA

> Este archivo es el **punto de entrada** para cualquier agente que trabaje en este
> repositorio. NO es una biblia de reglas: es un **mapa**. Lee solo lo que
> necesites cuando lo necesites (divulgación progresiva).

---

## 1. Antes de empezar (obligatorio)

1. Lee `progress/current.md` y `feature_list.json` para ubicar el trabajo.
2. Ejecuta `./init.sh` solo al implementar/revisar código o si el entorno
   parece roto; no la ejecutes para leer o editar specs/documentación.
3. Toda feature nueva (`"sdd": true`) pasa por
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
| `docs/specs.md`              | Proceso SDD: EARS notation y los 3 archivos                                  | Antes de redactar o leer un spec |
| `docs/verification.md`       | Cómo verificar que tu trabajo funciona (incluye trazabilidad requirements)  | Antes de declarar una tarea como `done` |
| `CHECKPOINTS.md`             | Criterios objetivos de "estado final correcto"                              | Para auto-evaluarte |
| `.claude/agents/`            | Definiciones de subagentes (`leader`, `spec_author`, `implementer`, `reviewer`) | Si orquestas trabajo |
| `.claude/nocturno.md`        | Instrucciones del leader en modo nocturno                                   | Si trabajas sin humano |
| `.claude/hooks/`             | Scripts de verificación manual                                             | Si hace falta revisar el entorno |
| `.claude/settings.json`      | Permisos y hooks activos: copia de `.claude/modes/<modo>.json` (la pone `./modo.sh`) | Si un comando pide permiso |
| `opencode.json` / `.opencode/agents/` | Modelo DeepSeek y permisos del escritor OpenCode | Para implementar una feature aprobada |
| `scripts/run_opencode_writer.sh` | Puente invocado por el implementer Claude en ambos modos | Al implementar o corregir código |
| `progress/nocturno_*.md`     | Informe de cada noche de trabajo autónomo                                   | Al volver de una noche |
| `docs/proyecto.md`           | Qué es el chatbot, decisiones, contratos, riesgos y dudas abiertas          | Siempre, antes de redactar o implementar un spec |
| `contracts/`                 | Contratos HTTP/JSON entre servicios (`CONTRATOS.md` + `lazaro_contracts`)   | Antes de tocar cualquier ruta entre servicios |
| `services/<servicio>/`       | Código y tests de cada microservicio                                        | Para implementar |
| `.env.example`               | Variables de entorno (nunca leas `.env`)                                    | Al añadir configuración |
| `THIRD_PARTY_NOTICES.md`     | Código copiado de otros repos y su licencia                                 | Si copias código |
| `referencias/`               | Repos de referencia clonados (solo lectura, fuera de git)                   | Si un spec reutiliza piezas de otro repo |

## 3. Reglas duras (no negociables)

- **Una sola feature a la vez.** No mezcles cambios de varias tareas en la misma sesión.
- **No declares una tarea `done` sin pruebas verdes.** Tras implementar, corre
  `./init.sh` una vez y solicita revisión de código.
- El reviewer aprueba el spec en una pasada enfocada. Si pide cambios, corrige
  solo esos puntos y vuelve a revisar una vez.
- Bloquea solo ante decisiones de producto materiales que no puedan resolverse
  con el acceptance, `docs/proyecto.md`, decisiones previas o un default seguro.
- Mantén informes breves y no dupliques análisis ya registrados.
- **Documenta lo que haces** en `progress/current.md` mientras trabajas, no al final.
- **Deja el repositorio limpio** antes de cerrar la sesión (ver §5).
- **Si no sabes algo, busca en `docs/`** antes de inventarlo.

## 4. Flujo de trabajo (SDD)

```
pending → [spec_author] → spec_ready → [reviewer: spec] → in_progress → [implementer → reviewer: código] → done
```

1. El leader detecta la primera feature `pending` con `"sdd": true`.
2. El leader lanza `spec_author`, que crea
   `specs/<name>/{requirements,design,tasks}.md` y marca el status como
   `spec_ready`.
3. Reviewer valida el spec en una pasada enfocada. Si aprueba, el leader cambia
   el status a `in_progress` y lanza `implementer` sin esperar aprobación manual.
4. El implementer ejecuta `tasks.md` una a una, marcándolas `[x]`.
6. El reviewer verifica trazabilidad `R<n>` ↔ test y tasks completas;
   aprueba o rechaza.
7. Si aprueba, el implementer marca `done` y mueve el resumen a
   `progress/history.md`.

## 5. Cierre de sesión (lifecycle)

Antes de terminar:

1. Si hubo cambios de código, ejecuta `./init.sh` — todo verde.
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
| `supervisado` | `leader` (CLAUDE.md); OpenCode/DeepSeek escribe | Reviewer aprueba el spec | Claude coordina; OpenCode solo edita archivos del proyecto y no ejecuta shell |
| `nocturno`    | `leader` + `.claude/nocturno.md`; OpenCode/DeepSeek escribe | `reviewer` (revisión de spec) | Claude coordina; OpenCode tiene los mismos límites; lo arriesgado se deniega |

- Cambiar de modo: `./modo.sh supervisado` o `./modo.sh nocturno` (y
  reiniciar Claude Code). Ambos modos usan OpenCode/DeepSeek para escribir código.
  `./modo.sh` muestra el modo actual.
- Trabajo autónomo continuo: `./nocturno.sh`. Lanza una sesión por
  feature, se para sola con frenos de seguridad y deja un informe en
  `progress/nocturno_<fecha>.md`.
- En modo nocturno, si te bloqueas **no pares toda la noche**: marca la
  feature `blocked`, explica el motivo en `progress/blocked_<name>.md`,
  deja `./init.sh` verde y termina la sesión. El script sigue con la
  siguiente.
