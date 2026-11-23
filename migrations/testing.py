"""Bases Postgres desechables con todas las migraciones aplicadas (solo tests).

`TEST_DATABASE_URL` debe apuntar a un Postgres local (p. ej. el contenedor
`pgvector/pgvector:pg16`) con un usuario que pueda crear bases. Nunca se usa
la base de producción: cada test crea la suya y la borra al terminar.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlparse, urlunparse

from .runner import connect, load_migrations, resolve_variables, run_migrations

TEST_DATABASE_ENV = "TEST_DATABASE_URL"


def database_url_for_tests() -> str | None:
    return os.environ.get(TEST_DATABASE_ENV) or None


def _with_db(url: str, name: str) -> str:
    return urlunparse(urlparse(url)._replace(path=f"/{name}"))


@contextmanager
def migrated_database(admin_url: str | None = None) -> Iterator[str]:
    """Crea una base nueva, aplica `migrations/*.sql` y la borra al salir."""
    admin_url = admin_url or database_url_for_tests()
    if not admin_url:
        raise RuntimeError(f"{TEST_DATABASE_ENV} no está definido")
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = connect(admin_url)
    admin.autocommit = True
    admin.cursor().execute(f"CREATE DATABASE {name}")
    url = _with_db(admin_url, name)
    try:
        conn = connect(url)
        try:
            run_migrations(conn, load_migrations(), resolve_variables({}))
        finally:
            conn.close()
        yield url
    finally:
        cursor = admin.cursor()
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (name,),
        )
        cursor.execute(f"DROP DATABASE IF EXISTS {name}")
        admin.close()
