# Tasks — historial_conversacional_sin_login

- [x] T1 — Añadir helper de contexto conversacional sin sesión, manteniendo el contexto autenticado y leyendo mensajes solo con login opcional. Cubre: R1, R4, R7, R9.
- [x] T2 — Excluir el mensaje actual por rol, texto y timestamp, y limitar por `MEMORY_CONTEXT_MESSAGES`; respetar el switch `MEMORY_ENABLED`. Cubre: R2-R3, R5.
- [x] T3 — Añadir pruebas de historial opcional, límite, texto repetido con timestamp distinto, aislamiento, consentimiento, memoria apagada, sesión activa y login obligatorio. Cubre: R1-R7, R9.
- [x] T4 — Verificar estructuralmente el uso del repositorio actual y la ausencia de almacenamiento/servicio nuevo. Cubre: R8.
- [ ] T5 — La suite completa se lanzó vía `./init.sh` y se interrumpió tras más de dos minutos sin salida; `test_conversational_memory.py -q` pasó (9 tests). El reviewer aprobó estáticamente la feature; falta concluir la verificación completa. Cubre: R1-R9.
