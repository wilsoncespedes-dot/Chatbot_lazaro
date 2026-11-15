"""Reasignación de casos y vista global desde el panel del supervisor (#49)."""
from __future__ import annotations

from datetime import timedelta
from itertools import count

import pytest

CSRF = "csrf-token"
CASE_ID = "case-1"
_TARGET_SEQ = count(1)


@pytest.fixture()
def env(env_factory):
    return env_factory(
        admin_cookie_secure=False,
        password_hash_iterations=100000,
    )


def _supervisor(env, panel):
    profile = panel.login(env, "supervisor", username="super1", telegram_user_id=900)
    panel.link_case(env, CASE_ID)
    return profile


def _target(env, panel, *, role: str = "asesor", available: bool = True):
    profile = panel.make_profile(
        env,
        f"target{next(_TARGET_SEQ)}",
        role,
        {"asesor": 222, "supervisor": 223}.get(role),
    )
    if available:
        panel.set_presence(env, profile.id, "available")
    return profile


def _post_reassign(env, panel, target_id: str, *, case_id: str = CASE_ID):
    return env.client.post(
        f"/asesor/casos/{case_id}/reasignar",
        data={"csrf_token": panel.CSRF, "target_profile_id": target_id},
        follow_redirects=False,
    )


def _audit(env, action: str):
    return [row for row in env.repo.panel_audit if row.action == action]


# --- R11, R11b, R17: reasignación correcta y auditoría ------------------------


def test_supervisor_reassigns_and_sees_result(env, panel):
    """R11, R11b: usa el profile.id de la sesión, llama a handover y muestra ok."""
    supervisor = _supervisor(env, panel)
    target = _target(env, panel)

    response = _post_reassign(env, panel, target.id)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/todos?ok=reassign"
    assert env.handover.reassigned == [(CASE_ID, supervisor.id, target.id)]
    audit = _audit(env, "reassign")
    assert len(audit) == 1
    assert (audit[0].case_id, audit[0].result) == (CASE_ID, "ok")
    assert audit[0].target == f"from:previous to:{target.id}"


def test_reassignment_requires_available_attending_advisor(env, panel):
    """R14: destino no atendedor o con presencia away responde 4xx sin llamar."""
    _supervisor(env, panel)
    client = _target(env, panel, role="cliente")
    away = _target(env, panel, available=False)

    assert _post_reassign(env, panel, client.id).status_code == 422
    unavailable = _post_reassign(env, panel, away.id)
    assert unavailable.status_code == 409
    assert 'data-code="advisor_unavailable"' in unavailable.text
    assert env.handover.reassigned == []


def test_reassign_to_supervisor_target_is_allowed(env, panel):
    """R6b, R7: un supervisor también es asesor atendedor de destino."""
    _supervisor(env, panel)
    target = _target(env, panel, role="supervisor")

    response = _post_reassign(env, panel, target.id)

    assert response.status_code == 303
    assert env.handover.reassigned[0][2] == target.id


@pytest.mark.parametrize(
    ("attribute", "value", "status", "code"),
    [
        ("reassign_error", "forbidden", 403, "forbidden"),
        ("reassign_error", "not_found", 404, "not_found"),
        ("reassign_error", "case_closed", 409, "case_closed"),
        ("reassign_error", "case_changed", 409, "case_changed"),
        ("reassign_error", "case_not_assigned", 409, "case_not_assigned"),
        ("reassign_error", "validation_error", 422, "validation_error"),
        ("fail_reassign", True, 502, "upstream_error"),
    ],
)
def test_reassign_maps_handover_errors(
    env, panel, attribute, value, status, code
):
    """R11b, R13: los errores de handover se muestran como páginas fijas."""
    _supervisor(env, panel)
    target = _target(env, panel)
    setattr(env.handover, attribute, value)

    response = _post_reassign(env, panel, target.id)

    assert response.status_code == status
    if code == "forbidden":
        assert 'data-code="forbidden"' in response.text
    else:
        assert f'data-code="{code}"' in response.text
    audit = _audit(env, "reassign")
    assert audit and audit[-1].result == code


def test_forbidden_responses_are_uniform(env, panel):
    """R18: un 403 propio y un 403 de handover tienen el mismo contenido."""
    _supervisor(env, panel)
    target = _target(env, panel)
    env.handover.reassign_error = "forbidden"
    denied_by_handover = _post_reassign(env, panel, target.id)

    panel.login(env, "asesor", username="asesor2", telegram_user_id=701)
    denied_by_role = _post_reassign(env, panel, target.id)

    assert denied_by_handover.status_code == denied_by_role.status_code == 403
    assert denied_by_handover.text == denied_by_role.text
    assert CASE_ID not in denied_by_role.text


# --- R8: vista global ---------------------------------------------------------


def test_supervisor_all_cases_view_shows_assignee_and_filters(env, panel):
    """R8: /asesor/todos lista cualquier estado y muestra el asesor asignado."""
    _supervisor(env, panel)
    advisor = _target(env, panel)
    env.handover.case_list = [
        panel.case_item("case-open", "open", created_at=panel.NOW),
        panel.case_item(
            "case-other",
            "assigned",
            ["reassign"],
            created_at=panel.NOW + timedelta(seconds=30),
        ).model_copy(update={"advisor_id": advisor.id}),
        panel.case_item(
            "case-closed",
            "closed",
            ["close"],
            created_at=panel.NOW + timedelta(minutes=1),
        ).model_copy(update={"advisor_id": advisor.id}),
    ]

    response = env.client.get("/asesor/todos")

    assert response.status_code == 200
    assert env.handover.listed_all == ["900"]
    for fragment in (
        "Todos los casos",
        "case-open",
        "case-other",
        "case-closed",
        advisor.username,
        "Asesor",
        "/asesor/casos/case-other/reasignar",
    ):
        assert fragment in response.text
    assert response.text.index("case-open") < response.text.index("case-closed")


def test_all_cases_filters_by_channel_and_assignment(env, panel):
    """R8: la vista global reutiliza los filtros de la bandeja."""
    _supervisor(env, panel)
    panel.link_case(env, "case-tg", channel="telegram", user="10", chat="100")
    panel.link_case(env, "case-wa", channel="whatsapp", user="57300", chat="57301")
    env.handover.case_list = [
        panel.case_item("case-tg", "open"),
        panel.case_item("case-wa", "open"),
    ]

    response = env.client.get("/asesor/todos?canal=whatsapp")

    assert response.status_code == 200
    assert "case-wa" in response.text
    assert "case-tg" not in response.text


# --- R19: métricas en solo lectura -------------------------------------------


def test_supervisor_metrics_are_read_only_and_audited(env, panel):
    """R19: las métricas se muestran sin formularios de modificación y se auditan."""
    _supervisor(env, panel)
    response = env.client.get("/asesor/metricas?dias=7")
    assert response.status_code == 200
    assert "Métricas" in response.text
    assert "Intervalo" in response.text
    for fragment in ("Guardar", "Ajustes", "name=\"dias\""):
        assert fragment not in response.text
    assert any(row.action == "metrics_viewed" for row in env.repo.panel_audit)


@pytest.mark.parametrize("days", ["0", "91", "abc"])
def test_supervisor_metrics_rejects_invalid_days(env, panel, days):
    """R19: días fuera de 1..90 responden 422 antes de consultar métricas."""
    _supervisor(env, panel)
    response = env.client.get(f"/asesor/metricas?dias={days}")
    assert response.status_code == 422
