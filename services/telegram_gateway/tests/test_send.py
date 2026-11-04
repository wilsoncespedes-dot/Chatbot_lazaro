"""Tests de POST /send del telegram_gateway."""
from __future__ import annotations

from lazaro_contracts import ErrorResponse

SERVICE_TOKEN = "svc-token"  # igual que en conftest.py

HEADERS = {"X-Service-Token": SERVICE_TOKEN}


def test_send_ok_returns_sent_true(env):
    """R18"""
    r = env.client.post("/send", json={"chat_id": 9, "text": "hola"}, headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert env.telegram.sent == [(9, "hola")]


def test_send_telegram_failure_returns_502(env):
    """R19"""
    env.telegram.fail = True
    r = env.client.post("/send", json={"chat_id": 9, "text": "hola"}, headers=HEADERS)
    assert r.status_code == 502
    body = r.json()
    ErrorResponse.model_validate(body)
    assert body["error"] == "telegram_error"


def test_send_without_token_returns_401(env):
    """R20"""
    r = env.client.post("/send", json={"chat_id": 9, "text": "hola"})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"
    assert env.telegram.sent == []


def test_send_invalid_body_returns_422(env):
    """R21"""
    r = env.client.post("/send", json={"chat_id": 9}, headers=HEADERS)
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


def test_send_canonical_signed_options_renders_inline_keyboard(env):
    """R38: la ruta /send pinta los botones de consentimiento como teclado."""
    response = env.client.post(
        "/send",
        json={
            "channel": "telegram",
            "destination": "77",
            "blocks": [
                {"type": "text", "text": "Elige"},
                {
                    "type": "options",
                    "options": ["Acepto", "No acepto"],
                    "option_ids": ["privacy.accept", "privacy.reject"],
                    "option_proofs": ["a" * 32, "b" * 32],
                },
            ],
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert env.telegram.reply_markups[-1] == {
        "inline_keyboard": [
            [
                {"text": "Acepto", "callback_data": f"privacy.accept:{'a' * 32}"},
                {"text": "No acepto", "callback_data": f"privacy.reject:{'b' * 32}"},
            ]
        ]
    }
