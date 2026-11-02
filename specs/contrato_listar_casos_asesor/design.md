# Design — contrato_listar_casos_asesor (feature #33)

## Decisión

Ruta de solo lectura en handover, dueño de los casos y de `ADVISOR_CHAT_IDS`. El
filtrado se hace en SQL (un solo `SELECT` con `LIMIT`) y las `actions` se calculan en
`domain.py` llamando a la función existente `can_act_on_case`
(`services/handover/handover/domain.py:162`), que implementa S12, sin reescribir sus
reglas; así, si S12 cambia, `actions` cambia con ella. Sin dependencias nuevas, sin tablas ni
migraciones (se leen columnas existentes de `handover_cases`).

## Archivos

| Archivo | Cambio |
|---------|--------|
| `contracts/lazaro_contracts/common.py` | `DEFAULT_CASE_LIST_LIMIT = 50`, `MAX_CASE_LIST_LIMIT = 200`. |
| `contracts/lazaro_contracts/cases.py` | `CaseListAction`, `CaseListStatus`, `CaseListQuery`, `CaseListItem`, `CaseListResponse` (abajo). |
| `contracts/lazaro_contracts/__init__.py` | Exporta los nuevos nombres y constantes (y en `__all__`). |
| `contracts/examples/` | `case_list_query.json`, `case_list_response.json`, `case_list_response_empty.json`. |
| `contracts/CONTRATOS.md` | Nueva sección `### GET /cases` al final de `## Rutas` (tras `POST /privacy/purge`) y nueva fila `S14`. Solo líneas añadidas. |
| `contracts/tests/test_examples.py` | Registrar los 3 ejemplos en `EXAMPLES` (inserción, sin tocar entradas existentes). |
| `contracts/tests/test_listar_casos_asesor.py` (nuevo) | Tests R1–R7, R21. |
| `services/handover/handover/config.py` | `case_list_limit: int = Field(default=DEFAULT_CASE_LIST_LIMIT, ge=1, le=MAX_CASE_LIST_LIMIT)`. |
| `services/handover/handover/adapters/repository.py` | `list_cases_for_advisor` en Protocol, Fake y Postgres. |
| `services/handover/handover/domain.py` | `list_advisor_cases(advisor_id, settings, adapters) -> CaseListResponse`. |
| `services/handover/handover/main.py` | `@app.get("/cases", response_model=CaseListResponse)`. |
| `services/handover/tests/test_list_cases.py` (nuevo) | Tests R8–R20, R22 (app + dominio + repo Postgres con `connect` falso, como en `test_repository.py`). |
| `.env.example` | `CASE_LIST_LIMIT=50` con comentario (opcional, 1–200). |

`docker-compose.yml` no se toca: el default funciona sin la variable.

## Modelos de contrato

```python
CaseListAction = Literal["reply", "assign", "close"]
CaseListStatus = Literal["open", "timed_out", "assigned"]

class CaseListQuery(ContractModel):          # extra="forbid" heredado
    advisor_id: Identifier                     # S6

class CaseListItem(ContractModel):
    case_id: Identifier
    status: CaseListStatus
    created_at: AwareDatetime
    actions: Annotated[list[CaseListAction], Field(min_length=1)]
    # validator: sin repetidos

class CaseListResponse(RootModel[list[CaseListItem]]):
    root: Annotated[list[CaseListItem], Field(max_length=MAX_CASE_LIST_LIMIT)]
```

Arreglo de nivel superior como `GET /manuals` y `POST /search` (S10): coherente con
las rutas de lectura existentes.

## Handover

```python
# adapters/repository.py
def list_cases_for_advisor(
    self, advisor_id: str, registered_ids: list[str], limit: int
) -> list[Case]: ...
```

SQL Postgres (parametrizado, `_run` con el `threading.Lock` existente):

```sql
SELECT {_CASE_COLUMNS} FROM handover_cases
WHERE status IN ('open', 'timed_out')
   OR (status = 'assigned' AND advisor_id = %s)
   OR (status = 'assigned' AND (advisor_id IS NULL OR NOT (advisor_id = ANY(%s))))
ORDER BY created_at ASC, case_id ASC
LIMIT %s
```

`Fake` aplica el mismo filtro/orden/límite en memoria. La condición de huérfano en
SQL existe solo por eficiencia (R16: el límite se aplica en la consulta); la
autoridad sobre qué se lista y con qué `actions` es el filtro de dominio de abajo.

```python
# domain.py
def list_advisor_cases(advisor_id: str, settings: Settings, adapters: Adapters) -> CaseListResponse:
    if not is_registered_advisor(advisor_id, settings):
        return CaseListResponse([])            # R10: no consulta el repo, no registra denegación
    registered = [str(i) for i in settings.advisor_ids]
    cases = adapters.repository.list_cases_for_advisor(advisor_id, registered, settings.case_list_limit)
    items = []
    for case in cases:
        actions = [
            a for a in ("reply", "assign", "close")
            if can_act_on_case(case, advisor_id, a, settings)
            and not (a == "assign" and case.status == "assigned")   # no-op de S11
        ]
        if not actions:
            continue                            # descarte defensivo (único filtro en dominio)
        items.append(CaseListItem(case_id=case.case_id, status=case.status,
                                  created_at=case.created_at, actions=actions))
    return CaseListResponse(items)
```

`actions` no tiene tabla propia: es `can_act_on_case` evaluada en las tres acciones,
con la única excepción de quitar `assign` cuando `case.status == "assigned"` (ver
alternativas descartadas). El resultado esperado hoy es el de R11–R13. Un caso que
el SQL devuelva y para el que `can_act_on_case` no permita ninguna acción (p. ej.
`closed` o asignado a otro asesor registrado) se descarta; no hay otra regla de
descarte. El orden de `actions` es siempre `reply`, `assign`, `close`.

```python
# main.py
@app.get("/cases", response_model=CaseListResponse)
def get_cases(query: Annotated[CaseListQuery, Query()]) -> CaseListResponse: ...
```

FastAPI ≥ 0.115 (ya en `requirements.txt`) admite modelos de query; con
`extra="forbid"` un parámetro no declarado produce `RequestValidationError`, que el
handler existente convierte en `422 validation_error` (R9). El middleware de token
ya cubre la ruta (R8); el handler genérico ya da `500 internal_error` (R20).

Precedencia: `401` → `422` → `200`. La ruta no responde `403` ni `404`: un asesor no
registrado recibe `[]` (decisión del borrador de #29), sin escribir denegación — las
denegaciones de #14 son de mutaciones y se mantienen en `authorize`/`assign`/`close`.

Logs: un `INFO` con el número de casos devueltos; sin `advisor_id`, ids de caso ni
datos del cliente.

## Reglas que no cambian

S11, S12 (#13/#14/#17) y S13 quedan intactas. `actions` es informativa: el panel
siempre llama a `authorize`/`assign`/`close`, que siguen siendo la autoridad. Entre
listar y actuar el caso puede cambiar; la mutación responde `403`/`409` como hoy.

## Alternativas descartadas

- **Respuesta objeto con cursor/`truncated`**: añade paginación que el panel aún no
  necesita; con el orden por antigüedad el asesor ve primero los casos más urgentes.
  Se puede añadir después como cambio aditivo.
- **Filtrar en Python tras `SELECT *`**: lee casos ajenos y aplica mal el límite;
  el filtro en SQL respeta R16 con una sola consulta.
- **`403` para asesor no registrado**: el borrador de #29 fijó `200 []`; evita que el
  panel distinga "sin casos" de "no autorizado" y no genera denegaciones por lectura.
- **Incluir `assign` en casos ya asignados al propio asesor**: S11 lo hace un no-op;
  ofrecerlo en el panel sería un botón inútil.

## Dependencias

Ninguna nueva. Código reutilizado: solo del propio repositorio.

## Supuestos (defaults configurables)

- `CASE_LIST_LIMIT` = 50, rango 1–200 (`MAX_CASE_LIST_LIMIT`), env de handover.
- Sin cursor en v1; más allá del límite los casos no se listan hasta que se
  atiendan los más antiguos.
- `actions` derivadas de `can_act_on_case` (resultado esperado en R11–R13); si el humano quiere `reason` o mensajes en el
  listado, es un cambio de contrato posterior.
