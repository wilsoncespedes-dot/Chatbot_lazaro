# Design — roles_supervisor_responsable_datos (#49)

Sin servicios ni dependencias nuevas. El panel sigue renderizado en servidor en el orchestrator; la reasignación la decide handover.

## Archivos

| Archivo | Cambio |
|---|---|
| `contracts/lazaro_contracts/cases.py`, `__init__.py` | `CaseReassignRequest/Response`; `AdvisorRosterEntry.role` admite `supervisor` y `responsable_datos`; `CaseListScope` (R28). |
| `contracts/examples/case_reassign_request.json`, `case_reassign_response.json` | Nuevos; mapear en `contracts/tests/test_examples.py`. |
| `contracts/CONTRATOS.md` | `### POST /cases/{id}/reassign`; `scope` en `GET /cases`; S12 y S14 reescritos (R28, R29); filas 403/409/422. |
| `contracts/tests/test_models.py`, `test_contratos_doc.py` | Casos nuevos. |
| `services/handover/handover/domain.py` | `reassign_case`, `list_cases(scope)`, `is_supervisor`; `DenialAction` añade `"reassign"`, `"list_all"`; excepciones `CaseChanged` (409 `case_changed`), `CaseNotAssigned` (409 `case_not_assigned`). |
| `services/handover/handover/adapters/repository.py` | `reassign_if_assigned_to(case_id, from_id, to_id, now)` (UPDATE condicional) en Protocol, Fake y Postgres; roster guarda rol; `list_all_cases`. |
| `services/handover/handover/main.py` | `POST /cases/{case_id}/reassign`; `scope` en `GET /cases`. |
| `services/orchestrator/orchestrator/accounts.py`, `main.py` | `ROLES` y `Role` con cinco valores. |
| `services/orchestrator/orchestrator/domain.py` | `STAFF_ROLES` incluye los nuevos; `change_role` invalida sesiones (R4); roster incluye asesor+supervisor (R7); `reassign_case` (valida supervisor, presencia, auditoría); `all_cases_view`. |
| `services/orchestrator/orchestrator/config.py` | Validador de `SUPPRESSION_EXECUTOR_ROLES` admite `responsable_datos`; default `admin` (R23). |
| `services/orchestrator/orchestrator/advisor_routes.py` | `_require_session(request, adapters, allowed)` con conjunto de roles; login acepta los tres roles; `/asesor/todos`, `/asesor/casos/{id}/reasignar`, `/asesor/metricas`; guardas por ruta (R25); redirección del responsable (R22). |
| `services/orchestrator/orchestrator/advisor_panel.py`, `admin.py` | Selector de rol con cinco opciones; navegación por rol; formulario de reasignar; métricas solo lectura (reusa `render_metrics` sin formularios). |
| `services/orchestrator/orchestrator/adapters/handover.py` | `reassign` y `scope` en Protocol, Http y Fake. |
| `services/orchestrator/orchestrator/adapters/repository.py` | `get_session_for_roles(token_hash, now, roles)`; `delete_sessions_for_profile`. |
| `.env.example`, `render.yaml`, `docs/architecture.md` | Comentario del valor admitido de `SUPPRESSION_EXECUTOR_ROLES`; una línea de roles. |
| Tests | `contracts/tests/*`; `services/handover/tests/test_reassign.py`, `test_security.py`, `test_list_cases.py`; `services/orchestrator/tests/test_roles_matrix.py`, `test_panel_reassign.py`, `test_accounts.py`, `test_config.py`, `test_panel_suppression.py`, `test_repository_schema.py`. |

## Firmas

```python
class CaseReassignRequest(ContractModel):
    advisor_id: Identifier          # supervisor que reasigna
    target_advisor_id: Identifier
class CaseReassignResponse(ContractModel):
    status: Literal["assigned"]
    case_id: Identifier
    previous_advisor_id: Identifier | None
    advisor_id: Identifier

# handover/domain.py
def reassign_case(case_id, req, settings, adapters) -> CaseReassignResponse
# orchestrator/accounts.py
ROLES = ("admin", "supervisor", "asesor", "responsable_datos", "cliente")
```

Precedencia en handover: `403` (no supervisor) → `404` → `409 case_closed` → `409 case_not_assigned` → `422` (destino inválido/igual al actual) → escritura condicional → `409 case_changed` si perdió la carrera. La presencia `available` (R14) la valida el orquestador antes de llamar, igual que la transferencia #41; handover solo conoce el roster.

## Decisiones

- Un único login `/asesor/login` para `asesor`, `supervisor` y `responsable_datos`; la sesión guarda el perfil y el rol se relee del perfil en cada petición (R5). `/admin/login` sigue solo para `admin`.
- El supervisor está en el roster de handover como asesor atendedor (puede hacer todo lo de un asesor, R6/R7); la distinción se hace por rol del roster. `responsable_datos` no entra (R24).
- La cola de supresión del responsable usa las funciones existentes `suppression_queue` y `execute_suppression_from_panel`, que ya consultan `SUPPRESSION_EXECUTOR_ROLES`.
- Métricas: `admin_metrics` se reutiliza; la ruta del supervisor es de solo lectura y no importa nada de `/admin/**`.
- Cambio de rol invalida sesiones del perfil para que no sobreviva privilegio (R4).

## Alternativa descartada

Hacer la reasignación en el orquestador (escribir directamente `advisor_id` o cerrar+asignar). Descartada: reintroduce la carrera de lectura-escritura entre orquestador y handover y rompe la propiedad de que handover es dueño de los casos; la escritura condicional en handover garantiza que no deshace un cierre o respuesta simultáneos (R13).

## Supuestos a confirmar

Presencia `available` para el destino (acceptance); `403` para roles ajenos en lugar de `404`; default de `SUPPRESSION_EXECUTOR_ROLES` sin cambios.
