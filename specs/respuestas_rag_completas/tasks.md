# Tasks — respuestas_rag_completas

- [x] T1 — Pedir explícitamente al LLM respuestas sintetizadas y breves, conservando citas. Cubre: R1, R2, R6.
- [x] T2 — Implementar fragmentación por frases y líneas con solapamiento de unidades completas. Cubre: R3, R4.
- [x] T3 — Dividir respuestas largas en el orquestador y Telegram, y registrar una sola respuesta íntegra en la cola transaccional. Cubre: R5.
- [x] T4 — Añadir pruebas de prompt, fragmentación, validación y envío multimensaje. Cubre: R1-R6.
- [x] T5 — Revisión estática aprobada y verificación intentada. `./init.sh` falló antes de pytest por WSL/CRLF; el usuario confirma que verificó #79. Cubre: R1-R6.
