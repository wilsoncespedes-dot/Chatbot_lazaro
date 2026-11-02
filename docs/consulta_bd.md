# Consultas de datos de solo lectura (feature #26)

Esta guía la ejecuta el dueño de la base de datos, no el código. El orquestador
solo lee por una conexión separada (`DB_QUERY_DATABASE_URL`) con un rol de
PostgreSQL de solo lectura. Mientras `DB_QUERY_ENABLED=false` (valor por
defecto) no se ejecuta ninguna consulta ni se envía el esquema al proveedor de
IA (supuesto S1 de `specs/consulta_bd_lenguaje_natural/design.md`).

## 1. Rol de solo lectura

```sql
CREATE ROLE lazaro_lectura LOGIN PASSWORD '<clave-fuerte>';
ALTER ROLE lazaro_lectura SET default_transaction_read_only = on;
ALTER ROLE lazaro_lectura SET statement_timeout = '5s';
REVOKE ALL ON DATABASE lazaro FROM lazaro_lectura;
GRANT CONNECT ON DATABASE lazaro TO lazaro_lectura;
```

La barrera real no es el `SET` del rol (una sesión puede cambiarlo), sino que el
rol solo tenga `SELECT` sobre las vistas del esquema `consultas` y ningún
permiso sobre el resto:

```sql
CREATE SCHEMA IF NOT EXISTS consultas;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
-- Si el rol hereda privilegios de PUBLIC, revísalos con tu DBA.
GRANT USAGE ON SCHEMA consultas TO lazaro_lectura;
GRANT SELECT ON ALL TABLES IN SCHEMA consultas TO lazaro_lectura;
ALTER DEFAULT PRIVILEGES IN SCHEMA consultas
  GRANT SELECT ON TABLES TO lazaro_lectura;
```

No concedas `SELECT` sobre tablas del esquema `public` ni sobre
`pg_catalog`/`information_schema` más allá de lo que PostgreSQL concede por
defecto.

## 2. Vistas permitidas

El orquestador solo acepta SQL que referencie
`DB_QUERY_VIEWS_SCHEMA.<vista>` para cada entrada de `DB_QUERY_ALLOWLIST`, por
ejemplo:

```env
DB_QUERY_VIEWS_SCHEMA=consultas
DB_QUERY_ALLOWLIST={"consultas.v_pedidos": ["id", "estado", "fecha"], "consultas.v_clientes": ["id", "nombre"]}
```

Regla dura: cada vista debe exponer **exactamente** las columnas de su entrada
en `DB_QUERY_ALLOWLIST`, ni una más ni una menos. Al primer uso, el adaptador
comprueba en `pg_catalog` que el objeto sea una vista (`relkind = 'v'`) y que
las columnas reales (`attnum > 0 AND NOT attisdropped`) coincidan con la
allowlist. Si sobra o falta alguna columna, **toda** consulta responde
`DB_QUERY_UNAVAILABLE_REPLY` y no se ejecuta el SQL. Por eso, al añadir o quitar
una columna de una vista hay que actualizar la allowlist y reiniciar el
orquestador.

La comprobación de catálogo se memoriza por instancia tras el primer éxito: un
`CREATE OR REPLACE VIEW` posterior no se detecta hasta reiniciar. Reinicia el
servicio después de cambiar las vistas.

## 3. Habilitar las consultas

1. Crea el rol y las vistas con los pasos anteriores.
2. Rellena `DB_QUERY_DATABASE_URL` (DSN del rol de lectura), `DB_QUERY_ALLOWLIST`
   y, si hace falta, `DB_QUERY_VIEWS_SCHEMA`.
3. Activa `DB_QUERY_ENABLED=true`.
4. Reinicia el orquestador. `Settings` se niega a arrancar si el DSN está vacío,
   si coincide con `DATABASE_URL` o si la allowlist no es válida.

Al activarlo, el dueño acepta que se envíen al proveedor de IA únicamente los
nombres estáticos de vistas y columnas de la allowlist. Nunca se envían filas,
resultados, conteos ni metadatos leídos de la base.

## 4. Qué se ejecuta y qué se audita

- Una única sentencia `SELECT` validada por allowlist de tokens; sin `;`
  intermedios, comentarios, comillas dobles, `$`, `::` ni funciones fuera de la
  lista. Los tokens se separan solo con espacios ASCII (espacio, tabulador,
  salto de línea, CR y form feed); otros espacios Unicode se rechazan.
- Dentro de una transacción `READ ONLY` con `statement_timeout`, y siempre con
  `ROLLBACK`; la conexión de lectura se cierra al terminar cada consulta.
- Como máximo `DB_QUERY_MAX_ROWS` filas; se pide una más para saber si hubo
  truncado.
- Cada solicitud (incluidas las denegadas y rechazadas) deja una fila en
  `db_query_audit` con perfil, `telegram_user_id`, estado, vistas, número de
  filas y `sql_sha256`. No se guardan la pregunta, el SQL en claro ni las filas.
