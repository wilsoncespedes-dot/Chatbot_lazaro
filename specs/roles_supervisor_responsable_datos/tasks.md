# Tasks — roles_supervisor_responsable_datos (#49)

- [x] 1. Contratos: `CaseReassignRequest/Response`, rol ampliado en `AdvisorRosterEntry`, `scope` en `GET /cases`, ejemplos y tests de modelos/ejemplos. Cubre R28.
- [x] 2. `contracts/CONTRATOS.md`: sección `POST /cases/{id}/reassign`, `scope`, S12/S14 reescritos y tabla de errores; ajustar `test_contratos_doc.py`. Cubre R28, R29.
- [x] 3. Handover: repositorio (roster con rol, `reassign_if_assigned_to`, `list_all_cases`) en Protocol, Fake y Postgres. Cubre R7, R12, R13.
- [x] 4. Handover: `reassign_case`, `scope=all`, excepciones nuevas y ruta en `main.py`; tests `test_reassign.py`, concurrencia contra cierre/transferencia y 401/403/404/409/422 en `test_security.py`. Cubre R9, R10, R12–R16, R29.
- [x] 5. Orchestrator: `ROLES`/`Role`, `STAFF_ROLES`, selector de rol y validación, invalidación de sesiones al cambiar rol (incluye crear `delete_sessions_for_profile` en el repositorio); tests de cuentas. Cubre R1–R4.
- [x] 6. Orchestrator: `get_session_for_roles` (rol leído del perfil en servidor), roster asesor+supervisor, adaptador de handover (`reassign`, `scope`). Cubre R5–R7, R24.
- [x] 7. Orchestrator: `SUPPRESSION_EXECUTOR_ROLES` admite `responsable_datos`, default `admin`; `.env.example`, `render.yaml`; tests de config. Cubre R23.
- [x] 8. Orchestrator: dominio y rutas del supervisor (`/asesor/todos`, reasignar con presencia `available`, `/asesor/metricas` solo lectura, auditoría, CSRF, 403 uniforme sin revelar el caso) y render. Cubre R6, R8, R11, R14, R17–R19, R27.
- [x] 9. Orchestrator: rutas del responsable de datos y guardas por rol en todas las rutas `/asesor/**` y `/admin/**`. Cubre R20–R22, R25.
- [x] 10. Tests: matriz de permisos de los cinco roles, seguridad forzando URL/formulario por asesor, reasignación concurrente, auditoría, CSRF, 403 uniforme sin revelar el caso. Cubre R18, R25–R27, R30.
- [x] 11. `docs/architecture.md` (una línea); `./init.sh` verde y revisión. Cubre R30.
