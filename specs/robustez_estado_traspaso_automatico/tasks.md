# Tasks — robustez del estado de traspaso automático (#34)

- [x] T1 — Extender fake y PostgreSQL `purge_personal_data`: borrar outcomes con `at < cutoff` y outcomes/rachas de contactos inactivos; incluir conteos en resultado y auditoría de purga. Cubre: R1–R3.
- [x] T2 — Garantizar que una excepción de `_handover` deja la racha en `retry` y se propaga. Cubre: R4.
- [x] T3 — Añadir pruebas para corte, contacto purgado, conteos, rollback y excepción; conservar pruebas existentes de privacidad/handover. Cubre: R1–R5.
- [x] T4 — `./init.sh`: 2092 passed, 1 skipped; trazabilidad R1–R6 registrada. Cubre: R6.
