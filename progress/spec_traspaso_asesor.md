# Notas del spec — traspaso_asesor (feature 7)

Modo nocturno. Spec en `specs/traspaso_asesor/`, estado `spec_ready`.

## Decisión que el humano debe revisar primero

El contrato v1 no permite que handover sepa que un asesor respondió (el estado `assigned` vive
en handover y la respuesta pasa por el orquestador), y el acceptance exige ambas cosas. Se
propuso una ruta aditiva `POST /cases/{id}/assign` (S11, error `409 case_closed`) dentro de esta
feature (R11-R14, R33, R39, R40). Alternativa: rechazar el cambio y dejar la feature `blocked`.

## Otros supuestos (todos en design.md, «Supuestos a confirmar»)

- `no_advisors` pasa el caso a `timed_out` al instante (el cliente ya recibe `NO_ADVISORS_REPLY`).
- Reutilizar un caso abierto vuelve a avisar a todos los asesores.
- `advisor_id` no se valida contra `ADVISOR_CHAT_IDS`.
- Textos `NO_ADVISORS_REPLY` y `HANDOVER_TIMEOUT_REPLY` con valor por defecto configurable.
- Fuera de alcance: reenviar mensajes del cliente al asesor, worker/cron de `check-timeouts`, panel.

## Dependencias

`httpx` y `pg8000` en `services/handover/requirements.txt` (ya usadas por el orquestador).

## Impacto en tests existentes

Tests de la feature 4 que asuman «`no_advisors` no envía nada» deben actualizarse (T28).
