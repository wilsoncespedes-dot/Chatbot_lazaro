# Tasks — retirar_asesores_telegram

- [x] T1 — Actualizar S6, S12, S13 y S14, y documentar `POST /advisors/sync`, `X-Advisor-Roster-Generation`, errores, identidades y respuestas de todas las rutas afectadas. Cubre: R14–R16, R17–R29, R36, R38–R40.
- [x] T2 — Añadir modelos Pydantic de roster, generación y respuestas actualizadas; exportarlos, crear ejemplos request/response y validar ejemplos, cuerpos inválidos y literales inválidas. Cubre: R9–R12, R14–R16, R27–R28, R39–R43.
- [x] T3 — Añadir repositorio de roster en handover y migración transaccional idempotente de asignaciones Telegram a perfiles o casos huérfanos; conservar datos existentes. Cubre: R9, R30–R33.
- [x] T4 — Implementar `POST /advisors/sync` con token requerido, códigos `401/422/500`, actualización atómica de roster/casos y generación persistida; probar autenticación válida/ausente/inválida, request inválido y error de persistencia. Cubre: R9–R13, R30–R37, R39, R42, R49–R50.
- [x] T5 — Cambiar autorización, listado, respuesta, asignación, transferencia, cierre y handover de handover a profile IDs y generación exacta; preservar S8/S11/S12/S14 y retirar avisos Telegram nuevos. Cubre: R14–R26, R29, R36.
- [x] T6 — Cambiar `POST /cases/{id}/client-message` para no notificar asesores por Telegram y devolver `available_in_panel` para casos asignados. Cubre: R27–R28.
- [x] T7 — Añadir estado/generación compartidos en la base de orchestrator; sincronizar al arranque y tras cambios pertinentes; usar transacciones para pending/synced y bloquear llamadas cuando pending en todas las instancias. Cubre: R13, R34–R37, R50.
- [x] T8 — Cambiar rutas y adaptadores del panel para usar `session.profile.id`, incluir generación y permitir asesores sin Telegram vinculado. Cubre: R4–R6, R29, R34–R37.
- [x] T9 — Retirar el manejo de `/responder` y `/cerrar` manteniendo el flujo habitual y `/consultar`; probar comando de Telegram heredado sin envío/respuesta/cierre del caso. Cubre: R1–R3, R47.
- [x] T10 — Adaptar pruebas de seguridad y regresión de contratos, handover, panel, comandos, configuración y migración; agregar cobertura de asesor sin Telegram, casos huérfanos, sync/multi-instancia y generación obsoleta sin quitar aserciones previas. Cubre: R1–R52.
- [x] T11 — Retirar `ADVISOR_CHAT_IDS` y textos de comandos de `.env.example`, `docker-compose.yml`, `render.yaml` y documentación vigente; actualizar arquitectura y operación. Cubre: R44–R46.
- [x] T12 — Actualizar `progress/current.md`, crear `progress/impl_retirar_asesores_telegram.md` con trazabilidad de cada R a pruebas, ejecutar `./init.sh` y dejar la revisión de código lista. Cubre: R48–R52.
