# Spec review — feature #41 panel_asesores_multicanal

**Veredicto:** APPROVED (modo nocturno; reviewer aprueba en lugar del humano)

## Cobertura acceptance -> R -> tasks
- A1 bandeja ambos canales, canal/estado/espera/asignación, roles y autorización por caso: R1–R13 -> T18, T22, T23, T25.
- A2 responder/transferir/resolver/devolver por adaptador del canal con ventana/plantilla: R14–R39, R74 -> T1–T5, T9, T10, T14–T17, T26, T27.
- A3 historial, resumen, datos permitidos, memoria, auditoría sin exponer otros clientes: R40–R55 -> T19, T20, T22, T28, T29 (R44 filtra ventanas de sesión ajenas; R53 limita la auditoría a ids internos).
- A4 cola de supresión con prioridad, fecha límite y ejecución humana con resultado: R60–R70 -> T21, T23, T24, T30.
- A5 tests ambos canales, permisos, auditoría, respuesta, supresión, init verde: T25–T32.
- Todas las tasks en `[ ]`, ordenadas, con sus R; entre todas cubren R1–R74.

## Coherencia verificada contra el código
- `advisor_client_memory`, `execute_suppression(request_id, actor_profile_id, ...)`, `SUPPRESSION_EXECUTOR_ROLES`, `session_window`, `TemplateBlock`, `send_channel_blocks`, `ADVISOR_RESOLVED/RETURNED`, `_raise_authorization_error`, `try_assign` y `StoredSuppressionRequest.contact_id/channel` existen como describe el design.
- R13 corrige un defecto real: `PostgresRepository.get_case_contact` (repository.py:2058) solo selecciona `id, telegram_user_id, chat_id`, así que pierde el canal WhatsApp.
- Transferencia: contrato aditivo en `contracts/` con ruta nueva en handover y escritura condicional; no cambia rutas existentes. Respeta las 3 capas y el patrón de denegación de handover.
- Sin dependencias nuevas (design §Dependencias). No usa la red fuera de los adaptadores existentes ni toca archivos fuera del repo.
- Supresión: solo la ejecuta una persona con rol ejecutor, con CSRF, vía la `execute_suppression` de #40; ninguna ruta de IA borra datos (coherente con #39/#40).

## Supuestos (S1–S8) aceptados como defaults seguros
Identidad del asesor por `telegram_user_id` (compatibilidad temporal de la fase 6), plantillas y plazos en el entorno (pasan a #42), 15 días hábiles sin festivos (pendiente de revisión legal), `<meta refresh>` en lugar de tiempo real (panel sin JS), supervisor/notas/respuestas guardadas fuera del acceptance. Todos son configurables o están diferidos de forma explícita; ninguno es irreversible.

## Observaciones no bloqueantes (para el implementer)
1. EARS editorial: R12, R25, R30, R31 y R69 combinan dos obligaciones; R3 usa "cuando" dentro de un requisito ubicuo. Son verificables tal cual; los tests deben cubrir cada rama.
2. La ventana WhatsApp se calcula con los mensajes `user` guardados; si #35 no guarda los mensajes previos al consentimiento, la ventana sale cerrada (conservador). El gateway sigue siendo la segunda barrera (R21).
3. R36 conserva el comportamiento actual de `close_case`, que guarda el aviso con `_send` (test_advisor_panel.py:505); R39 solo omite el envío con la ventana cerrada.
4. Leader: registrar la feature posterior que retire `/responder`, `/cerrar` y la identidad Telegram de los asesores (S1), y la de supervisor (S8).
