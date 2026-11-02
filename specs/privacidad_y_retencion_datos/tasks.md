# Tasks — privacidad_y_retencion_datos (feature #27)

## Contratos
- [x] T1 — Crear `contracts/lazaro_contracts/privacy.py` con `PrivacyPurgeRequest` y `PrivacyPurgeResponse` (`cutoff`, `deleted`, `closed_active_cases`; design §3) y exportarlos en `__init__.py`. Cubre: R52.
- [x] T2 — Documentar `POST /privacy/purge` de orchestrator y handover en `contracts/CONTRATOS.md` (orden handover → orchestrator, `closed_active_cases`) y añadir `503 privacy_not_configured` a la tabla de errores. Cubre: R51.
- [x] T3 — Tests en `contracts/tests/` (modelos con `closed_active_cases` por defecto 0, exportación y documentación de la ruta). Cubre: R51, R52.

## Orchestrator — configuración y consentimiento
- [x] T4 — `orchestrator/privacy.py`: `normalize_privacy_text`, `notice_sha256`, `is_acceptance`. Cubre: R3, R9, R12.
- [x] T5 — `config.py`: campos `PRIVACY_*`, `privacy_configured`, `retention_days`, añadir a `REQUIRED_IN_PRODUCTION`, validadores. Cubre: R1, R2, R3.
- [x] T6 — Repositorio (Protocol, InMemory, Postgres): esquema `privacy_consents`, `has_privacy_consent`, `add_privacy_consent`. Cubre: R9, R15.
- [x] T7 — `domain.py`: `_privacy_gate` y reordenar `process_message` (contacto creado después de la puerta en la ruta de cliente; rutas de personal sin cambios). Cubre: R4–R19.
- [x] T8 — Tests `test_config.py`: producción sin cada variable (parametrizado), días inválidos (`0`, `-1`, `abc`), aviso sin la frase. Cubre: R1, R2, R3.
- [x] T9 — Tests en `tests/test_privacy.py`: sin configuración → nada creado/guardado, sin llamadas a fakes ni gateway; respuesta 202; log sin datos. Cubre: R4, R5, R6.
- [x] T10 — Tests: sin consentimiento → se envía el aviso, nada se guarda ni se llama a RAG/LLM/handover. Cubre: R7, R8.
- [x] T11 — Tests: frase exacta (también con mayúsculas/espacios) → registro con versión, sha256 y `accepted_at` del reloj; confirmación enviada; texto no guardado ni procesado. Cubre: R9, R10, R11.
- [x] T12 — Tests: frase con texto extra → sin consentimiento guardado y aviso enviado; `/start <token>` y comandos no crean consentimiento. Cubre: R12, R13, R14.
- [x] T13 — Tests: cambio de versión → reaceptación y se conservan los registros anteriores. Cubre: R15.
- [x] T14 — Tests: con consentimiento vigente, el flujo RAG/traspaso/reenvío sigue igual; la suite existente pasa ajustando solo el fixture para que tenga configuración completa y consentimiento. Cubre: R16.
- [x] T15 — Tests: fallo de `add_privacy_consent` → sin confirmación enviada; respuesta 500. Cubre: R17, R18.
- [x] T16 — Tests: `/start <token>`, `/consultar`, `/responder`, `/cerrar` funcionan igual sin configuración y sin consentimiento. Cubre: R19.

## Orchestrator — retención
- [x] T17 — Repositorio: esquema `privacy_purge_runs` y `purge_personal_data(cutoff, ran_at)` (InMemory y Postgres en una transacción, orden del design). Cubre: R22–R28.
- [x] T18 — `domain.purge_personal_data` (`closed_active_cases = 0`) y `POST /privacy/purge` en `main.py`. Cubre: R20, R21, R27.
- [x] T19 — Tests en `tests/test_privacy_purge.py`: 401 sin token; 503 sin días y nada borrado. Cubre: R20, R21.
- [x] T20 — Tests: límites del corte en `messages` y `events` (antes del corte se borra, en el corte y después se conserva). Cubre: R22, R23.
- [x] T21 — Tests: contacto inactivo borrado con sus `case_links`; contacto con mensaje o `case_link` reciente conservado. Cubre: R24, R25.
- [x] T22 — Test: tablas operativas y `privacy_consents` intactas tras la purga. Cubre: R26.
- [x] T23 — Tests: respuesta (con `closed_active_cases = 0`) y fila en `privacy_purge_runs`; segunda ejecución con recuentos 0. Cubre: R27, R28.
- [x] T24 — Test de SQL de Postgres (con el helper de sentencias que ya usa `test_repository.py`): orden de borrado y tablas tocadas. Cubre: R24, R26.

## Handover
- [x] T25 — `config.py`: `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS` en `REQUIRED_IN_PRODUCTION`, validadores (entero ≥ 1; activo < retención), propiedades `retention_days`, `active_case_max_days`, `retention_configured`. Cubre: R29, R30, R31.
- [x] T26 — Repositorio (Protocol, InMemory, Postgres): `privacy_purge_runs` y `purge_personal_data(cutoff, active_cutoff, ran_at)` en una transacción con el orden del design §3 (casos activos expirados + sus `handover_requests`, luego `closed` y `handover_requests` por corte). Cubre: R34–R40.
- [x] T27 — `domain.purge_personal_data` (un solo `clock()` para ambos cortes) y `POST /privacy/purge`. Cubre: R32, R33, R40.
- [x] T28 — Tests `test_config.py`: producción sin cada una de las dos variables (parametrizado); valores inválidos (`0`, `-1`, `abc`) en cada una; activo = retención y activo > retención → `ValueError`; activo < retención válido. Cubre: R29, R30, R31.
- [x] T29 — Tests `tests/test_privacy_purge.py`: 401; 503 sin borrar si falta cualquiera de las dos variables; `closed` antiguo borrado y reciente conservado. Cubre: R32, R33, R34.
- [x] T30 — Tests: casos `open`/`assigned`/`timed_out` con `created_at` < corte de casos activos borrados (no recuperables con `get_case`) junto con sus `handover_requests` (por `case_id` y por `requested_case_id`); casos activos con `created_at` en el corte y después conservados sin cambios; `closed_active_cases` en la respuesta igual al número borrado; fallo simulado a mitad → nada borrado (Postgres: rollback por SQL helper). Cubre: R35, R36, R37, R40.
- [x] T31 — Tests: `handover_requests` por corte; `handover_notifications` y `handover_denials` intactas (también las de casos activos borrados); fila de ejecución guardada con `closed_active_cases`. Cubre: R38, R39, R40.

## Ejecución programada
- [x] T32 — `scripts/purgar_datos.py` (calco de `vencer_casos.py`, `_run_iteration` con orden handover → orchestrator y salto del orchestrator si handover falla). Cubre: R41–R46.
- [x] T33 — Tests `services/handover/tests/test_purgar_datos.py`: orden de llamadas (handover primero, luego orchestrator) con token y `{}`; exit 0 si ambas son 200; handover con status ≠ 200 o `httpx.HTTPError` → orchestrator no llamado y exit ≠ 0; orchestrator falla → exit ≠ 0; en bucle sigue tras un fallo y repite el orden (sleep parcheado). Cubre: R41–R46.
- [x] T34 — `COPY scripts/purgar_datos.py` en `services/handover/Dockerfile`; servicio `retention_worker` en `docker-compose.yml`; variables en `.env.example` (incluida `PRIVACY_ACTIVE_CASE_MAX_DAYS=` vacía). Cubre: R47, R48, R49, R50.
- [x] T35 — Tests `test_worker_compose.py`: bloque `retention_worker` con comando y Dockerfile, sin `ports`; Dockerfile copia el script; `.env.example` con las 6 variables aprobadas vacías. Cubre: R47, R48, R49, R50.

## Cierre
- [x] T36 — Ejecutar `./init.sh`; documentar la trazabilidad R1–R52 en `progress/impl_privacidad_y_retencion_datos.md`, incluidos los supuestos S1–S6 pendientes de aprobación del dueño. Cubre: R1–R52. (Trazabilidad hecha; `./init.sh` lo ejecuta Claude al cerrar la sesión: el implementer no ejecuta shell.)
