"""Adaptador de datos propios del cliente: RLS, catálogo y transacción (#39)."""
from __future__ import annotations

import pytest

from orchestrator.adapters.client_data import (
    FakeClientData,
    PostgresClientDataQuery,
)
from orchestrator.db_query import DbQueryUnavailable, QueryResult, ValidatedQuery

ALLOWLIST = {"mis_datos.v_datos": ("cliente_id", "nombre")}
QUERY = ValidatedQuery(
    sql="SELECT nombre FROM mis_datos.v_datos", views=("mis_datos.v_datos",)
)
RESULT_ROWS = [("Ana",)]


class _Cursor:
    def __init__(
        self,
        *,
        role_rows=None,
        kinds=None,
        columns=None,
        probe_rows=None,
        query_rows=None,
        query_error: bool = False,
    ) -> None:
        self.log: list[tuple[str, tuple]] = []
        self.role_rows = [(False, False)] if role_rows is None else role_rows
        self.kinds = kinds or {name: "v" for name in ALLOWLIST}
        self.columns = columns or {
            name: list(cols) for name, cols in ALLOWLIST.items()
        }
        self.probe_rows = [] if probe_rows is None else probe_rows
        self.query_rows = RESULT_ROWS if query_rows is None else query_rows
        self.query_error = query_error
        self._rows: list = []
        self.description = None

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))
        self._rows = []
        if sql.startswith("SELECT rolsuper"):
            self._rows = list(self.role_rows)
        elif "c.relkind" in sql:
            names = params[0]
            self._rows = [(name, self.kinds.get(name)) for name in names]
        elif "a.attname" in sql:
            names = params[0]
            for name in names:
                for column in self.columns.get(name, []):
                    self._rows.append((name, column))
        elif sql.startswith("SELECT 1 FROM"):
            self._rows = list(self.probe_rows)
        elif sql.startswith("SELECT * FROM"):
            if self.query_error:
                raise RuntimeError("fallo de consulta")
            self._rows = list(self.query_rows)
            self.description = [("nombre",)]

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def _adapter(cursor: _Cursor, *, connect=None):
    conn = _Conn(cursor)
    adapter = PostgresClientDataQuery(
        "postgresql://ro@db/clientes",
        ALLOWLIST,
        "lazaro.cliente_id",
        connect=connect or (lambda: conn),
    )
    return adapter, conn


def test_r27_r28_order_and_cliente_id_only_as_parameter():
    """R27, R28: transacción de solo lectura, set_config parametrizado y ROLLBACK."""
    cursor = _Cursor()
    adapter, conn = _adapter(cursor)

    result = adapter.run(QUERY, "cliente-A", 20, 5000)

    assert result.rows == RESULT_ROWS
    statements = [sql for sql, _ in cursor.log]
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert statements[1].startswith("SET LOCAL statement_timeout = 5000")
    set_config = next(
        index
        for index, (sql, _params) in enumerate(cursor.log)
        if sql.startswith("SELECT set_config(%s, %s, true)")
    )
    assert cursor.log[set_config][1] == ("lazaro.cliente_id", "cliente-A")
    consulta = next(
        index for index, (sql, _) in enumerate(cursor.log) if sql.startswith("SELECT * FROM")
    )
    assert set_config < consulta
    assert statements[-1] == "ROLLBACK"
    assert conn.closed is True
    assert all(
        "cliente-A" not in sql for sql, _params in cursor.log
    )


def test_r29_r30_r31_first_use_checks_run_before_the_query():
    """R29–R31: rol, catálogo y sonda de RLS se comprueban en el primer uso."""
    cursor = _Cursor()
    adapter, _ = _adapter(cursor)

    adapter.run(QUERY, "cliente-A", 20, 5000)

    statements = [sql for sql, _ in cursor.log]
    roles = next(i for i, sql in enumerate(statements) if sql.startswith("SELECT rolsuper"))
    kinds = next(i for i, sql in enumerate(statements) if "c.relkind" in sql)
    columns = next(i for i, sql in enumerate(statements) if "a.attname" in sql)
    probe = next(i for i, sql in enumerate(statements) if sql.startswith("SELECT 1 FROM"))
    assert roles < kinds < columns < probe


def test_first_use_checks_are_memoized_after_success():
    """R29–R31: la verificación de catálogo y RLS no se repite en cada consulta."""
    cursor = _Cursor()
    adapter, _ = _adapter(cursor)

    adapter.run(QUERY, "cliente-A", 20, 5000)
    cursor.log.clear()
    adapter.run(QUERY, "cliente-A", 20, 5000)

    statements = [sql for sql, _ in cursor.log]
    assert not any("pg_roles" in sql for sql in statements)
    assert not any("c.relkind" in sql for sql in statements)
    assert not any(sql.startswith("SELECT 1 FROM") for sql in statements)


def test_r29_invalid_catalog_fails_closed_without_querying():
    """R29: si el objeto no es una vista con sus columnas, no se ejecuta el SQL."""
    cursor = _Cursor(kinds={"mis_datos.v_datos": "r"})
    adapter, conn = _adapter(cursor)

    with pytest.raises(DbQueryUnavailable):
        adapter.run(QUERY, "cliente-A", 20, 5000)

    assert not any(sql.startswith("SELECT * FROM") for sql, _ in cursor.log)
    assert cursor.log[-1][0] == "ROLLBACK"
    assert conn.closed is True


@pytest.mark.parametrize(
    "role_rows", [[(True, False)], [(False, True)], [(True, True)]]
)
def test_r30_superuser_or_bypassrls_fails_closed(role_rows):
    """R30: un rol con privilegios de superusuario o BYPASSRLS no consulta."""
    cursor = _Cursor(role_rows=role_rows)
    adapter, conn = _adapter(cursor)

    with pytest.raises(DbQueryUnavailable):
        adapter.run(QUERY, "cliente-A", 20, 5000)

    assert not any(sql.startswith("SELECT * FROM") for sql, _ in cursor.log)
    assert conn.closed is True


def test_r31_rls_probe_returning_a_row_fails_closed():
    """R31: si la sonda con setting vacío devuelve una fila, la RLS no está activa."""
    cursor = _Cursor(probe_rows=[(1,)])
    adapter, conn = _adapter(cursor)

    with pytest.raises(DbQueryUnavailable):
        adapter.run(QUERY, "cliente-A", 20, 5000)

    assert not any(sql.startswith("SELECT * FROM") for sql, _ in cursor.log)
    assert conn.closed is True


def test_query_error_always_rolls_back_and_closes():
    """R27: incluso con error se hace ROLLBACK y se cierra la conexión."""
    cursor = _Cursor(query_error=True)
    adapter, conn = _adapter(cursor)

    with pytest.raises(DbQueryUnavailable):
        adapter.run(QUERY, "cliente-A", 20, 5000)

    assert cursor.log[-1][0] == "ROLLBACK"
    assert conn.closed is True


def test_fake_client_data_only_returns_rows_for_the_requested_client():
    """R57: la versión falsa simula RLS y solo devuelve las filas de su cliente."""
    fake = FakeClientData(
        {
            "A": QueryResult(columns=["nombre"], rows=[("Ana",)], truncated=False),
            "B": QueryResult(columns=["nombre"], rows=[("Beto",)], truncated=False),
        }
    )

    result = fake.run(QUERY, "A", 20, 5000)

    assert result.rows == [("Ana",)]
    assert fake.calls == [(QUERY, "A", 20, 5000)]
