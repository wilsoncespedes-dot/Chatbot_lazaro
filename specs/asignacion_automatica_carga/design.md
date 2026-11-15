# #52 asignacion_automatica_carga — Design

Reparto de responsabilidades: la **presencia** vive en el orchestrator, la **carga y
los casos** en handover. Por eso el orchestrator calcula los candidatos disponibles
y handover elige y asigna atómicamente. Sin servicios ni dependencias nuevas; no se
copia código de terceros.

## Archivos

| Archivo | Cambio |
|---|---|
| `contracts/lazaro_contracts/cases.py` (+ export en `__init__`, test de contrato) | `CaseAutoAssignRequest`, `CaseAutoAssignResponse` (R24). |
| `services/handover/handover/domain.py` | `auto_assign_case` (R7–R9, R11, R13–R15, R19). |
| `.../handover/adapters/repository.py` | Protocol + Fake + Postgres: `auto_assign_least_loaded`; tabla `handover_auto_assignments` (R13, R19). |
| `.../handover/main.py` | `POST /cases/{case_id}/auto-assign` (R24, R25). |
| `services/orchestrator/orchestrator/adapters/handover.py` | `auto_assign(case_id, candidate_ids)` en Protocol, Http y Fake. |
| `.../orchestrator/administration.py` | `SettingSpec` tipo `enum` para `assignment.mode`; prefijo `assignment.` en `OPERATIONAL_PREFIXES`; `OperationalSettings.assignment_mode` (R1–R4). |
| `.../orchestrator/admin_routes.py`, `admin.py` | Mostrar/guardar el ajuste y auditarlo (R1, R3, R4). |
| `.../orchestrator/domain.py` | `_handover(..., allow_auto_assign=True)`; `_try_auto_assign`; `available_advisor_ids` (R5, R6, R10, R12, R16–R18, R20). La herramienta de supresión pasa `allow_auto_assign=False`. |
| `.../orchestrator/config.py`, `.env.example`, `render.yaml` | `ASSIGNMENT_MODE=manual` (R2). |
| Tests | `services/handover/tests/test_auto_assign.py` (R7–R9, R11, R13–R15, R19, R24, R25); `services/orchestrator/tests/test_auto_assign.py` (R1–R6, R10, R12, R16–R18, R20–R23); `contracts/tests/` (R24). |

## Firmas

```python
# contracts
class CaseAutoAssignRequest(ContractModel): candidate_ids: list[Identifier]  # 1..200
class CaseAutoAssignResponse(ContractModel):
    status: Literal["assigned", "queued", "skipped"]
    case_id: Identifier
    advisor_id: Identifier | None

# handover/domain.py
def auto_assign_case(case_id: str, req: CaseAutoAssignRequest, settings, adapters) -> CaseAutoAssignResponse

# handover repository
def auto_assign_least_loaded(self, case_id: str, candidate_ids: list[str], at: datetime) -> str | None
# None si el caso ya no está open sin asesor o no hay candidatos válidos; si no, advisor_id elegido

# orchestrator/domain.py
def available_advisor_ids(settings, adapters) -> list[str]
def _try_auto_assign(contact, case_id, settings, adapters) -> None
```

## Atomicidad (R13, R14, R19)

`auto_assign_least_loaded` en Postgres corre en **una transacción** con
`pg_advisory_xact_lock(<constante>)` para serializar asignaciones automáticas
(el recuento de carga es consistente), luego:

1. Filtra `candidate_ids` contra el roster atendedor (R9).
2. Calcula la carga: `SELECT advisor_id, count(*) FROM handover_cases WHERE status='assigned'`.
3. Elige `min(carga, advisor_id)` (R7, R8).
4. `UPDATE ... SET status='assigned', advisor_id=%s, assigned_at=%s WHERE case_id=%s AND status='open' AND advisor_id IS NULL`; si 0 filas → rollback implícito, retorna `None` (R14, nunca pisa una acción humana: las acciones humanas usan escrituras condicionales sobre el mismo estado).
5. `INSERT INTO handover_auto_assignments(case_id, advisor_id, reason, at)` con `reason='auto'` en la misma transacción (R19).

`auto_assign_case` distingue `skipped` (caso cambiado) de `queued` (sin candidatos válidos) releyendo el caso cuando el repo devuelve `None` (R11, R14, R15). El Fake imita la misma lógica bajo un `threading.Lock` para el test de concurrencia.

## Flujo del orchestrator (R5, R6, R10, R12, R16–R18)

En `_handover`, tras `status == "queued"` y `apply_conversation_event(ESCALATED)`:
si `allow_auto_assign` y modo `automatica` y (horario deshabilitado o dentro de él) y el
caso es nuevo/sin asesor, llama `_try_auto_assign`. El caso reutilizado (R18) lo cubre
handover: `open_case` no cambia el estado de un caso asignado y `skipped` es el
resultado de `assign` condicional. `available_advisor_ids` lee el roster de perfiles
atendedores y `effective_presence` (reutiliza `get_advisor_presence`). Lista vacía →
no se llama (R10). `ServiceUnavailable`/error → evento `auto_assign_failed` y el caso
sigue en cola (R12). La calidad "dentro de horario" reutiliza `within_business_hours`
ya usado para el aviso (R17).

## Config

| Variable | Default | Valores |
|---|---|---|
| `ASSIGNMENT_MODE` | `manual` | `manual`, `automatica` |

El valor guardado en `app_settings` (`assignment.mode`) tiene prioridad sobre el entorno y se lee en cada escalamiento (R3).

## Supuestos a confirmar (defaults seguros, no bloquean)

- **S1 Casos en cola (acceptance)**: un caso que quedó en cola por falta de asesores disponibles **no** se asigna solo cuando un asesor vuelve a estar disponible; lo toma un asesor o lo asigna el supervisor (R23). Es el comportamiento más conservador: evita asignaciones sorpresa y no exige un bucle de fondo; no se implementa ningún barrido.
- **S2 Carga**: cuentan solo casos `assigned`; los `open` en cola no suman.
- **S3 Desempate**: menor `advisor_id` lexicográfico (estable, determinista).
- **S4 Aviso al asesor**: la bandeja lo muestra; no se envía notificación push nueva.
- **S5 Supervisor como candidato**: entra si es atendedor y está `available` (es un rol atendedor en #48/#49).

## Alternativas descartadas

- **Elegir en el orchestrator y asignar con `assign`**: la carga vive en handover; dos escalamientos simultáneos leerían la misma carga y repartirían mal. Se descarta por atomicidad (R13).
- **Barrido periódico que asigna la cola al volver un asesor**: lo excluye el supuesto del acceptance y añade un proceso de fondo y condiciones de carrera.
- **Round-robin con contador**: no cumple «menos casos asignados sin cerrar».

## Dependencias

Ninguna nueva.
