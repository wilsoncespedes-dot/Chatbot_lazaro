# Review — feature #26 consulta_bd_lenguaje_natural

**Veredicto:** APPROVED

Verificación: se toma la ejecución de `./init.sh` informada por el leader (exit 0, 1758 tests).
Los 36 tests citados en `progress/impl_consulta_bd_lenguaje_natural.md` existen en
`services/orchestrator/tests/test_db_query.py` (lo comprobé por script).

## Seguridad (foco pedido)

- **Parser SQL** (`orchestrator/db_query.py`): es una allowlist real de tokens. `;` interno,
  `--`, `/* */`, `"`, `$`, `::` y `\` se rechazan antes de tokenizar (l.139-145). Cualquier
  carácter fuera de palabra, número, literal `'..'` u operador fijo da `invalid_token`. Cada
  palabra tiene que ser una keyword permitida, una función permitida seguida de `(` (esto se
  comprueba antes que el alias, l.496-499), un calificador de vista o alias seguido de `.` y una
  columna allowlisted, una columna de una vista referenciada, o un alias de columna como
  elemento directo de `ORDER BY`. Tras `FROM`/`JOIN` solo se acepta
  `<schema>.<vista>` allowlisted (l.293-330); se rechazan el alias implícito, las subconsultas en
  `FROM` y las listas con coma.
- **Bypasses probados a mano**: `SELECT *`, `v.*`, `t.*`, alias/vista sueltos (fila completa),
  `AS pg_sleep`, alias de columna en WHERE/GROUP/HAVING/ON/funciones y las colisiones de alias
  se rechazan todos. Las subconsultas escalares sobre vistas allowlisted se aceptan, y es
  correcto. No encontré ninguna ruta hacia una relación, función o columna fuera de la allowlist.
- **Transacción** (`adapters/db_query.py:61-94`): pg8000 con `autocommit` desactivado abre
  `BEGIN` implícito. Después se ejecutan `SET TRANSACTION READ ONLY`, luego
  `SET LOCAL statement_timeout`, la verificación de catálogo (`relkind='v'` + columnas exactas
  en `pg_attribute`, memorizada solo si tiene éxito), la consulta envuelta en `LIMIT max+1`, y
  `ROLLBACK` en `finally`. El DSN es separado y `Settings` lo valida (`config.py:172-181`).
- **Autorización** (`domain.py:663-682`): perfil `asesor` vinculado, `uid > 0` y
  `chat_id == uid`, todo evaluado antes de mirar si la pregunta está mal formada y antes del
  flag. `profiles.telegram_user_id` es `UNIQUE` (`repository.py:459`).
- **Auditoría/filtrado**: la auditoría solo guarda hash, vistas, conteo y estado. Los logs son
  etiquetas fijas sin datos. `DbQueryUnavailable` se relanza sin el mensaje original
  (`from None`). `_process` en `main.py` registra solo el nombre del tipo de excepción. Si la
  auditoría falla, la respuesta es `unavailable` y no se envían filas (`domain.py:645-653`).

## Trazabilidad requirements ↔ tests
- R1-R36: [x] el mapa completo está en `progress/impl_consulta_bd_lenguaje_natural.md:32-67` y
  todos los tests existen.

## Tasks completas
- T1-T20: [x] (`specs/consulta_bd_lenguaje_natural/tasks.md`). La nota de T19 está justificada.

## Checkpoints (aplicables a la feature)
- C1: [x]  · C2: [x]  · C3: [x] (sin dependencias nuevas, SQL de usuario solo tras validación
  por allowlist, variables en `.env.example`)  · C4: [x] (fakes; sin BD real)  · C5: [x]
  · C6: [x]

## Observaciones no bloqueantes (follow-up recomendado)
1. `adapters/db_query.py:65`: la conexión de lectura nunca se cierra (`connection.close()`
   falta en `finally`). Hoy depende del GC; bajo carga puede agotar el límite de conexiones del
   rol de lectura.
2. `db_query.py:152`: `str.isspace()` acepta espacios Unicode (p. ej. U+00A0), y PostgreSQL los
   trata como parte de un identificador. Ahora mismo no es explotable (solo produce errores o
   nombres inexistentes, y R20 y los GRANT lo acotan), pero conviene limitar los separadores a
   espacios ASCII para que el tokenizador y PG nunca discrepen.
3. Falsos negativos conservadores, sin impacto de seguridad: `IN (...)`, `(subconsulta) > 0`
   en `WHERE` y `t.col * t.otra` se rechazan.

## Addendum 2026-11-01: revisión del hardening

**Veredicto se mantiene: APPROVED.** No hay regresión. `./init.sh` está en verde, con 1777 tests.

- **Obs. 1 resuelta** (`adapters/db_query.py:58-99`): `run()` usa `try/except/finally`. El
  `finally` ejecuta `ROLLBACK` si hay cursor y luego `connection.close()` si hay conexión. Cada
  paso va en su propio `try/except` y registra solo etiquetas fijas (`db_query_rollback_failed`,
  `db_query_close_failed`). Así, un fallo de ROLLBACK no impide el cierre. Un fallo de cierre no
  sustituye ni el `return` del resultado ni la `DbQueryUnavailable` en curso, porque la excepción
  se captura dentro del `finally`. Si falla `connect()` o `cursor()`, igualmente se cierra lo que
  exista. Tests: `test_adapter_uses_read_only_transaction_timeout_limit_and_rollback`,
  `test_adapter_rolls_back_and_closes_after_execution_error` (ROLLBACK y cierre después del error,
  en ese orden), `test_adapter_close_failure_does_not_replace_query_result` (resultado intacto y
  el log no filtra el mensaje) y `test_adapter_rejects_non_view_object_without_running_sql`
  (cierre en el camino de catálogo inválido).
- **Obs. 2 resuelta** (`db_query.py:41-43,155`): el tokenizador solo salta
  `_ASCII_WHITESPACE = " \t\r\n\f\v"`. Cualquier otro separador cae en `invalid_token`. El
  `strip()` de los extremos acepta espacios Unicode, pero `normalized` (`db_query.py:534`)
  aplica el mismo `strip()`, así que el SQL ejecutado no los contiene. Dentro de un literal
  `'...'` siguen permitidos, lo cual es correcto. Tests:
  `test_validate_sql_rejects_non_ascii_whitespace` (4 separadores × 4 posiciones),
  `test_validate_sql_accepts_ascii_whitespace` y
  `test_unicode_whitespace_sql_is_rejected_without_database` (de punta a punta, sin llamar a la
  BD). Los tests de rechazo de SQL anteriores (`test_safe_sql_is_accepted` y los de rechazo)
  siguen presentes y sin relajar.
- Menor, no bloqueante: no hay un test explícito para un fallo de `ROLLBACK`. El código es
  trivialmente correcto (un `try` independiente antes del cierre).
