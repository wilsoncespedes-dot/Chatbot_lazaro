"""Asignación automática de casos por carga en el orquestador (feature #52)."""
from __future__ import annotations

from pathlib import Path

import pytest
from lazaro_contracts import CaseListItem, HandoverResponse

from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.config import Settings
from orchestrator.domain import operational_settings

CSRF = "csrf-token"
ACK = "Avisé a un asesor; te responderá por aquí en cuanto pueda."
ROOT = Path(__file__).resolve().parents[3]


def _set_mode(
    env,
    mode: str,
    *,
    enabled: bool | None = None,
) -> None:
    values = {"assignment.mode": mode}
    if enabled is not None:
        values["business_hours.enabled"] = "true" if enabled else "false"
    env.repo.save_app_settings(values, [])


def _advisor(env, panel, telegram_user_id: int, role: str = "asesor", name: str = "asesor"):
    profile = panel.make_profile(env, name, role, telegram_user_id=telegram_user_id)
    panel.set_presence(env, profile.id, "available")
    return profile


def _escalate(env, update_id: int = 1):
    return env.post(text="quiero un asesor", update_id=update_id)


def _events(env, event_type: str):
    return [reason for kind, reason in env.events() if kind == event_type]


@pytest.fixture()
def admin_env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def _save_mode(env, mode: str):
    return env.client.post(
        "/admin/ajustes",
        data={"csrf_token": CSRF, "assignment.mode": mode},
        follow_redirects=False,
    )


# --- R2, R5: modo manual por defecto ------------------------------------------------


def test_default_mode_is_manual(env):
    """R2: sin valor guardado ni entorno, el modo efectivo es manual."""
    assert Settings().assignment_mode == "manual"
    assert env.settings.assignment_mode == "manual"
    assert operational_settings(env.settings, env.adapters).assignment_mode == "manual"
    assert "ASSIGNMENT_MODE=manual" in (ROOT / ".env.example").read_text(
        encoding="utf-8"
    )


def test_mode_manual_does_not_auto_assign(env, panel):
    """R5: en modo manual el escalamiento no invoca la asignación automática."""
    _advisor(env, panel, 701)
    _set_mode(env, "manual")

    response = _escalate(env)

    assert response.status_code == 202
    assert len(env.handover.requests) == 1
    assert env.handover.auto_assigned == []
    assert _events(env, "auto_assigned") == []


# --- R1, R3, R4: ajuste del panel --------------------------------------------------


def test_admin_sets_assignment_mode_applies_without_restart_and_audited(
    admin_env, panel
):
    """R1, R3: el panel guarda el modo, se aplica en el siguiente escalamiento y audita."""
    _advisor(admin_env, panel, 701)

    response = _save_mode(admin_env, "automatica")

    assert response.status_code == 303
    assert operational_settings(admin_env.settings, admin_env.adapters).assignment_mode == (
        "automatica"
    )
    audit = [
        row
        for row in admin_env.repo.panel_audit
        if row.action == "settings_update"
    ]
    assert any(row.target == "assignment.mode" and row.result == "ok" for row in audit)

    _escalate(admin_env)
    assert len(admin_env.handover.auto_assigned) == 1


def test_invalid_assignment_mode_422(admin_env):
    """R4: un modo fuera de la lista responde 422 y no cambia el valor guardado."""
    assert _save_mode(admin_env, "manual").status_code == 303
    response = _save_mode(admin_env, "round_robin")

    assert response.status_code == 422
    stored = admin_env.repo.get_app_settings(("assignment.",))
    assert stored["assignment.mode"] == "manual"


def test_settings_page_offers_assignment_mode(admin_env):
    """R1: /admin/ajustes ofrece el ajuste con sus dos valores."""
    page = admin_env.client.get("/admin/ajustes")
    assert page.status_code == 200
    assert "assignment.mode" in page.text
    assert 'value="manual"' in page.text
    assert 'value="automatica"' in page.text


# --- R6, R10, R12: reparto, cola y fallo -------------------------------------------


def test_automatic_mode_requests_assignment_with_available_advisors(env, panel):
    """R6: envía solo los perfiles atendedores con presencia available."""
    _advisor(env, panel, 701, name="asesor1")
    away = panel.make_profile(env, "asesor2", "asesor", telegram_user_id=702)
    panel.set_presence(env, away.id, "away")
    _advisor(env, panel, 703, role="supervisor", name="super1")
    panel.make_profile(env, "admin1", "admin", telegram_user_id=704)
    _set_mode(env, "automatica")

    response = _escalate(env)

    assert response.status_code == 202
    assert len(env.handover.auto_assigned) == 1
    case_id, candidates = env.handover.auto_assigned[0]
    assert case_id == "case-1"
    assert candidates == ("701", "703")
    assert _events(env, "auto_assigned") == ["case:case-1 advisor:701 reason:auto"]


def test_no_available_advisors_leaves_case_queued(env, panel):
    """R10: sin asesores disponibles no se llama y el caso sigue en cola."""
    profile = panel.make_profile(env, "asesor1", "asesor", telegram_user_id=701)
    panel.set_presence(env, profile.id, "away")
    _set_mode(env, "automatica")

    _escalate(env)

    assert len(env.handover.requests) == 1
    assert env.handover.auto_assigned == []
    assert _events(env, "auto_assigned") == []
    assert ACK in [text for _, text in env.gateway.sent]


def test_auto_assign_failure_keeps_case_queued(env, panel):
    """R12: un fallo de handover deja el caso en cola y registra auto_assign_failed."""
    _advisor(env, panel, 701)
    _set_mode(env, "automatica")
    env.handover.fail_auto_assign = True

    response = _escalate(env)

    assert response.status_code == 202
    assert len(env.handover.auto_assigned) == 1
    assert _events(env, "auto_assign_failed") == ["case:case-1"]
    assert _events(env, "auto_assigned") == []
    assert ACK in [text for _, text in env.gateway.sent]


# --- R16, R17, R18: exclusiones ----------------------------------------------------


def test_suppression_case_not_auto_assigned(env, panel):
    """R16: un caso creado por la herramienta de supresión no se asigna solo."""
    _advisor(env, panel, 701)
    _set_mode(env, "automatica")

    response = env.post(text="borrar mis datos", update_id=1)

    assert response.status_code == 202
    assert len(env.handover.requests) == 1
    assert env.handover.auto_assigned == []
    assert _events(env, "auto_assigned") == []


def test_out_of_hours_case_not_auto_assigned(env, panel):
    """R17: fuera del horario de atención el caso sigue en cola con su aviso."""
    _advisor(env, panel, 701)
    _set_mode(env, "automatica", enabled=True)

    _escalate(env)

    assert len(env.handover.requests) == 1
    assert env.handover.auto_assigned == []
    assert _events(env, "out_of_hours") == ["queued"]


class _ReusingHandover(FakeHandoverClient):
    """Simula la reutilización del caso activo que hace handover."""

    def request(self, req):  # type: ignore[override]
        self.requests.append(req)
        return HandoverResponse(status=self.status, case_id="case-reused")


def test_reescalation_does_not_reassign(env, panel):
    """R18: un caso reutilizado ya asignado no se vuelve a asignar (skipped)."""
    _advisor(env, panel, 701)
    _set_mode(env, "automatica")
    reusing = _ReusingHandover()
    env.adapters.handover = reusing

    _escalate(env, update_id=1)
    assert _events(env, "auto_assigned") == ["case:case-reused advisor:701 reason:auto"]

    reusing.auto_assign_status = "skipped"
    _escalate(env, update_id=2)

    assert [case_id for case_id, _ in reusing.auto_assigned] == [
        "case-reused",
        "case-reused",
    ]
    assert _events(env, "auto_assigned") == ["case:case-reused advisor:701 reason:auto"]
    assert env.repo.get_contact_last_case(env.repo.contacts[10].id) == "case-reused"


# --- R20, R21, R22: registro, bandeja y reasignación -------------------------------


def test_auto_assigned_event_logged_without_text(env, panel):
    """R20: el evento auto_assigned lleva caso, asesor y motivo, sin texto del cliente."""
    _advisor(env, panel, 701)
    _set_mode(env, "automatica")
    _escalate(env, update_id=1)

    [reason] = _events(env, "auto_assigned")
    assert reason == "case:case-1 advisor:701 reason:auto"
    assert "quiero un asesor" not in reason


def test_auto_assigned_case_in_advisor_inbox(env, panel):
    """R21: la bandeja del asesor muestra el caso asignado automáticamente."""
    panel.login(env, "asesor", username="asesor1", telegram_user_id=701)
    panel.set_presence(env, "701", "available")
    _set_mode(env, "automatica")
    _escalate(env)
    env.handover.case_list = [
        CaseListItem(
            case_id="case-1",
            status="assigned",
            created_at=env.adapters.clock(),
            actions=["reply", "close"],
            advisor_id="701",
        )
    ]

    response = env.client.get("/asesor/cases")

    assert response.status_code == 200
    assert "case-1" in response.text
    assert "Mío" in response.text


def test_supervisor_can_reassign_auto_assigned_case(env, panel):
    """R22: la reasignación existente del supervisor funciona sobre un caso auto."""
    panel.login(env, "supervisor", username="super1", telegram_user_id=900)
    panel.link_case(env, "case-1")
    _advisor(env, panel, 701, name="asesor1")
    target = _advisor(env, panel, 702, name="asesor2")
    _set_mode(env, "automatica")
    _escalate(env)
    assert len(env.handover.auto_assigned) == 1

    response = env.client.post(
        "/asesor/casos/case-1/reasignar",
        data={"csrf_token": CSRF, "target_profile_id": target.id},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert env.handover.reassigned == [("case-1", "900", "702")]


# --- R23: la cola no se reparte sola -----------------------------------------------


def test_advisor_becoming_available_does_not_assign_queued_case(env, panel):
    """R23: un caso que quedó en cola no se asigna al volver la disponibilidad."""
    profile = panel.make_profile(env, "asesor1", "asesor", telegram_user_id=701)
    panel.set_presence(env, profile.id, "away")
    _set_mode(env, "automatica")
    _escalate(env)
    assert env.handover.auto_assigned == []

    panel.set_presence(env, profile.id, "available")

    assert env.handover.auto_assigned == []
    assert _events(env, "auto_assigned") == []
