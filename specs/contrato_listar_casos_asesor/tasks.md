# Tasks — contrato_listar_casos_asesor (feature #33)

## Contrato

- [x] T1 — Añadir `DEFAULT_CASE_LIST_LIMIT`/`MAX_CASE_LIST_LIMIT` en `common.py` y `CaseListAction`, `CaseListStatus`, `CaseListQuery`, `CaseListItem` (validador sin repetidos), `CaseListResponse` en `cases.py`; exportar en `__init__.py`. Cubre: R2, R3, R4, R5.
- [x] T2 — Crear `case_list_query.json`, `case_list_response.json` (open, assigned propio, huérfano; orden R15) y `case_list_response_empty.json`; registrarlos en `EXAMPLES` de `test_examples.py` (cada uno valida contra su modelo). Cubre: R6, R21.
- [x] T3 — Añadir `### GET /cases` (bullets Expone/Llama/Modelos, tabla de query con `TABLE_HEADER`, respuesta `200`, tabla de errores 401/422/500, `X-Service-Token`) y la fila `S14` en `CONTRATOS.md`, sin editar líneas existentes. Cubre: R1, R7.
- [x] T4 — `contracts/tests/test_listar_casos_asesor.py`: sección y bullets; tabla de query lista `advisor_id`; tabla de respuesta lista exactamente los 4 campos; errores 401/422/500; mención de `X-Service-Token`; `S14` existe y menciona `CASE_LIST_LIMIT`, 50, 200, orden y lista vacía; filas S1–S13 sin cambios (comparar con `git show HEAD:contracts/CONTRATOS.md`). Cubre: R1, R7.
- [x] T5 — En el mismo archivo: `CaseListQuery` exige `advisor_id`, rechaza vacío/65 caracteres/extra; `CaseListItem` rechaza fecha sin zona, status `closed`, `actions` vacía/repetida/desconocida y cada campo prohibido de R5; `CaseListResponse` acepta 200 y rechaza 201; `DEFAULT_CASE_LIST_LIMIT == 50`. Cubre: R2, R3, R4, R5.

## Handover

- [x] T6 — `config.py`: `case_list_limit` (default 50, 1–200) + `.env.example`. Tests: sin la variable → 50 (R22); `0`, `201` y `abc` fallan al construir `Settings` (R17). Cubre: R17, R22.
- [x] T7 — `repository.py`: `list_cases_for_advisor` en Protocol, Fake y Postgres (SQL del design). Test Postgres con `connect` falso: SQL parametrizado con `ORDER BY created_at ASC, case_id ASC` y `LIMIT`. Cubre: R13, R14, R15, R16.
- [x] T8 — `domain.py`: `list_advisor_cases` calculando `actions` con `can_act_on_case` existente en `reply`/`assign`/`close` (quitando `assign` si `status == "assigned"`) y descartando casos con `actions` vacía, según el design; sin reescribir reglas de S12. Cubre: R10, R11, R12, R13, R14, R18.
- [x] T9 — `main.py`: `GET /cases` con `Annotated[CaseListQuery, Query()]`. Cubre: R8, R9, R20.
- [x] T10 — `services/handover/tests/test_list_cases.py` (app con `FakeCaseRepository`):
  - sin token / token erróneo → 401 (R8);
  - sin `advisor_id`, vacío, 65 caracteres, parámetro extra → 422 `validation_error` (R9);
  - asesor no registrado con casos open y casos asignados a él → `200 []` (R10);
  - open y timed_out → `["reply","assign","close"]` (R11);
  - assigned al solicitante → `["reply","close"]` (R12);
  - assigned con `advisor_id` nulo y con asesor retirado → `["close"]` (R13);
  - closed y assigned a otro asesor registrado no aparecen (R14);
  - igualdad con S12: para cada caso listado (open, timed_out, assigned propio, huérfano), `actions` == `[a for a in ("reply","assign","close") if can_act_on_case(case, advisor_id, a, settings)]` salvo `assign` en casos `assigned`; y un repositorio falso que devuelve un caso `closed` y uno asignado a otro asesor registrado → descartados (R11, R12, R13, R14);
  - orden por `created_at` y desempate por `case_id` con fechas iguales (R15);
  - `CASE_LIST_LIMIT=2` con 3 casos visibles y casos ajenos más antiguos → los 2 visibles más antiguos (R16);
  - sin `CASE_LIST_LIMIT` en el entorno, con 51 casos visibles → 50 elementos (R22);
  - claves de cada elemento == `{case_id,status,created_at,actions}` y el cuerpo no contiene `contact_id`/`chat_id`/texto de mensajes sembrados (R18);
  - repositorio sin cambios y sin denegaciones/notificaciones tras listar (registrado y no registrado) (R19);
  - repositorio que lanza excepción → 500 `internal_error` sin traceback (R20);
  - la respuesta valida contra `CaseListResponse` (R3, R4).
  Cubre: R8–R20, R22.
- [x] T11 — Ejecutar `./init.sh` (contracts + handover verdes, sin tests existentes eliminados ni debilitados) y documentar la trazabilidad R→test en `progress/impl_contrato_listar_casos_asesor.md`. Cubre: R1–R22.
