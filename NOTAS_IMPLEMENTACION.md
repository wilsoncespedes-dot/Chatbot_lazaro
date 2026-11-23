# Notas de implementación — rama `feat/produccion-multicanal`

Decisiones tomadas sin consultar (decisión + motivo), por fase. Al final: resumen,
pendientes, variables nuevas y pasos de despliegue.

## Decisión general

- **Sin el arnés del proyecto.** Por instrucción expresa del dueño, estas fases no
  pasan por `feature_list.json`, specs ni el flujo leader/implementer; el código lo
  escribe Claude directamente. Motivo: prioridad de velocidad pedida por el dueño.

## Fase 1 — Migraciones y secretos

- **Runner en `migrations/runner.py` (`python -m migrations.runner`).** Las SQL y el
  runner viven juntos en `migrations/`, con su propia imagen (`migrations/Dockerfile`,
  solo `pg8000`). Motivo: el runner no debe depender de la imagen de ningún servicio.
- **Servicio `migrate` en docker compose** (`restart: "no"`); los servicios con base
  esperan `service_completed_successfully`. Motivo: corre una vez por `docker compose
  up` del despliegue y nunca desde los servicios (el deadlock de 5d1a398 desaparece:
  ya no hay DDL concurrente).
- **Lock de sesión `pg_advisory_lock(7301985)`** (clave distinta del antiguo turno
  7301984) y **una transacción por archivo** junto con su fila en
  `schema_migrations(version, nombre, sha256, aplicada_en)`.
- **Checksum estricto:** si un archivo ya aplicado cambia, el runner aborta. Motivo:
  las migraciones aplicadas son inmutables; se corrige con una nueva.
- **Archivos ejecutados con el protocolo simple de Postgres** (cursor sin parámetros
  en pg8000), así un `.sql` puede tener varias sentencias sin partirlo a mano.
- **`{{EMBEDDINGS_DIM}}`**: la dimensión de `chunks.embedding` dependía de la
  configuración del RAG; el runner la sustituye (por defecto 1536, validada como
  entero). Solo se aceptan variables de una lista blanca.
- **0001 se generó desde las constantes de DDL** (`_SCHEMA`, `_INDEXES`,
  `_MIGRATIONS` del orquestador, handover, canales, buzón, RAG y MCP) con el texto
  exacto, en secciones `-- ── <servicio>`. Las constantes se eliminaron; los tests
  de esquema leen ahora las secciones con `migrations.section(...)`.
- **MCP:** `schema.initialize` ya no crea tablas; solo siembra las ofertas de
  demostración si `MCP_DEMO_SEED=true` (es dato, no esquema).
- **`require_service_token` en `lazaro_contracts.production`** (reusa la lista de
  marcadores `PLACEHOLDERS`: `cambia-esto`, `changeme`, `test`, `xxx`…). Se llama en
  el `lifespan` de los 5 servicios y en los workers del orquestador. Motivo: validar
  en el arranque real y no al importar el módulo (varios `main.py` crean la app al
  importarse, y los tests los importan).
- **`POSTGRES_PASSWORD:?`** en compose: sin valor, compose se niega a arrancar.
- Tests de integración del runner contra Postgres real: `migrations/tests/
  test_runner_integracion.py`, se activan con `TEST_DATABASE_URL` (contenedor
  `pgvector/pgvector:pg16` local desechable). Los tests en memoria que simulaban el
  backfill de #36 se sustituyeron por estos.
- `render.yaml` (despliegue antiguo en Render) no ejecuta el runner; no se tocó
  porque el despliegue vigente es docker compose en EC2.
