"""Seguridad del panel en tiempo real (#53): autorización y CSP."""
from __future__ import annotations

import json
import time

from orchestrator import admin

WS_SETTINGS = {
    "panel_ws_allowed_origins": "http://testserver",
    "panel_events_poll_seconds": 1,
}


def _ws(env, path: str = "/asesor/ws"):
    return env.client.websocket_connect(
        path, headers={"origin": "http://testserver", "host": "testserver"}
    )


def test_ws_delivers_only_cases_in_advisor_list(env_factory, panel):
    """R11: solo llegan eventos de casos que la bandeja del asesor incluye."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    panel.link_case(env, "case-visible")
    panel.link_case(env, "case-hidden", channel="whatsapp", user="57300", chat="57301")
    env.handover.case_list = [panel.case_item("case-visible")]
    with _ws(env) as ws:
        ws.receive_json()
        env.repo.publish_panel_event("case-hidden", "case_updated", panel.NOW)
        env.repo.publish_panel_event("case-visible", "case_updated", panel.NOW)
        event = ws.receive_json()
    assert event["case_id"] == "case-visible"


def test_ws_never_delivers_other_advisors_case(env_factory, panel):
    """R11: un caso ajeno no se entrega aunque exista el evento."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    panel.link_case(env, "case-mine")
    panel.link_case(env, "case-other", channel="whatsapp", user="57300", chat="57301")
    env.handover.case_list = [panel.case_item("case-mine")]
    with _ws(env) as ws:
        ws.receive_json()
        env.repo.publish_panel_event("case-other", "case_updated", panel.NOW)
        env.repo.publish_panel_event("case-mine", "case_updated", panel.NOW)
        event = ws.receive_json()
    assert event["case_id"] == "case-mine"


def test_ws_fails_closed_when_handover_unavailable(env_factory, panel):
    """R12: si handover falla, el lote no se entrega y se registra el error."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    env.handover.case_list = [panel.case_item("case-1")]
    with _ws(env) as ws:
        ws.receive_json()
        env.handover.fail_list_cases = True
        env.repo.publish_panel_event("case-1", "case_updated", panel.NOW)
        time.sleep(2.2)
        env.handover.fail_list_cases = False
        env.repo.publish_panel_event("case-1", "message", panel.NOW)
        event = ws.receive_json()
    assert event["type"] == "message"


def test_ws_event_has_no_tokens_text_or_client_data(env_factory, panel):
    """R13: el aviso no transporta tokens, CSRF, texto ni datos externos."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    env.handover.case_list = [panel.case_item("case-1")]
    with _ws(env) as ws:
        ws.receive_json()
        env.repo.add_message(contact.id, "user", "TEXTO-PRIVADO", panel.NOW)
        event = ws.receive_json()
    assert set(event) == {"type", "id", "case_id"}
    serialized = json.dumps(event)
    assert "TEXTO-PRIVADO" not in serialized
    assert panel.CSRF not in serialized
    assert env.settings.service_token not in serialized


def test_supervisor_scope_all_receives_global_events(env_factory, panel):
    """R7, R11: el supervisor con `scope=all` recibe avisos de cualquier caso."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env, role="supervisor")
    env.handover.case_list = [
        panel.case_item("case-other", "assigned", ["reply", "close"])
    ]
    with _ws(env, "/asesor/ws?scope=all") as ws:
        ws.receive_json()
        env.repo.publish_panel_event("case-other", "case_updated", panel.NOW)
        event = ws.receive_json()
    assert event["case_id"] == "case-other"
    assert env.handover.listed_all == ["700"]


def test_panel_pages_csp_is_strict(env_factory, panel):
    """R29: todas las páginas del panel usan la CSP estricta sin `unsafe-*`."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = []
    paths = (
        "/asesor/login",
        "/asesor",
        "/asesor/cases",
        "/asesor/cases/case-1",
        "/asesor/static/panel_live.js",
    )
    for path in paths:
        response = env.client.get(path)
        csp = response.headers["content-security-policy"]
        assert csp == admin.PANEL_CSP
        for directive in (
            "default-src 'self'",
            "script-src 'self'",
            "connect-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "object-src 'none'",
        ):
            assert directive in csp
        assert "unsafe-inline" not in csp
        assert "unsafe-eval" not in csp
