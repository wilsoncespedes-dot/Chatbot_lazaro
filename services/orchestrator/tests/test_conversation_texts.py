"""Textos del flujo administrados por el panel (#37, R19-R21, R25, R32, R33)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import NormalizedMessage

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.config import Settings
from orchestrator.domain import Adapters, consent_configured, process_channel_message
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token-centinela"
PASSWORD = "clave-segura-123"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    settings: Settings
    adapters: Adapters
    gateway: FakeGatewayClient
    clock: list[datetime] = field(default_factory=lambda: [FIXED_NOW])


@pytest.fixture()
def env() -> Env:
    settings = Settings(
        service_token=SERVICE_TOKEN,
        password_hash_iterations=100000,
        admin_cookie_secure=False,
        admin_session_ttl_minutes=60,
        admin_login_max_attempts=3,
        admin_login_window_minutes=15,
        admin_trust_proxy_headers=False,
        privacy_notice_text=(
            "Aviso base. Acepto el tratamiento de mis datos."
        ),
        privacy_notice_version="v1",
        privacy_accept_phrase="Acepto el tratamiento de mis datos.",
        privacy_accepted_reply="Gracias.",
        privacy_retention_days="30",
    )
    clock = [FIXED_NOW]
    repo = FakeRepository()
    gateway = FakeGatewayClient()
    adapters = Adapters(
        repository=repo,
        rag=FakeRagClient(),
        llm=FakeLLM(reply=""),
        gateway=gateway,
        handover=FakeHandoverClient(),
        db_query=FakeDbQuery(),
        clock=lambda: clock[0],
        new_id=lambda: "generated-id",
    )
    client = TestClient(create_app(settings, adapters))
    return Env(client, repo, settings, adapters, gateway, clock)


def _create_admin_and_login(env: Env) -> None:
    created = env.client.post(
        "/profiles",
        json={"username": "admin1", "role": "admin", "password": PASSWORD},
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    assert created.status_code == 201
    response = env.client.post(
        "/admin/login",
        data={"username": "admin1", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _csrf(env: Env, path: str = "/admin/texts") -> str:
    page = env.client.get(path)
    assert page.status_code == 200
    match = CSRF_RE.search(page.text)
    assert match is not None
    return match.group(1)


def _texts_form(csrf: str, **changes) -> dict[str, str]:
    values = {
        "csrf_token": csrf,
        "notice_text": "Aviso del panel",
        "notice_version": "v-panel",
        "greeting": "Saludo del panel",
        "accepted_reply": "Aceptado del panel",
        "rejected_reply": "Cerrado del panel",
        "login_reminder": "Login del panel",
        "suspended_reply": "Suspendido del panel",
        "unsupported_reply": "Solo texto del panel",
        "active_welcome": "Bienvenida del panel",
        "confirm_button_reply": "Botón del panel",
        "login_link_label": "Enlace de acceso del panel",
        "session_closed_reply": "Sesión cerrada del panel",
    }
    values.update(changes)
    return values


def _message(kind: str = "text", text: str | None = "hola") -> NormalizedMessage:
    return NormalizedMessage(
        channel="telegram",
        external_user_id="10",
        external_chat_id="100",
        external_message_id="m1",
        kind=kind,  # type: ignore[arg-type]
        text=text,
        button_id=None,
        received_at=FIXED_NOW,
    )


def test_texts_page_requires_admin_session(env):
    """R19: la pantalla de textos exige sesión admin como el resto del panel."""
    response = env.client.get("/admin/texts", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_saves_texts_and_version_together(env):
    """R19, R20: el panel persiste texto legal y versión en la configuración existente."""
    _create_admin_and_login(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/texts", data=_texts_form(csrf), follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/texts"
    stored = env.repo.conversation_texts
    assert stored.notice_text == "Aviso del panel"
    assert stored.notice_version == "v-panel"
    assert stored.greeting == "Saludo del panel"
    assert stored.unsupported_reply == "Solo texto del panel"
    assert stored.login_link_label == "Enlace de acceso del panel"
    assert stored.session_closed_reply == "Sesión cerrada del panel"


def test_identity_texts_do_not_gate_the_consent_flow(env):
    """R9: `login_link_label` y `session_closed_reply` no entran en `consent_configured`."""
    env.repo.save_conversation_texts(
        replace(
            env.repo.get_conversation_texts(),
            notice_text="Aviso del panel",
            notice_version="v-panel",
            greeting="Saludo del panel",
            accepted_reply="Aceptado del panel",
            rejected_reply="Cerrado del panel",
            login_reminder="Login del panel",
            suspended_reply="Suspendido del panel",
            unsupported_reply="Solo texto del panel",
            confirm_button_reply="Botón del panel",
            login_link_label="",
            session_closed_reply="",
        ),
        "admin-1",
        FIXED_NOW,
    )

    assert consent_configured(env.settings, env.adapters) is True


def test_saved_texts_are_used_without_restart(env):
    """R21, R32: el siguiente mensaje lee el texto guardado, sin reiniciar."""
    _create_admin_and_login(env)
    csrf = _csrf(env)
    env.client.post("/admin/texts", data=_texts_form(csrf), follow_redirects=False)

    process_channel_message(_message(), env.settings, env.adapters)

    prompt = env.gateway.channel_sent[-1][2]
    assert "Saludo del panel" in prompt
    assert "Aviso del panel" in prompt
    assert env.settings.privacy_notice_text not in prompt


def test_texts_post_requires_csrf(env):
    """R19: sin CSRF no se guarda nada."""
    _create_admin_and_login(env)
    before = env.repo.conversation_texts

    response = env.client.post(
        "/admin/texts",
        data=_texts_form("token-equivocado"),
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert env.repo.conversation_texts == before


def test_legal_text_and_version_are_required(env):
    """R20, R25, R33: sin texto legal o versión se rechaza y no se inventa nada."""
    _create_admin_and_login(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/texts",
        data=_texts_form(csrf, notice_text="", notice_version=""),
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert env.repo.conversation_texts.notice_text == ""
    assert env.repo.conversation_texts.notice_version == ""


def test_unsupported_reply_comes_from_the_panel(env):
    """R15, R21, R30: el texto de contenido no textual se lee del panel y no usa LLM."""
    _create_admin_and_login(env)
    csrf = _csrf(env)
    env.client.post(
        "/admin/texts",
        data=_texts_form(csrf, unsupported_reply="Texto no soportado del panel"),
        follow_redirects=False,
    )

    process_channel_message(_message(kind="unsupported"), env.settings, env.adapters)

    assert env.gateway.sent[-1] == (100, "Texto no soportado del panel")
    assert env.adapters.llm.calls == []
    assert env.repo.messages == []
    assert env.repo.conversation_states == {}


def test_version_change_from_panel_forces_new_acceptance(env):
    """R7, R20: publicar una versión nueva invalida la aceptación anterior."""
    env.repo.add_channel_privacy_consent(
        "telegram", "10", "v1", "sha", FIXED_NOW
    )
    _create_admin_and_login(env)
    csrf = _csrf(env)
    env.client.post(
        "/admin/texts",
        data=_texts_form(csrf, notice_version="v2"),
        follow_redirects=False,
    )

    process_channel_message(_message(), env.settings, env.adapters)

    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert "Aviso del panel" in env.gateway.channel_sent[-1][2]
