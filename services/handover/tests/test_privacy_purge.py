"""Retención y purga de datos personales de handover (#27)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from handover.adapters.repository import PostgresCaseRepository
from handover.domain import Denial, HandoverRequestRecord

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
NOW = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=30)
ACTIVE_CUTOFF = NOW - timedelta(days=7)


def _purge(env, headers: dict | None = HEADERS):
    return env.client.post("/privacy/purge", json={}, headers=headers)


def _request(case_id: str | None, received_at: datetime) -> HandoverRequestRecord:
    return HandoverRequestRecord(
        requested_case_id=case_id or "case-x",
        case_id=case_id,
        contact_id="contact-1",
        reason="user_request",
        received_at=received_at,
        result="received",
        advisors_configured=0,
        notices_delivered=0,
        messages_count=1,
    )


def test_purge_requires_service_token(env):
    """R33: sin X-Service-Token válido responde 401 sin borrar nada."""
    env.add_case("case-1", status="closed", closed_at=CUTOFF - timedelta(days=1))
    response = _purge(env, headers={})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert env.repo.get_case("case-1") is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"privacy_retention_days": ""},
        {"privacy_active_case_max_days": ""},
    ],
)
def test_purge_without_retention_config_returns_503(env_factory, overrides):
    """R32: si falta cualquiera de las dos variables responde 503 sin borrar nada."""
    env = env_factory(settings_overrides=overrides)
    env.add_case(
        "case-1", status="closed", created_at=CUTOFF - timedelta(days=5),
        closed_at=CUTOFF - timedelta(days=1),
    )
    response = _purge(env)
    assert response.status_code == 503
    assert response.json()["error"] == "privacy_not_configured"
    assert env.repo.get_case("case-1") is not None


def test_closed_cases_before_cutoff_are_deleted(env):
    """R34: los casos closed con closed_at < corte se borran y los recientes se conservan."""
    env.add_case(
        "old", status="closed", created_at=CUTOFF - timedelta(days=5),
        closed_at=CUTOFF - timedelta(seconds=1),
    )
    env.add_case(
        "at-cutoff", status="closed", created_at=CUTOFF - timedelta(days=5),
        closed_at=CUTOFF,
    )
    env.add_case(
        "recent", status="closed", created_at=CUTOFF - timedelta(days=5),
        closed_at=CUTOFF + timedelta(seconds=1),
    )
    response = _purge(env)
    assert response.status_code == 200
    assert env.repo.get_case("old") is None
    assert env.repo.get_case("at-cutoff") is not None
    assert env.repo.get_case("recent") is not None
    assert response.json()["deleted"]["handover_cases"] == 1


def test_expired_active_cases_are_closed_and_deleted_with_their_requests(env):
    """R35, R36, R37, R40: casos activos antiguos y sus solicitudes; los del corte se quedan."""
    for status in ("open", "assigned", "timed_out"):
        env.add_case(
            f"old-{status}", status=status, created_at=ACTIVE_CUTOFF - timedelta(days=1),
            advisor_id="111" if status == "assigned" else None,
        )
    env.add_case("boundary", status="open", created_at=ACTIVE_CUTOFF)
    env.add_case("recent", status="open", created_at=ACTIVE_CUTOFF + timedelta(days=1))
    boundary_before = env.repo.get_case("boundary")
    recent_before = env.repo.get_case("recent")

    env.repo.add_request(_request("old-open", NOW))
    env.repo.add_request(_request("old-assigned", NOW))
    env.repo.add_request(_request("boundary", NOW))

    response = _purge(env)
    assert response.status_code == 200
    body = response.json()
    assert body["closed_active_cases"] == 3
    assert body["deleted"]["handover_cases"] == 0
    assert body["deleted"]["handover_requests"] == 2
    for status in ("open", "assigned", "timed_out"):
        assert env.repo.get_case(f"old-{status}") is None
    assert env.repo.get_case("boundary") is not None
    assert env.repo.get_case("recent") is not None
    assert env.repo.get_case("boundary") == boundary_before
    assert env.repo.get_case("recent") == recent_before
    assert {record.requested_case_id for record in env.repo.requests} == {"boundary"}


def test_requests_are_deleted_by_received_at(env):
    """R38: las handover_requests con received_at < corte se borran."""
    env.repo.add_request(_request("old", CUTOFF - timedelta(seconds=1)))
    env.repo.add_request(_request("at", CUTOFF))
    env.repo.add_request(_request("recent", CUTOFF + timedelta(seconds=1)))
    response = _purge(env)
    assert response.json()["deleted"]["handover_requests"] == 1
    assert {record.requested_case_id for record in env.repo.requests} == {"at", "recent"}


def test_notifications_and_denials_are_preserved(env):
    """R39: handover_notifications y handover_denials no se borran, aunque el caso desaparezca."""
    env.add_case(
        "old", status="open", created_at=ACTIVE_CUTOFF - timedelta(days=1),
    )
    env.repo.add_notification("old", "111", "user_request", NOW, True)
    env.repo.add_denial(Denial(case_id="old", advisor_id="222", action="reply", at=NOW))
    _purge(env)
    assert env.repo.get_case("old") is None
    assert len(env.repo.notifications) == 1
    assert len(env.repo.denials) == 1
    [saved] = env.repo.privacy_purge_runs
    assert saved["closed_active_cases"] == 1
    assert saved["counts"] == {"handover_cases": 0, "handover_requests": 0}


class _Cursor:
    def __init__(self, log: list, fail_on: str | None = None) -> None:
        self.log = log
        self.fail_on = fail_on
        self.sql = ""

    def execute(self, sql, params=()):
        self.sql = sql
        self.log.append((sql, tuple(params)))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("fallo simulado")

    def fetchall(self):
        if self.sql.startswith("SELECT case_id FROM handover_cases"):
            return [("old",)]
        if self.sql.startswith("DELETE FROM handover_requests"):
            return [(1,)]
        if self.sql.startswith("DELETE FROM handover_cases"):
            return [("old",)]
        return []


class _Conn:
    def __init__(self, fail_on: str | None = None) -> None:
        self.log: list = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on = fail_on

    def cursor(self):
        return _Cursor(self.log, self.fail_on)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_postgres_purge_rolls_back_when_a_step_fails():
    """R35, R36: un fallo a mitad de la transacción no deja nada parcialmente borrado."""
    conn = _Conn(fail_on="DELETE FROM handover_cases WHERE case_id = ANY")
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    with pytest.raises(RuntimeError):
        repo.purge_personal_data(CUTOFF, ACTIVE_CUTOFF, NOW)
    assert conn.commits == 1
    assert conn.rollbacks == 1


def test_postgres_purge_uses_parameters_and_the_documented_order():
    """R34-R36, R38: SQL parametrizado en el orden del design."""
    conn = _Conn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    counts, closed = repo.purge_personal_data(CUTOFF, ACTIVE_CUTOFF, NOW)
    assert counts == {"handover_cases": 1, "handover_requests": 2}
    assert closed == 1
    assert conn.commits == 2 and conn.rollbacks == 0
    statements = [(sql, params) for sql, params in conn.log if not sql.startswith(("CREATE", "ALTER"))]
    starts = [
        "SELECT case_id FROM handover_cases",
        "DELETE FROM handover_requests WHERE case_id",
        "DELETE FROM handover_cases WHERE case_id",
        "DELETE FROM handover_cases WHERE status",
        "DELETE FROM handover_requests WHERE received_at",
        "INSERT INTO privacy_purge_runs",
    ]
    positions = [
        next(i for i, (sql, _) in enumerate(statements) if sql.startswith(start))
        for start in starts
    ]
    assert positions == sorted(positions)
    for sql, params in statements:
        assert "old" not in sql
        assert sql.count("%s") == len(params)
