# Tasks — health checks de dependencias (#47)

- [x] T1 — Ampliar `HealthResponse`, documentar en `contracts/CONTRATOS.md` los dos resultados de `GET /health` y añadir ejemplos JSON saludable y no saludable sin cambiar la representación saludable existente. Cubre: R1, R2.
- [x] T2 — Añadir `HEALTHCHECK_TIMEOUT_SECONDS` y probes Redis/PostgreSQL inyectables, con timeout acotado y operación de solo lectura; implementar fakes controlables para estado, error y timeout. Cubre: R3, R4, R5, R8.
- [x] T3 — Integrar probes en `/health` de los cuatro servicios y responder 200/503 con el cuerpo seguro especificado. Cubre: R1, R2, R3, R4.
- [x] T4 — Configurar healthchecks en Docker Compose para servicios de aplicación y Redis, además de dependencias de arranque saludables. Cubre: R6, R7.
- [x] T5 — Añadir pruebas del modelo ampliado, de ambos ejemplos JSON y de la documentación del contrato; cubrir además salud, dependencia caída, timeout, ausencia de secretos y configuración Compose. Cubre: R1–R8.
- [x] T6 — Ejecutar `./init.sh`, corregir fallos dentro del alcance y registrar trazabilidad `R<n> → test` en `progress/impl_healthcheck_dependencias.md`. Cubre: R9.
