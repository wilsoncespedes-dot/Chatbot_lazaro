# Spec corregido — autorizacion_asesores (#14), 2026-10-31 (tercera vuelta, modo nocturno)

Estado en `feature_list.json`: sigue `blocked` (no se ha tocado). Archivos:
`specs/autorizacion_asesores/{requirements,design,tasks}.md`. No se ha tocado ni código ni
tests, no se ha ejecutado la suite y no se han editado los specs de otras features.

## Segunda vuelta de review (cambios 1-3): verificados
1. Orden de las tasks: la cabecera tiene el orden de ejecución (ahora con T76-T79) y el bloque
   «Verificación» (T52, T53) se ha movido al final del archivo, antes de la tabla.
2. T69 cubre solo R49 y no figura en la fila de R43.
3. Caso huérfano: el vocabulario cita ahora el texto real de S12 publicado por la #17, que ya
   incluye el `advisor_id` nulo («es nulo o ya no está en `ADVISOR_CHAT_IDS`»). Ya no es una
   derivación del spec_author.

## Decisiones del humano (2026-10-31) aplicadas (numeración 1-7 de su lista, usada en todo el spec)
- **1 (C5):** ya estaba aplicada (R26, R29, R30, R53); queda marcada como decidida. Alineada con §9
  de `specs/contrato_autorizacion_asesores/design.md` (todos sus puntos para la #14 están cubiertos).
- **2 (cierre contra asignación):** R41 se reescribe en su sitio: el cierre exige en la misma
  sentencia `status IN ('open','timed_out') OR (status='assigned' AND advisor_id = <quien cierra>)`.
  **R54 nuevo**: para un huérfano, la condición usa el `advisor_id` huérfano leído (también nulo).
  **R55 nuevo**: si no escribe y al releer el caso no está `closed` → `403` + denegación `close`
  (ya cerrado → `200` por R42/S8). El método pasa de `close_if_not_closed` a
  `close_if_still_allowed(case_id, advisor_id, allowed_assignee, at)`. Dos variantes de SQL
  (`advisor_id = %s` / `advisor_id IS NULL`) en lugar de `IS NOT DISTINCT FROM` (opción
  conservadora, en §9). T65 se reescribe (ahora espera `403`); **T76-T79 nuevos** (carrera con
  la propia asignación, carrera de cierre de un huérfano, repositorio falso y SQL parametrizado).
  T68 queda solo para la asignación. Se cierra la duda «cierre contra asignación».
- **3 (D7, D8, D9)** y **4 (D12, D13):** las marcas REVISAR desaparecen de R19, R20, R22, R30, R49
  y R51; pasan a §8.2 como decididas. D7 incluye el `403` por carrera perdida (R38, R55).
- **5 (candado):** ya estaba (R44, R45, T56, T70, T71); queda marcado como decidido.
- **6:** el candado del orquestador es la #18 `candado_repositorio_orquestador`; solo se
  referencia en design §3.5, §8.2 y §8.5, sin R ni tasks.
- **7 (huérfanos):** ya estaba (R46-R52); se añade la R54 y se cita el texto real de S12.
- §8.3 queda vacía. §8.4 conserva solo los riesgos (d) y (e) de la #12 como duda abierta.
- Reutilización: ninguna (design §10). Helpdock es AGPL y no se toma nada; sin dependencias nuevas.
- Trazabilidad comprobada: R1-R55 tienen tasks y la tabla coincide con los «Cubre» de cada task.

## Para el leader: acceptance de la #14 en `feature_list.json` (no lo he editado)
No hay contradicciones, pero hay huecos que conviene cubrir con criterios «Decidido por el
humano (2026-10-31)»:
- Huérfanos: el criterio dice «cuyo asesor ya no está en `ADVISOR_CHAT_IDS`». Conviene añadir
  «o cuyo `advisor_id` es nulo», como en S12 y en la decisión 7.
- Carrera: el criterio solo habla del `assign` que pierde. Falta que el cierre condicional no
  puede cerrar un caso que ya quedó asignado a otro asesor (`403` + denegación, R55).
- Faltan D7 (solo los `403` son denegación, incluida la carrera perdida), D8 (`500` si falla
  guardar la denegación), D9 (solo log sin contacto vinculado), D12 (recuento en el `lifespan`) y
  D13 (si falla, `WARNING` y arranca).
- Candado: el criterio dice que lo del orquestador «se planifica antes de la #16». Conviene
  nombrar la #18 `candado_repositorio_orquestador`.
- `description`: puede quitar «BLOQUEADA hasta que el humano revise su spec» si el leader lo
  considera resuelto. Eso lo decide el leader, no este spec.
