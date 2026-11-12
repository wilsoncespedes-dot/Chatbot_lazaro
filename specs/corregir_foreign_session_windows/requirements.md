# #45 corregir_foreign_session_windows — Requirements

Servicio: **orchestrator** (único). Alcance: solo
`PostgresRepository.foreign_session_windows`
(`services/orchestrator/orchestrator/adapters/repository.py`). La columna
`client_sessions.profile_id` es `TEXT NOT NULL`. El repositorio en memoria
(`FakeRepository.foreign_session_windows`), la firma del método, el dominio
(`domain.py`) y los contratos HTTP no cambian.

## R1
CUANDO `PostgresRepository.foreign_session_windows` se invoca con
`profile_id=None`, el sistema DEBE ejecutar una sola sentencia SQL que filtre
`client_sessions` solo por `contact_id = %s`, con parámetros exactamente
`(contact_id,)`, sin ninguna condición `IS NULL` sobre un parámetro y sin
filtro por `profile_id`.

## R2
CUANDO `PostgresRepository.foreign_session_windows` se invoca con un
`profile_id` no nulo, el sistema DEBE ejecutar una sola sentencia SQL que
filtre por `contact_id = %s AND profile_id <> %s`, con parámetros exactamente
`(contact_id, profile_id)` y sin ninguna condición `IS NULL` sobre un parámetro.

## R3
El sistema NO DEBE pasar `None` como parámetro de la sentencia de
`foreign_session_windows` en ninguna de las dos ramas (R1, R2), de modo que
PostgreSQL nunca necesite inferir el tipo de un parámetro NULL (error 42P18).

## R4
CUANDO la consulta devuelve filas `(profile_id, started_at, last_activity_at,
ended_at)`, el sistema DEBE devolver, en el mismo orden, la lista de
`session_window(started_at, last_activity_at, ended_at, now, idle_minutes)`
de cada fila, igual que antes del cambio, en ambas ramas.

## R5
`FakeRepository.foreign_session_windows` NO DEBE cambiar: con `profile_id=None`
devuelve las ventanas de todas las sesiones del contacto y con `profile_id`
no nulo solo las de otros perfiles (las pruebas existentes siguen verdes sin
modificarse).

## R6
CUANDO `GET /asesor/cases/<id>` se atiende con un caso sin vínculo
(`profile_id` None) o con vínculo con perfil, el sistema NO DEBE responder 500
por la consulta de `foreign_session_windows`; queda garantizado por R1–R3 y
por las pruebas existentes de `test_panel_case_view.py`, que deben seguir verdes.

## Cobertura del acceptance
- Sin 42P18 con `profile_id` None ni no nulo; consulta sin inferir tipo de NULL → R1, R2, R3.
- None → todas las ventanas; no nulo → solo otros perfiles; memoria sin cambios → R1, R2, R4, R5.
- `GET /asesor/cases/<id>` deja de dar 500 por esta causa → R6.
- Pruebas de SQL y parámetros para None y no nulo; `./init.sh` verde → R1–R4 (tasks T2, T3).
