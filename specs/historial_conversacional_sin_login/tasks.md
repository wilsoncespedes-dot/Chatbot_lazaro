# Tasks — historial_conversacional_sin_login

- [x] T1 — Añadir helper de contexto conversacional sin sesión, manteniendo el contexto autenticado y leyendo mensajes solo con login opcional. Cubre: R1, R4, R7, R9.
- [x] T2 — Excluir el mensaje actual por rol, texto y timestamp, y limitar por `MEMORY_CONTEXT_MESSAGES`; respetar el switch `MEMORY_ENABLED`. Cubre: R2-R3, R5.
- [x] T3 — Añadir pruebas de historial opcional, límite, texto repetido con timestamp distinto, aislamiento, consentimiento, memoria apagada, sesión activa y login obligatorio. Cubre: R1-R7, R9.
- [x] T4 — Verificar estructuralmente el uso del repositorio actual y la ausencia de almacenamiento/servicio nuevo. Cubre: R8.
- [x] T5 — Suite completa en CI remoto: 4914 passed, 1 skipped; builds de orquestador, Telegram Gateway, RAG y handover correctos; revisión estática aprobada. `./init.sh` local no pudo completarse porque WSL dejó de iniciar comandos. Cubre: R1-R9.
