"""Fragmentos HTML del panel en vivo (#53)."""
from __future__ import annotations

from datetime import timedelta


def test_live_inbox_requires_session(env_factory):
    """R26: sin sesión válida el fragmento redirige al login igual que el panel."""
    env = env_factory()
    response = env.client.get("/asesor/live/inbox", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"


def test_live_inbox_matches_inbox_table_and_filters(env_factory, panel):
    """R23: misma tabla y mismos filtros que la bandeja habitual."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-tg", created_at=panel.NOW)
    panel.link_case(env, "case-wa", channel="whatsapp", user="57300", chat="57301")
    env.handover.case_list = [
        panel.case_item("case-tg", "open", created_at=panel.NOW),
        panel.case_item(
            "case-wa", "assigned", ["reply", "close"], created_at=panel.NOW
        ),
    ]

    response = env.client.get(
        "/asesor/live/inbox?canal=whatsapp&asignacion=mias"
    )

    assert response.status_code == 200
    assert response.text.strip().startswith('<div class="table-wrap"><table')
    assert "case-wa" in response.text
    assert "case-tg" not in response.text


def test_live_case_history_requires_authorization(env_factory, panel):
    """R24, R25: un caso no autorizado no devuelve contenido."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "SECRETO-DEL-CASO", panel.NOW)
    env.handover.authorize_error = "forbidden"

    response = env.client.get("/asesor/live/cases/case-1")

    assert response.status_code == 403
    assert "SECRETO-DEL-CASO" not in response.text


def test_live_case_history_missing_case_is_not_found(env_factory, panel):
    """R25: un caso inexistente responde 404 sin contenido."""
    env = env_factory()
    panel.login(env)
    response = env.client.get("/asesor/live/cases/no-existe")
    assert response.status_code == 404


def test_live_case_history_does_not_audit_memory_viewed(env_factory, panel):
    """R24: el refresco del historial no escribe `memory_viewed` ni auditoría."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)

    response = env.client.get("/asesor/live/cases/case-1")

    assert response.status_code == 200
    assert "hola" in response.text
    assert not any(event.type == "memory_viewed" for event in env.repo.events)
    assert not any(
        row.action == "case_viewed" for row in env.repo.panel_audit
    )


def test_live_fragment_contains_no_forms_outside_inbox_reassign(env_factory, panel):
    """R34: los fragmentos no ofrecen acciones; solo la bandeja global reasigna."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)
    env.handover.case_list = [panel.case_item("case-1")]

    history = env.client.get("/asesor/live/cases/case-1")
    inbox = env.client.get("/asesor/live/inbox")

    assert "<form" not in history.text
    assert "<form" not in inbox.text


def test_actions_remain_post_forms_with_csrf(env_factory, panel):
    """R34: responder, transferir, cerrar, devolver y reasignar siguen siendo POST."""
    env = env_factory(advisor_inbox_refresh_seconds=30)
    panel.login(env)
    panel.link_case(env, "case-1")

    response = env.client.get("/asesor/cases/case-1")

    assert response.status_code == 200
    for action in ("/asesor/reply", "/asesor/transfer", "/asesor/close", "/asesor/return"):
        assert f'method="post" action="{action}"' in response.text
    assert 'name="csrf_token" value="csrf-token"' in response.text


def test_reconnect_refetch_returns_current_state_without_duplicates(env_factory, panel):
    """R30, R31: pedir el fragmento de nuevo reemplaza y no duplica mensajes."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(
        env, contact, "user", "mensaje uno", panel.NOW - timedelta(minutes=2)
    )

    first = env.client.get("/asesor/live/cases/case-1")
    second = env.client.get("/asesor/live/cases/case-1")
    assert first.text.count("mensaje uno") == 1
    assert second.text.count("mensaje uno") == 1

    panel.add_message(env, contact, "user", "mensaje dos", panel.NOW)
    third = env.client.get("/asesor/live/cases/case-1")
    assert third.text.count("mensaje uno") == 1
    assert third.text.count("mensaje dos") == 1
