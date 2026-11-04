"""Cola y ejecución de supresiones desde el panel (#41)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from lazaro_contracts import TemplateBlock

from orchestrator.adapters.repository import StoredSuppressionRequest


def _post(env, path: str, data: dict):
    return env.client.post(path, data=data, follow_redirects=False)


def _client(env, panel, username: str = "cliente1"):
    return env.repo.create_profile(username, "cliente", "hash", panel.NOW)


def _request(env, panel, request_id: str, contact, channel: str = "telegram",
             created_at=None, profile_id: str = "cliente-1"):
    request_id, _ = env.repo.create_or_get_pending_suppression(
        request_id,
        profile_id,
        contact.id,
        channel,
        created_at or panel.NOW,
    )
    return request_id


def _executed_request(env, panel, request_id: str, executed_at):
    env.repo.suppression_requests[request_id] = StoredSuppressionRequest(
        id=request_id,
        profile_id="cliente-1",
        contact_id="c1",
        channel="telegram",
        status="executed",
        case_id=None,
        created_at=panel.NOW - timedelta(days=1),
        executed_at=executed_at,
        executed_by=None,
        removed_counts={"messages": 1},
    )


def test_admin_queue_shows_pending_with_priority(env_factory, panel):
    """R60, R63-R65: la cola admin muestra la solicitud y su prioridad."""
    env = env_factory()
    panel.login_admin(env)
    client = _client(env, panel)
    contact = panel.link_case(env)
    _request(
        env, panel, "req-1", contact, created_at=panel.NOW - timedelta(days=60),
        profile_id=client.id,
    )

    response = env.client.get("/admin/supresiones")

    assert response.status_code == 200
    for text in ("req-1", client.username, "telegram", "vencida", "Pendiente"):
        assert text in response.text


def test_asesor_queue_requires_executor_role(env_factory, panel):
    """R60, R61: el asesor solo ve la cola si está en SUPPRESSION_EXECUTOR_ROLES."""
    env = env_factory(suppression_executor_roles="admin,asesor")
    panel.login(env)
    assert env.client.get("/asesor/supresiones").status_code == 200

    env2 = env_factory(suppression_executor_roles="admin")
    panel.login(env2)
    response = env2.client.get("/asesor/supresiones")
    assert response.status_code == 403
    assert 'data-code="forbidden"' in response.text


def test_queue_orders_pending_by_deadline_and_limits_executed(env_factory, panel):
    """R62: pendientes por fecha límite y ejecutadas limitadas."""
    env = env_factory(suppression_queue_executed_limit=1)
    panel.login_admin(env)
    contact = panel.link_case(env)
    _request(
        env, panel, "req-old", contact, created_at=panel.NOW - timedelta(days=60),
        profile_id="cliente-a",
    )
    _request(env, panel, "req-new", contact, created_at=panel.NOW, profile_id="cliente-b")
    _executed_request(env, panel, "exec-old", panel.NOW - timedelta(days=2))
    _executed_request(env, panel, "exec-new", panel.NOW - timedelta(days=1))

    response = env.client.get("/admin/supresiones")

    assert response.status_code == 200
    assert response.text.index("req-old") < response.text.index("req-new")
    assert "exec-new" in response.text
    assert "exec-old" not in response.text


def test_execute_telegram_saves_note_and_sends_text(env_factory, panel):
    """R66, R68, R69: ejecuta, guarda la nota y avisa por Telegram como texto."""
    env = env_factory()
    panel.login_admin(env)
    client = _client(env, panel)
    contact = panel.link_case(env)
    _request(env, panel, "req-1", contact, profile_id=client.id)

    response = _post(
        env,
        "/admin/supresiones/req-1/execute",
        {"csrf_token": panel.CSRF, "note": "Revisado por soporte"},
    )

    assert response.status_code == 303
    request = env.repo.suppression_requests["req-1"]
    assert request.status == "executed"
    assert request.result_note == "Revisado por soporte"
    assert request.notification_result == "text"
    assert (contact.chat_id, env.settings.suppression_done_reply) in env.gateway.sent
    assert all(
        message.text != env.settings.suppression_done_reply
        for message in env.repo.messages
    )
    assert client.role == "cliente"


def test_execute_whatsapp_open_uses_text_and_closed_uses_template(env_factory, panel):
    """R68: WhatsApp abierta usa texto; cerrada usa TemplateBlock."""
    env = env_factory()
    panel.login_admin(env)
    client = _client(env, panel)
    contact = panel.link_case(env, channel="whatsapp", user="57300", chat="57301",
                        profile_id=client.id)
    panel.add_message(env, contact, "user", "hola", panel.NOW - timedelta(hours=1))
    _request(env, panel, "req-open", contact, channel="whatsapp", profile_id=client.id)

    _post(env, "/admin/supresiones/req-open/execute", {"csrf_token": panel.CSRF})
    assert env.repo.suppression_requests["req-open"].notification_result == "text"
    assert ("whatsapp", "57301", env.settings.suppression_done_reply) in env.gateway.channel_sent

    env2 = env_factory()
    panel.login_admin(env2)
    client2 = _client(env2, panel, "cliente2")
    contact2 = panel.link_case(env2, channel="whatsapp", user="57302", chat="57303",
                         profile_id=client2.id)
    _request(env2, panel, "req-closed", contact2, channel="whatsapp", profile_id=client2.id)
    _post(env2, "/admin/supresiones/req-closed/execute", {"csrf_token": panel.CSRF})
    request2 = env2.repo.suppression_requests["req-closed"]
    assert request2.notification_result == "template"
    assert isinstance(env2.gateway.blocks_sent[0][2][0], TemplateBlock)


def test_notice_failure_and_missing_contact_are_recorded(env_factory, panel):
    """R69: fallo de aviso -> failed; contacto inexistente -> skipped."""
    env = env_factory()
    panel.login_admin(env)
    client = _client(env, panel)
    contact = panel.link_case(env)
    _request(env, panel, "req-1", contact, profile_id=client.id)
    env.gateway.fail = True
    _post(env, "/admin/supresiones/req-1/execute", {"csrf_token": panel.CSRF})
    assert env.repo.suppression_requests["req-1"].notification_result == "failed"

    env2 = env_factory()
    panel.login_admin(env2)
    _request(env2, panel, "req-2", type("C", (), {"id": "no-existe"})())
    _post(env2, "/admin/supresiones/req-2/execute", {"csrf_token": panel.CSRF})
    assert env2.repo.suppression_requests["req-2"].notification_result == "skipped"


def test_long_note_is_422_without_executing(env_factory, panel):
    """R67: una nota de más de 500 caracteres no ejecuta la supresión."""
    env = env_factory()
    panel.login_admin(env)
    client = _client(env, panel)
    contact = panel.link_case(env)
    _request(env, panel, "req-1", contact, profile_id=client.id)
    response = _post(
        env,
        "/admin/supresiones/req-1/execute",
        {"csrf_token": panel.CSRF, "note": "x" * 501},
    )
    assert response.status_code == 422
    assert env.repo.suppression_requests["req-1"].status == "pending"


@pytest.mark.parametrize(
    ("setup", "status", "code", "path"),
    [
        ("missing", 404, "not_found", "/admin/supresiones/no-existe/execute"),
        ("executed", 409, "suppression_not_pending", "/admin/supresiones/req-1/execute"),
        ("forbidden", 403, "forbidden", "/asesor/supresiones/req-1/execute"),
    ],
)
def test_execution_errors_do_not_notify(env_factory, setup, status, code, path, panel):
    """R70: 404/409/403 no envían avisos y responden su página de error."""
    if setup == "forbidden":
        env = env_factory(suppression_executor_roles="admin")
        panel.login(env)
        client = _client(env, panel)
        contact = panel.link_case(env)
        _request(env, panel, "req-1", contact, profile_id=client.id)
    else:
        env = env_factory()
        panel.login_admin(env)
        client = _client(env, panel)
        contact = panel.link_case(env)
        _request(env, panel, "req-1", contact, profile_id=client.id)
        if setup == "executed":
            env.repo.suppression_requests["req-1"].status = "executed"
    response = _post(env, path, {"csrf_token": panel.CSRF})
    assert response.status_code == status
    if setup == "forbidden":
        assert f'data-code="{code}"' in response.text
    assert env.gateway.sent == []
    assert env.gateway.blocks_sent == []


def test_execute_without_csrf_is_forbidden(env_factory, panel):
    """R66: sin CSRF no se ejecuta la supresión."""
    env = env_factory()
    panel.login_admin(env)
    client = _client(env, panel)
    contact = panel.link_case(env)
    _request(env, panel, "req-1", contact, profile_id=client.id)
    response = env.client.post("/admin/supresiones/req-1/execute", data={})
    assert response.status_code == 403
    assert env.repo.suppression_requests["req-1"].status == "pending"
