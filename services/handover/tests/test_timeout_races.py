"""Carreras del vencimiento automático de handover (feature #12)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from handover import domain
from handover.adapters.gateway import FakeGatewayClient
from handover.adapters.repository import FakeCaseRepository

HEADERS = {"X-Service-Token": "svc-token"}
TIMEOUT_REPLY = "Sigue en espera"


class HookGateway(FakeGatewayClient):
    """Ejecuta un gancho una sola vez dentro de `send`, antes de registrar el envío."""

    def __init__(self) -> None:
        super().__init__()
        self.on_send = None
        self._hook_done = False

    def send(self, chat_id: int, text: str) -> None:
        if self.on_send is not None and not self._hook_done:
            self._hook_done = True
            self.on_send()
        super().send(chat_id, text)


class HookRepository(FakeCaseRepository):
    """Ejecuta un gancho una sola vez tras la lectura que abre la ventana de carrera."""

    def __init__(self) -> None:
        super().__init__()
        self.after_list = None
        self.after_find = None
        self._after_list_done = False
        self._after_find_done = False

    def list_open_cases(self):
        cases = super().list_open_cases()
        if self.after_list is not None and not self._after_list_done:
            self._after_list_done = True
            self.after_list()
        return cases

    def find_active_case(self, contact_id: str):
        case = super().find_active_case(contact_id)
        if self.after_find is not None and not self._after_find_done:
            self._after_find_done = True
            self.after_find()
        return case


def _check(env):
    return env.client.post("/cases/check-timeouts", json={}, headers=HEADERS)


def test_check_timeouts_claims_case_before_sending(env_factory):
    """R17: dentro del envío el caso sigue open y ya tiene la reclamación de este reloj."""
    repo = FakeCaseRepository()
    gateway = HookGateway()
    env = env_factory(repo=repo, gateway=gateway)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)
    observed = {}

    def on_send():
        observed["claim"] = repo.timeout_claims.get("case-1")
        observed["status"] = repo.cases["case-1"].status

    gateway.on_send = on_send
    assert _check(env).json() == {"timed_out_cases": ["case-1"]}
    assert observed == {"claim": env.clock(), "status": "open"}


def test_two_simultaneous_check_timeouts_send_once(env_factory):
    """R18: la ejecución anidada no obtiene la reclamación y no vuelve a enviar."""
    gateway = HookGateway()
    env = env_factory(repo=FakeCaseRepository(), gateway=gateway)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)
    nested = {}

    def on_send():
        nested["response"] = domain.check_timeouts(env.settings, env.adapters)

    gateway.on_send = on_send
    response = _check(env)
    assert nested["response"].timed_out_cases == []
    assert response.json() == {"timed_out_cases": ["case-1"]}
    assert env.gateway.sent == [(901, TIMEOUT_REPLY)]
    assert env.repo.cases["case-1"].status == "timed_out"


@pytest.mark.parametrize("rival", ["assigned", "closed"])
def test_check_timeouts_skips_case_assigned_or_closed_before_claim(env_factory, rival):
    """R19: si el caso cambió antes de reclamar no se envía ni se modifica."""
    repo = HookRepository()
    env = env_factory(repo=repo)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)

    def after_list():
        if rival == "assigned":
            domain.assign_case("case-1", "222", env.settings, env.adapters)
        else:
            domain.close_case("case-1", "222", env.settings, env.adapters)

    repo.after_list = after_list
    response = _check(env)
    assert response.json() == {"timed_out_cases": []}
    assert env.gateway.sent == []
    case = env.repo.cases["case-1"]
    if rival == "assigned":
        assert (case.status, case.advisor_id, case.assigned_at) == (
            "assigned",
            "222",
            env.clock(),
        )
    else:
        assert (case.status, case.closed_by, case.closed_at) == (
            "closed",
            "222",
            env.clock(),
        )
    assert "case-1" not in env.repo.timeout_claims


def test_assignment_during_timeout_send_is_kept(env_factory):
    """R20, R21: una asignación durante el envío sobrevive al vencimiento."""
    gateway = HookGateway()
    env = env_factory(repo=FakeCaseRepository(), gateway=gateway)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)
    gateway.on_send = lambda: domain.assign_case(
        "case-1", "222", env.settings, env.adapters
    )

    response = _check(env)
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == (
        "assigned",
        "222",
        env.clock(),
    )
    assert env.gateway.sent == [(901, TIMEOUT_REPLY)]
    assert response.json()["timed_out_cases"] == []


def test_close_during_timeout_send_is_kept(env_factory):
    """R21: un cierre durante el envío no se sobrescribe con timed_out."""
    gateway = HookGateway()
    env = env_factory(repo=FakeCaseRepository(), gateway=gateway)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)
    gateway.on_send = lambda: domain.close_case(
        "case-1", "222", env.settings, env.adapters
    )

    response = _check(env)
    case = env.repo.cases["case-1"]
    assert (case.status, case.closed_by, case.closed_at) == (
        "closed",
        "222",
        env.clock(),
    )
    assert env.gateway.sent == [(901, TIMEOUT_REPLY)]
    assert response.json()["timed_out_cases"] == []


@pytest.mark.parametrize("rival", ["assigned", "closed"])
def test_case_changed_during_send_not_listed(env_factory, rival):
    """R22: un caso que cambió durante el envío no se lista en timed_out_cases."""
    gateway = HookGateway()
    env = env_factory(repo=FakeCaseRepository(), gateway=gateway)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)

    def on_send():
        if rival == "assigned":
            domain.assign_case("case-1", "222", env.settings, env.adapters)
        else:
            domain.close_case("case-1", "222", env.settings, env.adapters)

    gateway.on_send = on_send
    assert _check(env).json() == {"timed_out_cases": []}


def test_send_failure_releases_claim_and_retries_immediately(env_factory):
    """R23: si el aviso falla se libera la reclamación y la siguiente llamada reintenta."""
    env = env_factory(repo=FakeCaseRepository(), gateway=FakeGatewayClient())
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(400)
    env.gateway.fail_for = {901}

    assert _check(env).json() == {"timed_out_cases": []}
    assert "case-1" not in env.repo.timeout_claims
    assert env.repo.cases["case-1"].status == "open"

    env.gateway.fail_for = set()
    assert _check(env).json() == {"timed_out_cases": ["case-1"]}
    assert env.repo.cases["case-1"].status == "timed_out"


def test_stale_claim_is_reclaimed(env_factory):
    """R24, R18: una reclamación vigente bloquea; una caducada se vuelve a reclamar."""
    repo = FakeCaseRepository()
    env = env_factory(repo=repo)
    env.add_case("case-1", status="open", chat_id=901)
    env.clock.advance(300)

    repo.timeout_claims["case-1"] = env.clock() - timedelta(seconds=299)
    assert _check(env).json() == {"timed_out_cases": []}
    assert env.gateway.sent == []
    assert env.repo.cases["case-1"].status == "open"
    assert repo.timeout_claims["case-1"] == env.clock() - timedelta(seconds=299)

    repo.timeout_claims["case-1"] = env.clock() - timedelta(seconds=300)
    assert _check(env).json() == {"timed_out_cases": ["case-1"]}
    assert env.gateway.sent == [(901, TIMEOUT_REPLY)]
    assert env.repo.cases["case-1"].status == "timed_out"


def test_reuse_concurrent_with_assignment_keeps_assignment(env_factory):
    """R25: la reutilización escribe solo last_messages y conserva la asignación."""
    repo = HookRepository()
    env = env_factory(repo=repo)
    env.add_case("case-1", status="open", contact_id="contact-1", chat_id=900)
    repo.after_find = lambda: domain.assign_case(
        "case-1", "222", env.settings, env.adapters
    )

    response = env.handover(
        case_id="case-new",
        contact_id="contact-1",
        last_messages=[{"role": "user", "text": "sigo aquí", "at": "2026-01-02T02:59:00Z"}],
    )
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == (
        "assigned",
        "222",
        env.clock(),
    )
    assert [message.text for message in case.last_messages] == ["sigo aquí"]
    assert "case-new" not in env.repo.cases


def test_no_advisors_reuse_concurrent_with_assignment_keeps_assignment(env_factory):
    """R26: el no_advisors no deshace una asignación hecha tras la lectura."""
    repo = HookRepository()
    env = env_factory(advisors=[], repo=repo)
    env.add_case("case-1", status="open", contact_id="contact-1", chat_id=900)
    repo.after_find = lambda: repo.assign_if_unassigned("case-1", "222", env.clock())

    response = env.handover(case_id="case-new", contact_id="contact-1")
    assert response.json() == {"status": "no_advisors", "case_id": "case-1"}
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == (
        "assigned",
        "222",
        env.clock(),
    )
    assert env.gateway.sent == []
