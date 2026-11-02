# Design — consulta_bd_lenguaje_natural (feature #26)

Servicio: **orchestrator**. Sin cambios en `contracts/`, otros servicios ni `docker-compose.yml`.
No hay código externo reutilizado (no existe `referencias/`).

## 1. Flujo

`process_message` (domain.py): tras `parse_start_token` y **antes** de `parse_advisor_command`:

```
q = parse_db_query_command(text)            # None | DbQueryCommand(question) | MalformedDbQuery
if q is not None: handle_db_query(request, q, settings, adapters); return
```

Deduplicación (R33): `POST /messages` sigue llamando a `repo.mark_update_if_new(update_id)`
antes de encolar `process_message`; un `update_id` repetido devuelve `duplicate` y nunca llega a
`handle_db_query`. El desvío de `/consultar` va dentro de `process_message` (antes de
`add_message`, R31), así que no se añade ninguna ruta que se salte esa comprobación.

`handle_db_query` (orden fijo):
1. Autorizar (R4-R7): `repo.get_profile_by_telegram_user_id(uid)`; exige `role=="asesor"`,
   `uid > 0`, `chat_id == uid`. Si falla → audit `forbidden` + `DB_QUERY_FORBIDDEN_REPLY`.
2. `MalformedDbQuery` → audit `malformed` + `DB_QUERY_HELP_REPLY` (R2).
3. `not settings.db_query_enabled` → audit `disabled` + `DB_QUERY_DISABLED_REPLY` (R3).
4. `system, user = build_sql_prompt(question, allowlist)`; `adapters.llm.complete(...)`;
   `parse_sql_answer(raw)` → `DbQueryRejected` si inválido (R10-R12).
5. `validate_sql(sql, allowlist, schema, max_joins)` → `ValidatedQuery(sql, views)` o
   `DbQueryRejected` (R13-R17, R25, R27-R29, R34-R36).
6. `adapters.db_query.run(validated, max_rows, timeout_ms)` → `QueryResult(columns, rows,
   truncated)`; `DbQueryUnavailable` en fallo, si alguna vista no es vista o si sus columnas
   reales no coinciden exactamente con la allowlist (R18-R20, R24).
7. `repo.add_db_query_audit(...)` (R21-R23, R32); si lanza → `DB_QUERY_UNAVAILABLE_REPLY`, sin filas.
8. `format_rows(result, max_reply_chars)` → `_notify_sender` (R26).

Status de auditoría: `forbidden | malformed | disabled | rejected | unavailable | ok`.
Solo `ok` lleva `row_count > 0`. `sql_sha256` = sha256 hex del SQL validado o `""`.
`views` = nombres calificados separados por coma, o `""`.

## 2. Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/db_query.py` (nuevo) | Lógica pura: parser del comando, prompt, `parse_sql_answer`, `validate_sql`, `format_rows`, constantes, excepciones. Sin IO. |
| `services/orchestrator/orchestrator/adapters/db_query.py` (nuevo) | `DbQueryClient` (Protocol), `PostgresReadOnlyQuery`, `FakeDbQuery`. |
| `services/orchestrator/orchestrator/domain.py` | `Adapters.db_query`, `handle_db_query`, enganche en `process_message`. |
| `services/orchestrator/orchestrator/adapters/repository.py` | `get_profile_by_telegram_user_id`, `add_db_query_audit`; tabla `db_query_audit` en `_SCHEMA` (Fake + Postgres). |
| `services/orchestrator/orchestrator/config.py` | Campos `db_query_*`, propiedad `db_query_allowlist_map`, validación R8-R9 en el `model_validator`. |
| `services/orchestrator/orchestrator/main.py` | Construir `PostgresReadOnlyQuery` solo si `db_query_enabled`; si no, un cliente que lanza `DbQueryUnavailable` (nunca se llama). |
| `services/orchestrator/tests/fakes.py` / `conftest.py` | Inyectar `FakeDbQuery` que registra llamadas. |
| `services/orchestrator/tests/test_db_query.py` (nuevo) | Tests de R1-R36. |
| `.env.example` | Variables nuevas con defaults seguros. |
| `docs/consulta_bd.md` (nuevo) | SQL de referencia para el dueño: rol de lectura, esquema `consultas`, `GRANT SELECT` solo sobre vistas, `REVOKE` en `public`; regla de que cada vista expone exactamente las columnas de su entrada en `DB_QUERY_ALLOWLIST` (si no, `unavailable`). |

## 3. Firmas

```python
# db_query.py
DB_QUERY_COMMAND = "/consultar"
ALLOWED_KEYWORDS: frozenset[str]   # SELECT DISTINCT FROM JOIN INNER LEFT ON WHERE AND OR NOT IN IS
                                   # NULL LIKE ILIKE BETWEEN GROUP BY ORDER ASC DESC LIMIT AS HAVING
                                   # CASE WHEN THEN ELSE END TRUE FALSE
ALLOWED_FUNCTIONS: frozenset[str]  # count sum avg min max lower upper coalesce date_trunc
@dataclass(frozen=True) class DbQueryCommand: question: str
@dataclass(frozen=True) class MalformedDbQuery: ...
@dataclass(frozen=True) class ValidatedQuery: sql: str; views: tuple[str, ...]
@dataclass(frozen=True) class QueryResult: columns: list[str]; rows: list[tuple]; truncated: bool
class DbQueryRejected(Exception): reason: str      # motivo solo para tests; nunca al usuario/log
class DbQueryUnavailable(Exception): ...

def parse_db_query_command(text: str, max_len: int) -> DbQueryCommand | MalformedDbQuery | None
def build_sql_prompt(question: str, allowlist: dict[str, tuple[str, ...]]) -> tuple[str, str]
def parse_sql_answer(raw: str) -> str
def validate_sql(sql: str, allowlist: dict[str, tuple[str, ...]], schema: str, max_joins: int) -> ValidatedQuery
def format_rows(result: QueryResult, max_chars: int, truncated_note: str) -> str

# adapters/db_query.py
class DbQueryClient(Protocol):
    def run(self, query: ValidatedQuery, max_rows: int, timeout_ms: int) -> QueryResult: ...
class PostgresReadOnlyQuery:  # conexión propia (pg8000, _pg_connect reutilizado), threading.Lock
    def __init__(self, database_url: str, allowlist: dict[str, tuple[str, ...]],
                 connect: Callable[[], Any] | None = None) -> None

# repository.py (Protocol + Fake + Postgres)
def get_profile_by_telegram_user_id(self, telegram_user_id: int) -> Profile | None
def add_db_query_audit(self, profile_id: str | None, telegram_user_id: int, status: str,
                       views: str, row_count: int, sql_sha256: str, at: datetime) -> None
```

`validate_sql`: tokenizador propio por allowlist (no lista negra). Tokens permitidos: palabras
(`[A-Za-z_][A-Za-z0-9_]*`), números, literales `'...'` (con `''` como escape, sin `E'`),
operadores `= <> != < > <= >= , ( ) . * + - /`. Todo token palabra debe ser keyword permitida,
función permitida (seguida de `(`), vista allowlisted (calificada, tras `FROM`/`JOIN`), columna
allowlisted de una vista referenciada (sola o `vista.col`/`alias.col`), o alias en una de las
posiciones permitidas abajo. Primer token `SELECT` obligatorio. Comparación sin distinguir
mayúsculas. Todas las reglas de adyacencia («seguido de», «precedido de») se evalúan sobre la
lista de tokens, nunca sobre el texto: los espacios no son tokens, así que `pg_sleep (1)` y
`count ( * )` se tratan igual que sin espacios.

Reglas adicionales de `validate_sql`:
- **`;` final (R13):** tras validar, se eliminan los espacios finales y un único `;` final; el
  `ValidatedQuery.sql` resultante no contiene `;`, de modo que el adaptador puede envolverlo en
  `SELECT * FROM (<sql>) AS q LIMIT n`. `sql_sha256` se calcula sobre ese SQL sin `;`.
- **`*` (R16):** el token `*` solo se acepta (a) como `count ( * )`, es decir, precedido de `(`
  cuyo token anterior es `count` y seguido de `)`, o (b) como multiplicación, con un operando
  (número, columna, `)` o literal) inmediatamente antes y otro inmediatamente después. Se
  rechazan `SELECT *`, `SELECT <vista>.*`, `SELECT <alias>.*` y cualquier `*` tras `.` o `,`.
  El `SELECT *` exterior del adaptador no pasa por el validador y solo proyecta las columnas
  ya filtradas por la consulta interna.
- **Funciones (R14):** toda palabra cuyo siguiente token sea `(` debe estar en
  `ALLOWED_FUNCTIONS`, aunque coincida con un alias, columna o keyword; si no, rechazo.
- **Clasificación de alias:** un `AS <id>` justo tras `<schema>.<vista>` en `FROM`/`JOIN`
  declara un *alias de tabla*; un `AS <id>` en la lista `SELECT` (antes del primer `FROM`)
  declara un *alias de columna*. Cualquier otro `AS` (p. ej. dentro de `CASE` o tras `WHERE`) se
  rechaza. Las declaraciones se recogen en una primera pasada; la validación de usos, en una
  segunda.
- **Alias de tabla y nombre de vista (R35):** fuera de su declaración solo se aceptan como
  calificador: el token siguiente debe ser `.` y el posterior una columna allowlisted de esa
  vista. Suelto en cualquier posición (`SELECT t`, `count(t)`, `max(t)`, `WHERE t IS NULL`,
  `t = t`) → rechazo, porque PostgreSQL lo resolvería como la fila completa (compuesto) con
  columnas no allowlisted.
- **Alias de columna (R36):** fuera de su declaración solo se acepta como elemento directo de
  `ORDER BY`: precedido de `BY` o `,` dentro de la cláusula `ORDER BY` y seguido de `ASC`,
  `DESC`, `,`, `LIMIT` o fin. En cualquier otra posición (dentro de `(`…`)`, en una expresión,
  en `WHERE`, `GROUP BY`, `HAVING`, `ON`, o seguido de `.`) → rechazo. Así
  `SELECT lower(c) AS c ... WHERE c LIKE '3%'` no puede hacer que `c` resuelva a la columna real.
- **Colisiones de alias (R34):** el identificador tras `AS` no puede coincidir (sin distinguir
  mayúsculas) con ninguna palabra de `ALLOWED_KEYWORDS`, de la lista prohibida de R14, de
  `ALLOWED_FUNCTIONS`, con un nombre de vista (sin esquema), con una columna de **cualquier**
  vista allowlisted ni con otro alias ya declarado; si coincide, rechazo. Así `... AS pg_sleep`
  no habilita `pg_sleep(...)` y un alias no puede enmascarar una columna. El validador es puro y
  solo conoce la allowlist; la garantía de que «columna allowlisted» = «columna real» la da la
  verificación `pg_attribute` del adaptador (R20), de modo que un alias igual a una columna real
  no permitida (`AS secreto`) es imposible en ejecución: o `secreto` está en la allowlist (y se
  rechaza por colisión) o la vista tiene una columna extra (y el adaptador responde
  `unavailable`).

`PostgresReadOnlyQuery.run`:
```
SET TRANSACTION READ ONLY
SET LOCAL statement_timeout = <timeout_ms int>
-- primera vez: SELECT n.nspname||'.'||c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ...
--   WHERE n.nspname||'.'||c.relname = ANY(%s)  → todas deben existir con relkind 'v' (R20)
-- primera vez: SELECT n.nspname||'.'||c.relname, a.attname FROM pg_attribute a
--   JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
--   WHERE n.nspname||'.'||c.relname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped
--   → por cada vista, set(attname) == set(columnas allowlisted) (igualdad exacta) (R20)
SELECT * FROM (<sql validado>) AS q LIMIT <max_rows + 1>
ROLLBACK   (siempre, en finally)
```
Ambas comprobaciones de catálogo (`relkind` y columnas) se hacen la primera vez dentro de la
misma transacción READ ONLY; el resultado positivo se memoriza en la instancia (bajo el
`threading.Lock`). Si cualquiera falla (vista ausente, `relkind <> 'v'`, columna de más o de
menos), `run` lanza `DbQueryUnavailable` sin ejecutar el SQL validado, no memoriza el fallo (se
reintenta en la siguiente llamada) y no incluye en la excepción ni en logs los nombres de
columnas. Estas consultas son internas del adaptador y su resultado nunca sale del adaptador (R11).

Tabla: `CREATE TABLE IF NOT EXISTS db_query_audit (id BIGSERIAL PRIMARY KEY, profile_id TEXT,
telegram_user_id BIGINT NOT NULL, status TEXT NOT NULL, views TEXT NOT NULL, row_count INTEGER
NOT NULL, sql_sha256 TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)`.

Prompt (`build_sql_prompt`): sistema fijo («devuelve solo JSON `{"sql": ...}`, una sentencia
SELECT, solo estas vistas/columnas»), luego la lista `schema.vista(col1, col2)`. Usuario: la
pregunta pasada por `_neutralize` existente. Ningún dato de filas.

## 4. Configuración (`.env.example`)

| Variable | Default | Validación |
|---|---|---|
| `DB_QUERY_ENABLED` | `false` | bool |
| `DB_QUERY_DATABASE_URL` | `""` | R8 si enabled |
| `DB_QUERY_VIEWS_SCHEMA` | `consultas` | identificador |
| `DB_QUERY_ALLOWLIST` | `""` | JSON `{"consultas.v_x": ["col", ...]}`; R9 si enabled |
| `DB_QUERY_MAX_ROWS` | `50` | 1-200 |
| `DB_QUERY_TIMEOUT_MS` | `5000` | 100-30000 |
| `DB_QUERY_MAX_JOINS` | `1` | 0-3 |
| `DB_QUERY_MAX_QUESTION_LENGTH` | `500` | 1-2000 |
| `DB_QUERY_MAX_REPLY_CHARS` | `3500` | 200-4000 |
| `DB_QUERY_HELP_REPLY`, `_FORBIDDEN_REPLY`, `_DISABLED_REPLY`, `_REJECTED_REPLY`, `_UNAVAILABLE_REPLY`, `_TRUNCATED_NOTE` | textos fijos en español | no vacíos |

## 5. Excepciones

Nuevas: `DbQueryRejected`, `DbQueryUnavailable` (en `db_query.py`). Se reutiliza
`ServiceUnavailable` del LLM: se traduce a `unavailable`. Ninguna se propaga a `POST /messages`
(sigue respondiendo como hoy).

## 6. Alternativas descartadas

- **`sqlglot` para parsear SQL:** robusto pero añade dependencia y superficie; una allowlist de
  tokens estrecha es suficiente para SELECT simples y más fácil de auditar. Revaluable si se
  amplía la gramática.
- **Lista negra con regex de palabras peligrosas:** eludible (mayúsculas, comentarios,
  funciones); se usa allowlist.
- **Bot separado para personal (§10):** fuera de alcance; la restricción a chat privado + perfil
  asesor vinculado cubre el acceptance sin infraestructura nueva.
- **Usar `DATABASE_URL` con `SET TRANSACTION READ ONLY`:** una sesión puede revertirlo (§6.1);
  se exige DSN separado con rol de solo `SELECT` sobre vistas.

## 7. Dependencias nuevas

Ninguna (pg8000 ya está).

## 8. Supuestos a confirmar (§12)

- **S1 — Envío del esquema al proveedor de IA** (duda abierta): `DB_QUERY_ENABLED=false` por
  defecto. Activarlo equivale a que el dueño acepta enviar al proveedor **solo** los nombres
  estáticos de vistas/columnas de `DB_QUERY_ALLOWLIST`. Nunca se envían filas ni resultados.
  Mientras esté apagado, ninguna consulta se ejecuta (R3).
- **S2 — Número de JOIN** (duda abierta): `DB_QUERY_MAX_JOINS=1`.
- **S3 — SQL en auditoría:** §6.4 pide guardar el SQL; por «sin datos sensibles» se guarda
  `sql_sha256` + vistas, no el SQL en claro (el SQL puede llevar literales con datos personales,
  Ley 1581). Default seguro; cambiarlo requeriría otra feature.
- **S4 — Consultas predefinidas con parámetros (§6.5):** fuera de esta feature.
- La creación real del rol de lectura y de las vistas la hace el dueño con `docs/consulta_bd.md`;
  el código verifica que los objetos sean vistas y que sus columnas coincidan exactamente con la
  allowlist (R20) pero no las crea.
