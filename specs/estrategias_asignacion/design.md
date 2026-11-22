# Design — #69 estrategias_asignacion

## Archivos a tocar

- `contracts/lazaro_contracts/cases.py`: `CaseAutoAssignRequest.strategy: str = "por_carga"` (patrón `^[a-z_]{1,32}$`); constante `ASSIGNMENT_STRATEGIES = ("por_carga", "round_robin")` exportada en `__init__.py`.
- `contracts/CONTRATOS.md` y `contracts/examples/case_auto_assign_request.json`: documentar `strategy`; actualizar `contracts/tests/test_auto_assign.py` (R20).
- `services/handover/handover/strategies.py` (nuevo): interfaz, registro y las dos estrategias.
- `services/handover/handover/domain.py`: `auto_assign_case` resuelve la estrategia por nombre y llama `repo.auto_assign(...)`.
- `services/handover/handover/adapters/repository.py`: reemplaza `auto_assign_least_loaded` por `auto_assign` (Protocol, Fake y Postgres); tabla `handover_assignment_pointer`.
- `services/orchestrator/orchestrator/config.py`: `ASSIGNMENT_STRATEGY` (default `por_carga`) validada contra `ASSIGNMENT_STRATEGIES`.
- `services/orchestrator/orchestrator/administration.py`: nuevo `SettingSpec("assignment.strategy", "enum", ..., "assignment_strategy", ASSIGNMENT_STRATEGIES)`; campo `OperationalSettings.assignment_strategy`.
- `services/orchestrator/orchestrator/admin_routes.py`: rama de valor actual para `assignment.strategy` (el prefijo `assignment.` ya está permitido; la tabla de ajustes es genérica).
- `services/orchestrator/orchestrator/domain.py` (`_try_auto_assign`) y `adapters/handover.py` (Protocol, HTTP y Fake): pasan `strategy`.
- `.env.example` y `render.yaml`: `ASSIGNMENT_STRATEGY=por_carga`.
- Tests: `services/handover/tests/test_strategies.py` (nuevo), ajustes en tests de auto-assign existentes, `services/orchestrator/tests/test_auto_assign.py`, `contracts/tests/test_auto_assign.py`.

## Firmas nuevas

```python
# handover/strategies.py
@dataclass(frozen=True)
class ContextoAsignacion:
    cargas: Mapping[str, int]      # casos `assigned` por asesor
    ultimo: str | None             # puntero de ESTA estrategia

class EstrategiaAsignacion(Protocol):
    nombre: ClassVar[str]
    def elegir(self, candidatos: Sequence[str], contexto: ContextoAsignacion) -> str: ...

ESTRATEGIAS: dict[str, EstrategiaAsignacion] = {}
def registrar_estrategia(cls): ...   # decorador: instancia y registra por cls.nombre
def obtener_estrategia(nombre: str) -> EstrategiaAsignacion: ...  # lanza UnknownStrategy

# repository
def auto_assign(self, case_id: str, candidate_ids: list[str],
                strategy: EstrategiaAsignacion, at: datetime) -> str | None: ...
```

`candidatos` llega ya filtrado (atendedores del roster, sin repetir, disponibles según el orquestador) y no vacío; `elegir` es pura, sin IO. `round_robin`: `sorted(candidatos)`, primer `> ultimo`, si no, el primero.

## Flujo de `auto_assign` (Postgres)

Mismo candado `pg_advisory_xact_lock(AUTO_ASSIGN_ADVISORY_LOCK)` de #52, una transacción: filtrar válidos, leer cargas, leer puntero de `strategy.nombre` (`SELECT ... FOR UPDATE` no hace falta bajo el candado), `elegir`, `UPDATE handover_cases ... WHERE status='open' AND advisor_id IS NULL`; si 0 filas, rollback (puntero intacto, R8); si 1, `INSERT` en `handover_auto_assignments` y `INSERT ... ON CONFLICT (strategy) DO UPDATE` del puntero; commit. El Fake usa el mismo `threading.Lock` y un dict `pointers`. La escritura es genérica: todas las estrategias persisten su puntero (por_carga lo ignora), así no hay ramas por nombre.

## Excepciones

`UnknownStrategy(ValueError)` en `strategies.py`, capturada en `main.py` y mapeada a `422 validation_error` (R5). Se reutilizan `CaseNotFound` y `CaseClosed`.

## Ajuste y hot-swap

`assignment.mode` no cambia. `assignment.strategy` se resuelve con `resolve_operational_settings` en cada escalamiento (ya lee `app_settings` en cada llamada), por lo que el cambio es inmediato (R18). La lista de nombres válidos vive en contracts para que orchestrator no importe handover; un test de handover verifica `set(ESTRATEGIAS) == set(ASSIGNMENT_STRATEGIES)`. Añadir una estrategia = clase decorada + nombre en la constante (el test lo exige).

## Alternativa descartada

Mover la elección al orquestador y enviarle a handover el asesor ya decidido: rompe la atomicidad (carga/puntero leídos fuera de la transacción) y duplica la lógica de #52. También se descartó un puntero en memoria o en `app_settings` del orquestador: no sobrevive a reinicios ni es atómico con la escritura del caso.

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar

- Default `por_carga` configurable con `ASSIGNMENT_STRATEGY` (sin decisión de producto abierta).
- El orden del turno es lexicográfico por `advisor_id` (determinista); el puntero guarda el último id, no un índice, para tolerar cambios de roster.
- Un puntero hacia un asesor que ya no está en el roster sigue funcionando (se compara por orden, no por pertenencia).
- Se reemplaza `auto_assign_least_loaded` sin alias; los tests existentes se migran a `auto_assign` con `por_carga`.
