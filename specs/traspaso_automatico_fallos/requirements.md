# Requirements — traspaso automático tras fallos (#32)

Servicio: `orchestrator`; sin cambios de contrato. «Consulta RAG elegible» es un mensaje de cliente que supera los controles existentes y llega a `rag.search`.

## R1 — Política de motivos
CUANDO una consulta RAG elegible termina con un resultado, el sistema DEBE incrementar la racha solo si el motivo está en `AUTO_HANDOVER_FAILURE_REASONS`, una allowlist de `no_relevant_chunks` y `invalid_answer`.

## R2 — Exclusiones
CUANDO ocurre un error de RAG/LLM, el sistema NO DEBE contarlo como fallo de respuesta; tampoco debe contar comandos, aviso/aceptación de privacidad ni peticiones explícitas de asesor.

## R3 — Configuración
CUANDO se inicia el orquestador, el sistema DEBE leer `AUTO_HANDOVER_FAILURE_THRESHOLD` (entero ≥ 1, default `3`) y `AUTO_HANDOVER_FAILURE_REASONS` (default `no_relevant_chunks,invalid_answer`). `invalid_answer` solo se cuenta si `INVALID_ANSWER_HANDOVER=true`, preservando el control existente.

## R13 — Configuración inválida
SI `AUTO_HANDOVER_FAILURE_THRESHOLD` o `AUTO_HANDOVER_FAILURE_REASONS` no valida ENTONCES el sistema DEBE impedir el inicio y señalar la variable inválida.

## R4 — Aislamiento y persistencia
CUANDO el sistema registra un resultado, DEBE mantener el conteo persistente por `contact_id`, aislado de otras conversaciones.

## R5 — Idempotencia de actualización
SI un resultado con `update_id` ya fue registrado ENTONCES el sistema NO DEBE incrementar la racha otra vez.

## R6 — Reset
CUANDO una consulta RAG elegible produce una respuesta válida, el sistema DEBE reiniciar a cero la racha de esa conversación.

## R7 — Derivación al umbral
CUANDO una racha alcanza el umbral y aún no tiene derivación completada, el sistema DEBE iniciar una sola solicitud por el `POST /handover` existente, con el motivo fallido actual.

## R8 — No duplicar caso
MIENTRAS una racha ya tenga derivación completada, el sistema NO DEBE iniciar otra derivación automática por fallos adicionales de esa racha.

## R9 — Cliente con asesor notificado
CUANDO el traspaso automático responde `notified`, el sistema DEBE enviar y guardar `HANDOVER_ACK_REPLY` una sola vez para esa racha.

## R10 — Cliente sin asesor
CUANDO el traspaso automático responde `no_advisors`, el sistema DEBE enviar y guardar `NO_ADVISORS_REPLY` y cerrar la derivación de esa racha.

## R11 — Reintento transitorio
SI `POST /handover` no está disponible ENTONCES el sistema DEBE conservar la racha como pendiente y reintentar en la siguiente consulta elegible.

## R14 — Reutilizar en reintento
CUANDO se reintenta `POST /handover`, el sistema DEBE reutilizar cualquier caso activo que haya creado el intento anterior.

## R12 — Compatibilidad y verificación
CUANDO se ejecuta la batería completa tras el cambio, el sistema DEBE cubrir umbral, motivos admitidos/excluidos, reset, aislamiento, actualización repetida, reintento, reutilización de caso, `no_advisors` y comportamiento previo de comandos, privacidad, reenvío asignado y RAG, pasando `./init.sh` sin borrar ni debilitar pruebas existentes.
