"""Tests de POST /cases/check-timeouts con reloj falso."""
from __future__ import annotations

import inspect
import logging
from datetime import timedelta
from pathlib import Path

from lazaro_contracts import CheckTimeoutsResponse

from handover import domain

HEADERS = {"X-Service-Token": "svc-token"}
TIMEOUT_REPLY = "Sigue en espera"
PKG = Path(__file__).resolve().parents[1] / "handover"


def _check(env):
    return env.client.post("/cases/check-timeouts", json={}, headers=HEADERS)


def test_check_timeouts_notifies_client_and_marks_timed_out(env):
    """R17, R21, R22: un caso open con antigüedad >= timeout recibe el aviso y pasa a timed_out."""
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)
    response = _check(env)
    assert response.status_code == 200
    assert response.json() == {"timed_out_cases": ["case-1"]}
    CheckTimeoutsResponse.model_validate(response.json())
    assert env.gateway.sent == [(901, TIMEOUT_REPLY)]
    assert env.repo.cases["case-1"].status == "timed_out"


def test_check_timeouts_ignores_assigned_closed_and_recent_cases(env):
    """R18, R22: assigned, closed, timed_out y open recientes no se tocan."""
    env.add_case("assigned", status="assigned", advisor_id="111")
    env.add_case("closed", status="closed")
    env.add_case("timed", status="timed_out")
    env.clock.advance(1000)
    env.add_case("recent", status="open", created_at=env.clock() - timedelta(seconds=299))
    before = {k: v.model_copy(deep=True) for k, v in env.repo.cases.items()}
    response = _check(env)
    assert response.json() == {"timed_out_cases": []}
    assert env.gateway.sent == []
    assert env.repo.cases == before


def test_check_timeouts_uses_injected_clock(env):
    """R22: la antigüedad depende solo del reloj inyectado."""
    env.add_case("case-1", status="open")
    env.clock.advance(299)
    assert _check(env).json() == {"timed_out_cases": []}
    env.clock.advance(1)
    assert _check(env).json() == {"timed_out_cases": ["case-1"]}
    source = inspect.getsource(domain)
    assert "datetime.now" not in source and "time.time" not in source


def test_check_timeouts_send_failure_keeps_case_open(env, caplog):
    """R19: si el aviso falla, el caso sigue open, no se lista y se reintenta luego."""
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(400)
    env.gateway.fail_for = {901}
    caplog.set_level(logging.DEBUG)
    assert _check(env).json() == {"timed_out_cases": []}
    assert env.repo.cases["case-1"].status == "open"
    assert "case-1" in caplog.text and TIMEOUT_REPLY not in caplog.text
    env.gateway.fail_for = set()
    assert _check(env).json() == {"timed_out_cases": ["case-1"]}


def test_check_timeouts_continues_after_failure(env):
    """R20: un fallo en un caso no impide procesar los demás vencidos."""
    env.add_case("case-1", status="open", chat_id=901)
    env.add_case("case-2", status="open", chat_id=902)
    env.add_case("case-3", status="open", chat_id=903)
    env.clock.advance(301)
    env.gateway.fail_for = {902}
    response = _check(env)
    assert response.json() == {"timed_out_cases": ["case-1", "case-3"]}
    assert env.gateway.sent == [(901, TIMEOUT_REPLY), (903, TIMEOUT_REPLY)]
    assert env.repo.cases["case-2"].status == "open"


def test_check_timeouts_returns_empty_list_when_none_expired(env):
    """R21: sin casos vencidos responde lista vacía."""
    assert _check(env).json() == {"timed_out_cases": []}
    env.add_case("case-1", status="open")
    assert _check(env).json() == {"timed_out_cases": []}
    assert env.gateway.sent == []


def test_package_never_reads_wall_clock_outside_main():
    """R22: solo main.py (build_default_adapters) lee la hora real."""
    for path in PKG.rglob("*.py"):
        if path.name == "main.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "datetime.now" not in text and "utcnow" not in text, path
