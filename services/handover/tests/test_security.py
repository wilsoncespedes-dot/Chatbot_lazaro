"""Seguridad de las rutas de handover: token de servicio y validación del cuerpo."""
from __future__ import annotations

import pytest
from lazaro_contracts import ErrorResponse

HEADERS = {"X-Service-Token": "svc-token"}

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
    ("/cases/check-timeouts", {}),
]

INVALID_BODIES = [
    ("/handover", {**VALID_HANDOVER, "reason": "otro"}),
    ("/handover", {"case_id": "case-1"}),
    ("/cases/case-x/assign", {}),
    ("/cases/case-x/assign", {"advisor_id": ""}),
    ("/cases/case-x/close", {"advisor_id": "111", "extra": 1}),
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
