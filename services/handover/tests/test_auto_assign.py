"""Asignación automática por carga en handover (feature #52)."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from lazaro_contracts import CaseAutoAssignRequest, ErrorResponse

from handover.adapters.repository import FakeCaseRepository, PostgresCaseRepository
from handover.domain import auto_assign_case
from handover.strategies import obtener_estrategia

HEADERS = {"X-Service-Token": "svc-token"}


def _auto(env, case_id: str = "case-1", candidate_ids: list[str] | None = None):
    return env.client.post(
        f"/cases/{case_id}/auto-assign",
        json={"candidate_ids": candidate_ids or ["111", "222", "333"]},
        headers=HEADERS,
    )


def test_auto_assign_picks_least_loaded(env):
    """R7: elige al candidato con menos casos assigned."""
    env.add_case("busy-1", status="assigned", advisor_id="111", assigned_at=env.clock())
    env.add_case("busy-2", status="assigned", advisor_id="111", assigned_at=env.clock())
    env.add_case("busy-3", status="assigned", advisor_id="222", assigned_at=env.clock())
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=["111", "222"])

    assert response.status_code == 200
    assert response.json() == {
        "status": "assigned",
        "case_id": "case-1",
        "advisor_id": "222",
    }
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id) == ("assigned", "222")


def test_auto_assign_tie_breaks_by_advisor_id(env):
    """R8: a igual carga gana el menor advisor_id lexicográfico."""
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=["333", "222", "111"])

    assert response.status_code == 200
    assert response.json()["advisor_id"] == "111"


def test_auto_assign_ignores_non_roster_candidates(env):
    """R9: descarta candidatos que no son asesores atendedores del roster."""
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=["999", "111", "cliente-1"])

    assert response.status_code == 200
    assert response.json()["status"] == "assigned"
    assert response.json()["advisor_id"] == "111"
    assert env.repo.cases["case-1"].advisor_id == "111"


def test_auto_assign_no_valid_candidates_queued(env):
    """R11: sin candidatos válidos responde queued sin modificar el caso."""
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=["999", "otro"])

    assert response.status_code == 200
    assert response.json() == {
        "status": "queued",
        "case_id": "case-1",
        "advisor_id": None,
    }
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id) == ("open", None)
    assert env.repo.auto_assignments == []


def test_auto_assign_concurrent_no_double_assignment(env):
    """R13: dos asignaciones simultáneas no repiten caso ni carga."""
    env.add_case("case-1", status="open")
    env.add_case("case-2", status="open")
    request = CaseAutoAssignRequest(candidate_ids=["111", "222"])

    def assign(case_id: str):
        return auto_assign_case(case_id, request, env.settings, env.adapters)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(assign, ["case-1", "case-1", "case-2", "case-2"])
        )

    for case_id in ("case-1", "case-2"):
        own = [result for result in results if result.case_id == case_id]
        assert sorted(result.status for result in own) == ["assigned", "skipped"]
    advisors = {
        env.repo.cases["case-1"].advisor_id,
        env.repo.cases["case-2"].advisor_id,
    }
    assert advisors == {"111", "222"}
    assert len(env.repo.auto_assignments) == 2


class _LostToHuman(FakeCaseRepository):
    """Simula una asignación humana entre la lectura y la escritura."""

    def auto_assign(self, case_id, candidate_ids, strategy, at):
        case = self.cases[case_id]
        self.cases[case_id] = case.model_copy(
            update={"status": "assigned", "advisor_id": "222", "assigned_at": at}
        )
        return None


def test_auto_assign_skips_changed_case(env_factory):
    """R14: si una persona asignó el caso antes de escribir, responde skipped."""
    env = env_factory(repo=_LostToHuman())
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=["111", "222"])

    assert response.status_code == 200
    assert response.json() == {
        "status": "skipped",
        "case_id": "case-1",
        "advisor_id": "222",
    }
    assert env.repo.cases["case-1"].advisor_id == "222"
    assert env.repo.auto_assignments == []


def test_auto_assign_unknown_404_closed_409(env):
    """R15: caso inexistente 404 y caso cerrado 409."""
    missing = _auto(env, case_id="no-existe")
    assert missing.status_code == 404
    ErrorResponse.model_validate(missing.json())
    assert missing.json()["error"] == "not_found"

    env.add_case("case-1", status="closed", closed_at=env.clock())
    closed = _auto(env)
    assert closed.status_code == 409
    ErrorResponse.model_validate(closed.json())
    assert closed.json()["error"] == "case_closed"


def test_auto_assign_records_auto_reason(env):
    """R19: guarda case_id, advisor_id, motivo auto y fecha de la asignación."""
    env.add_case("case-1", status="open")
    env.clock.advance(90)

    response = _auto(env, candidate_ids=["111"])

    assert response.json()["status"] == "assigned"
    [record] = env.repo.auto_assignments
    assert (record.case_id, record.advisor_id, record.reason) == (
        "case-1",
        "111",
        "auto",
    )
    assert record.at == env.clock()


def test_auto_assign_requires_token_401(env):
    """R25: sin X-Service-Token válido responde 401 unauthorized."""
    env.add_case("case-1", status="open")
    for headers in ({}, {"X-Service-Token": "otro"}):
        response = env.client.post(
            "/cases/case-1/auto-assign",
            json={"candidate_ids": ["111"]},
            headers=headers,
        )
        assert response.status_code == 401
        ErrorResponse.model_validate(response.json())
        assert response.json()["error"] == "unauthorized"
    assert env.repo.cases["case-1"].status == "open"


class _AutoAssignCursor:
    def __init__(self) -> None:
        self.log: list[tuple[str, tuple]] = []
        self._rows: list = []

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))
        if "SELECT profile_id FROM handover_advisors" in sql:
            self._rows = [("111",), ("222",)]
        elif "SELECT advisor_id, COUNT(*)" in sql:
            self._rows = [("111", 1)]
        elif "SELECT last_advisor_id FROM handover_assignment_pointer" in sql:
            self._rows = []
        elif "UPDATE handover_cases SET status" in sql:
            self._rows = [("case-1",)]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class _AutoAssignConn:
    def __init__(self) -> None:
        self.cursor_obj = _AutoAssignCursor()
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_postgres_auto_assign_uses_lock_conditional_update_and_parameters():
    """R7, R13, R14: candado, UPDATE condicional e INSERT parametrizados."""
    conn = _AutoAssignConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    at = datetime(2026, 1, 2, 3, 0, 0)

    chosen = repo.auto_assign(
        "case-1", ["111", "222"], obtener_estrategia("por_carga"), at
    )

    assert chosen == "222"
    statements = [
        (sql, params)
        for sql, params in conn.cursor_obj.log
        if not sql.startswith(("CREATE", "ALTER", "INSERT INTO handover_roster_state"))
    ]
    assert any("pg_advisory_xact_lock" in sql for sql, _ in statements)
    update = [
        (sql, params)
        for sql, params in statements
        if sql.startswith("UPDATE handover_cases SET status = %s")
    ]
    assert len(update) == 1
    sql, params = update[0]
    assert "status = %s AND advisor_id IS NULL" in sql
    assert "RETURNING case_id" in sql
    insert = [
        (sql, params)
        for sql, params in statements
        if "INSERT INTO handover_auto_assignments" in sql
    ]
    assert len(insert) == 1
    assert "auto" in insert[0][1]
    pointer = [
        (sql, params)
        for sql, params in statements
        if "INSERT INTO handover_assignment_pointer" in sql
    ]
    assert len(pointer) == 1
    assert "ON CONFLICT (strategy) DO UPDATE" in pointer[0][0]
    assert pointer[0][1] == ("por_carga", "222", at)
    for sql, params in statements:
        assert "case-1" not in sql
        assert sql.count("%s") == len(params), sql
        assert not re.search(r"'[^']*'", sql), sql
