# Spec review — #26 consulta_bd_lenguaje_natural (revisión final de seguridad)

**Veredicto:** APPROVED

## Bloqueo previo (alias / `SELECT *`): resuelto
- **Alias de tabla y nombre de vista (R35, design §3):** solo pueden ir como calificador
  `x.` seguido de una columna allowlisted de esa vista. Se rechazan sueltos en cualquier posición,
  así que `SELECT t`, `count(t)`, `max(t)`, `WHERE t IS NOT NULL` y `SELECT v_x` no pueden
  devolver la fila completa como compuesto. Los alias implícitos (sin `AS`) no se clasifican y se
  rechazan. Si coinciden con una columna allowlisted, PostgreSQL resuelve primero la columna.
- **Alias de columna (R36):** solo se aceptan en su declaración o como elemento directo de
  `ORDER BY`, que en PostgreSQL resuelve primero el nombre de salida. Se rechazan dentro de
  funciones y en `WHERE`, `GROUP BY`, `HAVING`, `ON` y como calificador.
- **Colisiones (R34):** un alias no puede llamarse igual que una keyword, una palabra prohibida,
  una función, una vista, una columna de cualquier vista allowlisted ni otro alias.
- **`*` (R16):** solo se acepta en `count(*)` o en una multiplicación entre operandos. Se
  rechazan `SELECT *`, `v.*`, `alias.*` y cualquier `*` tras `.` o `,`.
- **`pg_attribute` (R20, design §3, T7/T16/T20):** el conjunto de columnas reales de cada vista
  (`attnum > 0 AND NOT attisdropped`) tiene que ser exactamente igual al de su allowlist. Si
  sobra o falta alguna columna, se responde `unavailable` sin ejecutar el SQL, sin nombres de
  columnas en el error ni en los logs, y solo se memoriza el éxito. T16 prueba los casos de
  columna sobrante, columna faltante, columnas iguales con la comprobación memorizada, y
  reintento tras un fallo.
- T15 cubre todos los casos de bypass citados en la revisión anterior, además de los casos
  aceptados.

## Correcciones previas: siguen cubiertas
- **EARS:** R1/R31 y R23/R32 separados. Cada `R<n>` tiene un solo `DEBE`/`NO DEBE`.
- **`;` final:** se quita después de validar. `ValidatedQuery.sql` va sin `;` y el hash se
  calcula sobre ese texto (T15).
- **Funciones con espacios:** las adyacencias se evalúan sobre tokens. T15 prueba
  `pg_sleep (1)`, `AS pg_sleep` y `count ( * )`.
- **Dedup Telegram (R33):** `mark_update_if_new` sigue en `main.py:182`, antes de
  `process_message`. T11 prueba que con el mismo `update_id` hay una sola llamada y una sola fila
  de auditoría.

## Cobertura y tasks
- Acceptance: A1 → R1-R7, R30 · A2 → R10-R20, R34-R36 · A3 → R21-R26, R32 · A4 → R27-R30.
- R1-R36 están cubiertos por T1-T20. Todas las tasks están en `[ ]` y en orden.

## No bloqueante (comprobar en la revisión de código)
- **Desincronización de literales:** con `standard_conforming_strings=off`, `'a\''` se cierra
  en PostgreSQL pero sigue abierto para el tokenizador (escape `''`). El riesgo queda limitado
  por el rol de solo `SELECT` sobre vistas, R20, READ ONLY y timeout. Aun así, conviene rechazar
  `\` en el SQL o fijar `SET LOCAL standard_conforming_strings = on` en el adaptador.
- **La comprobación de catálogo se memoriza por instancia:** un `ALTER`/`CREATE OR REPLACE VIEW`
  posterior no se detecta hasta reiniciar. Las reglas R35/R36 ya bloquean el acceso a las
  columnas por sí solas. Conviene mencionarlo en `docs/consulta_bd.md` (reiniciar tras cambiar
  las vistas).
