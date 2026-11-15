"""JavaScript propio y degradación sin JS del panel (#53)."""
from __future__ import annotations

import re

LIVE_SCRIPT = '<script src="/asesor/static/panel_live.js" defer>'


def test_js_served_same_origin_with_js_content_type(env_factory):
    """R27: el JavaScript se sirve desde el mismo origen con su tipo MIME."""
    env = env_factory()
    response = env.client.get("/asesor/static/panel_live.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "new WebSocket" in response.text


def test_pages_reference_script_without_inline_or_handlers(env_factory, panel):
    """R27, R28: las páginas referencian el JS externo sin scripts inline ni on*."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = [panel.case_item("case-1")]

    for path in ("/asesor/cases", "/asesor/cases/case-1"):
        html = env.client.get(path).text
        assert LIVE_SCRIPT in html
        assert html.count("<script") == 1
        assert re.search(r"\son[a-z]+\s*=", html.lower()) is None


def test_js_has_no_eval_function_string_timers_or_external_hosts(env_factory):
    """R28: sin `eval`, `Function`, timers con cadena ni hosts externos."""
    env = env_factory()
    js = env.client.get("/asesor/static/panel_live.js").text
    for forbidden in (
        "eval(",
        "new Function",
        'setTimeout("',
        "setTimeout('",
        'setInterval("',
        "setInterval('",
        "http://",
        "https://",
    ):
        assert forbidden not in js


def test_js_contains_backoff_and_polling_fallback_markers(env_factory):
    """R30, R31, R32: reemplazo idempotente, `hello`, backoff y sondeo de respaldo."""
    env = env_factory()
    js = env.client.get("/asesor/static/panel_live.js").text
    for marker in (
        "DOMParser",
        "replaceChildren",
        "BACKOFF_INITIAL_MS",
        "BACKOFF_MAX_MS",
        "30000",
        "setInterval",
    ):
        assert marker in js


def test_inbox_has_noscript_meta_refresh(env_factory, panel):
    """R33: sin JavaScript, la bandeja conserva la recarga periódica en `<noscript>`."""
    env = env_factory(advisor_inbox_refresh_seconds=30)
    panel.login(env)
    env.handover.case_list = []
    html = env.client.get("/asesor/cases").text
    assert "<noscript><meta http-equiv=\"refresh\" content=\"30\"></noscript>" in html


def test_pages_without_live_flag_omit_script_but_keep_refresh(env_factory, panel):
    """R35: con el interruptor apagado no hay script, pero sí recarga periódica."""
    env = env_factory(panel_live_enabled=False, advisor_inbox_refresh_seconds=30)
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = []

    inbox = env.client.get("/asesor/cases").text
    case = env.client.get("/asesor/cases/case-1").text

    assert LIVE_SCRIPT not in inbox
    assert LIVE_SCRIPT not in case
    assert "http-equiv=\"refresh\" content=\"30\"" in inbox
