"""Runner de migraciones: aplica `migrations/NNNN_nombre.sql` una sola vez.

Se ejecuta una vez por despliegue (servicio `migrate` de docker compose), nunca
desde los servicios. Garantías:

- Un `pg_advisory_lock` de sesión impide que dos runners migren a la vez.
- Cada archivo corre en su propia transacción junto con su fila en
  `schema_migrations`; si falla, se revierte entero y el runner se detiene.
- Un archivo ya aplicado cuyo contenido cambió aborta la ejecución
  (las migraciones aplicadas son inmutables; se corrige con una nueva).
- `{{VARIABLE}}` se sustituye solo con las variables permitidas y validadas.

Uso: `python -m migrations.runner [--status]` con `DATABASE_URL` en el entorno.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlparse

logger = logging.getLogger("migrations")

MIGRATIONS_DIR = Path(__file__).resolve().parent
MIGRATION_LOCK_KEY = 7301985
FILE_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
ROLE_PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9_\-.~+=!@#%^*]{16,128}$")

CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "version TEXT PRIMARY KEY, nombre TEXT NOT NULL, sha256 TEXT NOT NULL, "
    "aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now())"
)


class MigrationError(RuntimeError):
    """Falla que detiene el runner sin aplicar más archivos."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str
    sha256: str


def _int_between(low: int, high: int) -> Callable[[str], str]:
    def validate(value: str) -> str:
        if not value.isdigit() or not low <= int(value) <= high:
            raise MigrationError(f"debe ser un entero entre {low} y {high}")
        return str(int(value))

    return validate


# Variables que una migración puede usar y su valor por defecto.
VARIABLES: dict[str, tuple[str, Callable[[str], str]]] = {
    "EMBEDDINGS_DIM": ("1536", _int_between(1, 16000)),
}

# Roles de solo lectura que el runner habilita para LOGIN si su clave está en
# el entorno (la clave nunca se guarda en un archivo de migración).
ROLE_PASSWORD_ENV: dict[str, str] = {
    "bot_lectura": "BOT_LECTURA_PASSWORD",
    "bot_consultas": "BOT_CONSULTAS_PASSWORD",
}


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.sql")):
        match = FILE_PATTERN.match(path.name)
        if match is None:
            raise MigrationError(f"nombre de migración no válido: {path.name}")
        version, name = match.groups()
        if version in seen:
            raise MigrationError(f"versión repetida: {version}")
        seen.add(version)
        # El checksum no depende del fin de línea del checkout (CRLF en Windows).
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        migrations.append(
            Migration(
                version=version,
                name=name,
                path=path,
                sql=raw.decode("utf-8"),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return migrations


def resolve_variables(env: Mapping[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for name, (default, validate) in VARIABLES.items():
        raw = env.get(name, "").strip() or default
        try:
            values[name] = validate(raw)
        except MigrationError as exc:
            raise MigrationError(f"{name} {exc}") from None
    return values


def render(sql: str, variables: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise MigrationError(f"variable no permitida en migración: {name}")
        return variables[name]

    return PLACEHOLDER_PATTERN.sub(replace, sql)


def _applied(cursor: Any) -> dict[str, str]:
    cursor.execute("SELECT version, sha256 FROM schema_migrations")
    return {str(row[0]): str(row[1]) for row in cursor.fetchall()}


def pending(conn: Any, migrations: list[Migration]) -> list[Migration]:
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    applied = _applied(cursor)
    conn.commit()
    result: list[Migration] = []
    for migration in migrations:
        stored = applied.get(migration.version)
        if stored is None:
            result.append(migration)
        elif stored != migration.sha256:
            raise MigrationError(
                f"la migración {migration.path.name} ya aplicada cambió de contenido; "
                "crea una migración nueva en lugar de editarla"
            )
    return result


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sync_role_passwords(conn: Any, env: Mapping[str, str]) -> list[str]:
    """Habilita LOGIN en los roles de solo lectura cuya clave viene en el entorno."""
    updated: list[str] = []
    cursor = conn.cursor()
    for role, variable in ROLE_PASSWORD_ENV.items():
        password = env.get(variable, "")
        if not password:
            continue
        if ROLE_PASSWORD_PATTERN.fullmatch(password) is None:
            raise MigrationError(
                f"{variable} debe tener 16-128 caracteres sin comillas ni espacios"
            )
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if not cursor.fetchall():
            raise MigrationError(f"el rol {role} no existe; ¿faltan migraciones?")
        # ALTER ROLE no admite parámetros: la clave ya pasó la lista blanca.
        cursor.execute(
            f"ALTER ROLE {role} WITH LOGIN PASSWORD {_quote_literal(password)}"
        )
        updated.append(role)
    conn.commit()
    return updated


def run_migrations(
    conn: Any,
    migrations: list[Migration],
    variables: Mapping[str, str],
) -> list[str]:
    """Aplica las pendientes bajo el lock; devuelve las versiones aplicadas."""
    cursor = conn.cursor()
    cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
    conn.commit()
    applied_now: list[str] = []
    try:
        for migration in pending(conn, migrations):
            sql = render(migration.sql, variables)
            try:
                cursor = conn.cursor()
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO schema_migrations (version, nombre, sha256) "
                    "VALUES (%s, %s, %s)",
                    (migration.version, migration.name, migration.sha256),
                )
                conn.commit()
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001 - la conexión puede estar rota
                    pass
                raise MigrationError(
                    f"falló {migration.path.name}: {type(exc).__name__}: {exc}"
                ) from exc
            logger.info("migración aplicada: %s", migration.path.name)
            applied_now.append(migration.version)
    finally:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
            conn.commit()
        except Exception:  # noqa: BLE001 - al cerrar la sesión se libera igual
            pass
    return applied_now


def connect(database_url: str) -> Any:
    import pg8000.dbapi

    parsed = urlparse(database_url)
    return pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/").lstrip("/"),
    )


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--status", action="store_true", help="solo lista pendientes")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    database_url = env.get("MIGRATIONS_DATABASE_URL") or env.get("DATABASE_URL", "")
    if not database_url:
        logger.error("Falta DATABASE_URL (o MIGRATIONS_DATABASE_URL).")
        return 2
    try:
        migrations = load_migrations()
        variables = resolve_variables(env)
        conn = connect(database_url)
        try:
            if args.status:
                names = [m.path.name for m in pending(conn, migrations)]
                logger.info("pendientes: %s", ", ".join(names) or "ninguna")
                return 0
            applied = run_migrations(conn, migrations, variables)
            roles = sync_role_passwords(conn, env)
        finally:
            conn.close()
    except MigrationError as exc:
        logger.error("%s", exc)
        return 1
    logger.info(
        "listo: %d aplicadas%s",
        len(applied),
        f"; LOGIN habilitado para {', '.join(roles)}" if roles else "",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
