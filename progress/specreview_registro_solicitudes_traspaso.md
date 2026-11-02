# Spec review — registro_solicitudes_traspaso (feature #11)

**Veredicto:** SPEC_APPROVED

Tercera vuelta (2026-11-01, modo nocturno). El spec se ha puesto al día con el código actual de
`services/handover` (después de #10, #13, #14 y #17). No se toca `feature_list.json` ni `specs/`.

## Cambios pedidos en vueltas anteriores (siguen aplicados)
- [x] R2 partido: R2 se queda solo con el `NO DEBE` (requirements l.30-31); `messages_count` pasa a R19 (l.33-35) y R1 remite a R19.
- [x] Nivel de los logs: R20 y R21 en `ERROR`; tabla del design l.223-227; T21 (c) comprueba `levelno == logging.ERROR`.
- [x] S5 reescrito al estado posterior a la #10 (design l.313).

## Cobertura del acceptance (A1-A9)
- [x] A1 → R1, R3, R19 · A2 → R4, R5 · A3 → R6, R7 · A4 → R8 (+R9, R12) · A5 → R14, R15 y alcance «solo handover» · A6 → R16, R17, R18 · A7 → R2, R19 · A8 → «Alcance» · A9 → T6/T8, T11/T12, T9, T10, T13-T15, T23.

## Referencias al código (comprobadas en el árbol de trabajo)
- [x] `config.py`: `parse_advisor_chat_ids` en l.17, `_validate_advisor_chat_ids` en l.53 y `advisor_ids` en l.58. Coinciden con los rangos citados.
- [x] `domain.py`: `logger` en l.28; `dataclass`/`Literal` ya importados (l.5, l.7); `Case`/`Notification`/`Denial` en l.62-88; `open_case` en l.163-205, con el flujo descrito: `advisor_notice_failed` en `ERROR`, paso a `timed_out` y `logger.warning("no_advisors …")`.
- [x] `repository.py`: el import de l.12 es `Case, Denial, Notification`; `_SCHEMA` (l.120) tiene 3 tablas, la última `handover_denials`; `_lock` en l.183; `_connection` en l.185-193; `_run` en l.195-206 con el lock alrededor de `_connection` + `execute` + `fetchall` + `commit`/`rollback`.
- [x] `main.py`: `configure_logging` en l.51-58, llamada en l.156; `advisors_configured` en l.80; `post_handover` síncrona en l.134-135; handler genérico en l.124-127.
- [x] `test_repository.py`: los dos tests que cuentan `== 3` `CREATE TABLE` están en l.97 y l.315; `test_postgres_repository_uses_parameters_only` cuenta 6 sentencias no-`CREATE` y no se ve afectado; `_statements` en l.169; `_FakeConn(rows=...)` en l.34.
- [x] `conftest.py`: `START`, `ADVISORS = [111, 222, 333]`, `FakeClock.advance`, `env_no_advisors`. Coinciden.

## Diseño
- [x] Se respetan las capas: modelo y flujo en `domain.py`, SQL en `adapters/repository.py`, sin IO directo en el dominio.
- [x] SQL parametrizado con `%s`; `CREATE TABLE IF NOT EXISTS` como cuarta sentencia de `_SCHEMA`.
- [x] Concurrencia bien resuelta: los métodos nuevos llaman a `_run` una sola vez, no anidan llamadas (el `Lock` no es reentrante) y no añaden locks nuevos.
- [x] Sin contratos nuevos, sin dependencias nuevas y sin variables de entorno nuevas. Cinco alternativas descartadas.
- [x] Coordinación con #12 y #14: solo se añaden métodos y una sentencia. Los conflictos posibles son solo textuales (`_SCHEMA` y el conteo de `CREATE TABLE`) y están declarados.

## Decisiones del humano
- [x] Se cumplen las decisiones del 2026-10-31: se registra cada solicitud, también sin asesores y al reutilizar un caso; no se guarda texto de mensajes, solo `messages_count`.
- [x] S1, S2, S3, S4, S6 y «Retención» siguen marcadas como REVISAR, cada una con un default seguro y recomendado. Ninguna es irreversible ni pone en riesgo la seguridad, así que en modo nocturno no bloquean.

## EARS, verificabilidad y tasks
- [x] De R1 a R21, cada requirement tiene un solo `DEBE`/`NO DEBE` y su test concreto.
- [x] T1-T24 (incluida T7b) están en `[ ]`, en orden, y entre todas cubren R1-R21. Los fallos se inyectan con `monkeypatch`, sin red y de forma determinista.

## Nada peligroso
- [x] El spec no borra datos, no usa la red y no toca nada fuera del repo.

## Notas para el implementer (no bloquean)
- Las líneas citadas son orientativas; localiza el código por nombre.
- T24: el número de tests previos (887) da igual; lo que cuenta es que todos sigan en verde.

## Decisiones para el humano (siguen abiertas, no bloquean)
1. S2: si falla el registro, el traspaso sigue (recomendado) o se responde `500` sin avisar.
2. S1: valor intermedio `received` (dos escrituras) o un solo `INSERT` al final.
3. S3, S4 y S6: conteo de avisos en los registros `error`, sin `completed_at` y sin deduplicar reintentos.
4. Retención: la tabla guarda `contact_id` y `reason` sin límite de tiempo. Conviene abrir una feature de retención (Ley 1581) antes de producción.
