# Tasks — traspaso automático tras fallos (#32)

- [x] T1 — Configuración/validación del umbral y allowlist; respetar `INVALID_ANSWER_HANDOVER`; documentar defaults en `.env.example`. Cubre: R1–R3, R13.
- [x] T2 — Persistencia atómica/idempotente por contacto y update en fake/Postgres, incluyendo racha y estado de reintento; SQL parametrizado. Cubre: R4, R5, R8, R11, R14.
- [x] T3 — Cablear resultados elegibles, respuesta válida y outcomes excluidos en `process_message`; reutilizar `_handover`. Cubre: R1, R2, R6, R7, R11.
- [x] T4 — Gestionar estado `notified`/`no_advisors`, guardar el aviso existente y cerrar la racha para evitar nuevos traspasos. Cubre: R8–R10.
- [x] T5 — Tests de umbral/config inválida, outcomes, reset, contacto aislado, update duplicado, reinicio, handover transitorio, reutilización de caso, sin asesores y compatibilidad. Cubre: R1–R14.
- [x] T6 — Ejecutar `./init.sh`, mapear R1–R14 a tests en `progress/impl_traspaso_automatico_fallos.md` y solicitar revisión de código. Cubre: R12–R14.
