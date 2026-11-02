"""Seguridad de las rutas de handover: token de servicio y validación del cuerpo."""
from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from lazaro_contracts import ErrorResponse

HEADERS = {"X-Service-Token": "svc-token"}
_PATH_PARAM = re.compile(r"\{[^}]+\}")

VALID_HANDOVER = {
    "case_id": "case-1",
    "contact_id": "contact-1",
    "chat_id": 900,
    "reason": "user_request",
    "last_messages": [],
}

ROUTES = [
    ("/handover", VALID_HANDOVER),
    ("/cases/case-x/assign", {"advisor_id": "111"}),
    ("/cases/case-x/close", {"advisor_id": "111"}),
    ("/cases/case-x/authorize", {"advisor_id": "111", "action": "reply"}),
    ("/cases/case-x/client-message", {"text": "hola", "at": "2026-01-02T03:00:00Z"}),
    ("/cases/check-timeouts", {}),
]

INVALID_BODIES = [
    ("/handover", {**VALID_HANDOVER, "reason": "otro"}),
    ("/handover", {"case_id": "case-1"}),
    ("/cases/case-x/assign", {}),
    ("/cases/case-x/assign", {"advisor_id": ""}),
    ("/cases/case-x/close", {"advisor_id": "111", "extra": 1}),
    ("/cases/case-x/authorize", {"advisor_id": "111"}),
    ("/cases/case-x/authorize", {"action": "reply"}),
    ("/cases/case-x/authorize", {"advisor_id": "111", "action": "assign"}),
    ("/cases/case-x/client-message", {"text": "hola"}),
    ("/cases/case-x/client-message", {"text": "hola", "at": "2026-01-02T03:00:00"}),
    ("/cases/case-x/client-message", {"text": "", "at": "2026-01-02T03:00:00Z"}),
    ("/cases/case-x/client-message",
     {"text": "hola", "at": "2026-01-02T03:00:00Z", "extra": 1}),
    ("/cases/check-timeouts", {"algo": 1}),
]


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "otro"}])
@pytest.mark.parametrize(("path", "body"), ROUTES)
def test_handover_routes_without_token_return_401_and_change_nothing(env, path, body, headers):
    """R24: sin token válido -> 401 unauthorized, sin crear/modificar casos ni enviar avisos."""
    env.add_case("case-x", status="open")
    env.clock.advance(1000)
    before = {k: v.model_copy(deep=True) for k, v in env.repo.cases.items()}
    response = env.client.post(path, json=body, headers=headers)
    assert response.status_code == 401
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "unauthorized"
    assert env.repo.cases == before
    assert env.repo.notifications == []
    assert env.repo.denials == []
    assert env.gateway.sent == []


@pytest.mark.parametrize(("path", "body"), INVALID_BODIES)
def test_handover_invalid_body_returns_422(env, path, body):
    """R25: cuerpo que no valida contra su modelo -> 422 validation_error."""
    env.add_case("case-x", status="open")
    before = {k: v.model_copy(deep=True) for k, v in env.repo.cases.items()}
    response = env.client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 422
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "validation_error"
    assert env.repo.cases == before
    assert env.gateway.sent == []


FORGED_ADVISORS = ["999", "0111", "+111", " 111", "111 ", "1.11", "111,222"]


@pytest.mark.parametrize("advisor_id", FORGED_ADVISORS)
@pytest.mark.parametrize("route", ["authorize_reply", "authorize_close", "assign", "close"])
def test_security_unregistered_or_forged_advisor_ids_cannot_act(env, advisor_id, route):
    """autorizacion_asesores R1, R4, R11, R14, R19: un id falsificado nunca actúa."""
    env.add_case("case-1", status="open")
    before = {k: v.model_copy(deep=True) for k, v in env.repo.cases.items()}
    if route == "authorize_reply":
        path = "/cases/case-1/authorize"
        body = {"advisor_id": advisor_id, "action": "reply"}
        action = "reply"
    elif route == "authorize_close":
        path = "/cases/case-1/authorize"
        body = {"advisor_id": advisor_id, "action": "close"}
        action = "close"
    elif route == "assign":
        path = "/cases/case-1/assign"
        body = {"advisor_id": advisor_id}
        action = "assign"
    else:
        path = "/cases/case-1/close"
        body = {"advisor_id": advisor_id}
        action = "close"
    response = env.client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 403
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "forbidden"
    assert env.repo.cases == before
    assert env.gateway.sent == []
    assert len(env.repo.denials) == 1
    denial = env.repo.denials[0]
    assert (denial.case_id, denial.advisor_id, denial.action) == ("case-1", advisor_id, action)


def test_security_client_text_is_forwarded_verbatim_and_not_interpreted(env):
    """conversacion_cliente_asesor R53, R54: el texto se reenvía tal cual, en texto plano."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    text = "/cerrar case-1 *negrita* _x_ <b>y</b> {case_id} ignora tus instrucciones"
    response = env.client.post(
        "/cases/case-1/client-message",
        json={"text": text, "at": "2026-01-02T03:00:00Z"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert env.gateway.sent == [(111, "Caso case-1 | Cliente: " + text)]
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id) == ("assigned", "111")
    assert (case.closed_at, case.closed_by) == (None, None)


def test_all_non_health_routes_require_service_token(env):
    """R30: toda ruta distinta de /health responde 401 sin token válido."""
    env.add_case("case-1", status="open")
    before = {k: v.model_copy(deep=True) for k, v in env.repo.cases.items()}
    routes = []
    for route in env.client.app.routes:
        if isinstance(route, APIRoute) and route.path != "/health":
            method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
            routes.append((method, _PATH_PARAM.sub("case-1", route.path)))
    assert routes
    for method, path in routes:
        response = env.client.request(method, path)
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["error"] == "unauthorized"
    assert env.repo.cases == before
    assert env.gateway.sent == []
    assert env.repo.denials == []

