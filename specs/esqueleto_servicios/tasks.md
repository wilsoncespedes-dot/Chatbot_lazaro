# Tasks — esqueleto_servicios (feature #2)

> Orden pensado para que cada paso sea verificable. Python del proyecto: el que
> detecte `./init.sh` (`.venv/Scripts/python.exe` en Windows). Cada test lleva
> en su docstring el `R<n>` que cubre. Reglas de nombres de tests, conftest y
> lectura de YAML como texto: `design.md` §7 (la unicidad de nombres de archivo
> de test es obligatoria). **No se toca** `contracts/`, `init.sh`, `pytest.ini`,
> `conftest.py` raíz ni `docs/`. R7 está retirado (no tiene task ni test).

## Dependencias

- [ ] T1 — Crear `services/<svc>/requirements.txt` en los 4 servicios con el contenido exacto de `design.md` §8.1. Cubre: R5.
- [ ] T2 — En `requirements-dev.txt` añadir las 4 líneas `-r services/<svc>/requirements.txt`, conservando las existentes y sin añadir paquetes nuevos. Cubre: R37.
- [ ] T3 — Instalar en el `.venv`, una vez por servicio: `<python de init.sh> -m pip install -r services/<svc>/requirements.txt` para `telegram_gateway`, `orchestrator`, `rag` y `handover` (forma permitida por `nocturno.md` §Dependencias). No usar `pip install <paquete>` suelto ni `-r requirements-dev.txt`. Si falla o se deniega, la feature queda `blocked` con el error; no buscar vías alternativas. Cubre: R5.

## Servicios (repetir T4–T8 para `telegram_gateway`, `orchestrator`, `rag`, `handover`)

- [ ] T4 — Crear `services/<svc>/<svc>/__init__.py`, `domain.py` (con `DomainError`) y `adapters/__init__.py`. Cubre: R1, R20.
- [ ] T5 — Crear `services/<svc>/<svc>/config.py` con `Settings` (`service_token: str = ""`, sin `env_file`) según `design.md` §3. Cubre: R4, R15, R41.
- [ ] T6 — Crear `services/<svc>/<svc>/main.py` con `SERVICE_NAME`, `PUBLIC_PATHS`, `create_app()` (middleware de token con `hmac.compare_digest`, handlers de error, `GET /health`) y `app = create_app()` según `design.md` §3–§4. Cubre: R2, R3, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R41, R42.
- [ ] T7 — Crear `services/<svc>/Dockerfile` según `design.md` §5 (base `python:3.12-slim`, `USER app` como decisión de diseño sin requirement, `CMD uvicorn <svc>.main:app --host 0.0.0.0 --port 8000`). Cubre: R6.
- [ ] T8 — Crear `services/<svc>/tests/test_<svc>_app.py` (sin `__init__.py` ni `conftest.py` en `tests/`; helper `_block` local según `design.md` §7.2) con los 25 tests de la tabla de `design.md` §7.3, cada uno con `"""R<n>: ..."""`. Los tests de compose (R24, R26, R27) fallarán hasta T11. Cubre: R1, R2, R3, R4, R5, R6, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R24, R26, R27, R30, R38, R41, R42.
- [ ] T9 — Borrar `services/.gitkeep`. Cubre: R1.

## Infraestructura

- [ ] T10 — Crear `scripts/db/init/01_extensions.sql` con `CREATE EXTENSION IF NOT EXISTS vector;`. Cubre: R28.
- [ ] T11 — Crear `docker-compose.yml` respetando el formato obligatorio de `design.md` §5 (sangría de 2 espacios; postgres `pgvector/pgvector:pg16` con `env_file: [.env]` y montaje de `./scripts/db/init`; `redis:7.2-alpine`; los 4 servicios con `build: {context: ., dockerfile: services/<svc>/Dockerfile}`, `env_file: [.env]` y `ports: ["800N:8000"]`). Cubre: R21, R22, R23, R24, R25, R26, R27, R29.
- [ ] T12 — Crear `.dockerignore` en la raíz con las entradas de `design.md` §2. Cubre: R6.
- [ ] T13 — Añadir a `.env.example` el bloque `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (valores de ejemplo `lazaro`), sin borrar nada; comprobar que `SERVICE_TOKEN` sigue presente y que no hay `${VAR}` en el compose sin su línea. Cubre: R30, R31, R32.
- [ ] T14 — Crear `.github/workflows/ci.yml` respetando el formato de `design.md` §6. Cubre: R33, R34, R35, R36.

## Tests de artefactos globales

- [ ] T15 — Crear `services/orchestrator/tests/test_orchestrator_infra.py` (sin `__init__.py` ni `conftest.py`; `ROOT = Path(__file__).resolve().parents[3]`; helper `_block` local, sin PyYAML) con los 13 tests de la tabla de `design.md` §7.3. Cubre: R21, R22, R23, R25, R28, R29, R31, R32, R33, R34, R35, R36, R37.

## Verificación

- [ ] T16 — Ejecutar `python -m pytest --co -q` desde la raíz y comprobar que se recogen, sin errores de colección, los 5 archivos nuevos (`test_<svc>_app.py` ×4 y `test_orchestrator_infra.py`) y los de `contracts/tests/`. Pegar el resumen en `progress/impl_esqueleto_servicios.md`. Cubre: R39.
- [ ] T17 — Ejecutar `python -m pytest` desde la raíz: código de salida `0`, todos verdes. Pegar el resumen en `progress/impl_esqueleto_servicios.md`. Cubre: R43.
- [ ] T18 — Ejecutar `./init.sh`: código de salida `0` y bloque de tests en `[OK] Todos los tests pasan`. Pegar el resumen en `progress/impl_esqueleto_servicios.md`. Cubre: R40.
- [ ] T19 — Escribir en `progress/impl_esqueleto_servicios.md` el mapa de trazabilidad `R<n> → archivo::test` para R1–R6 y R8–R43 (R7 retirado; R39/R40/R43 → salidas de T16/T18/T17). Cubre: R1, R2, R3, R4, R5, R6, R8–R43.
