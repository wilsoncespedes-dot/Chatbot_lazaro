"""Asesores sin verificación por Telegram (#65)."""
from __future__ import annotations

import pytest

from orchestrator import advisor_panel


@pytest.mark.parametrize("role", ["asesor", "supervisor"])
def test_unlinked_advisor_sees_full_home(env_factory, panel, role):
    """R1: sin Telegram vinculado el Inicio muestra presencia y acciones, sin aviso."""
    env = env_factory()
    panel.login(env, role=role, telegram_user_id=None)
    response = env.client.get("/asesor")
    assert response.status_code == 200
    html = response.text
    assert "Telegram" not in html
    for action in ("/asesor/presence", "/asesor/reply", "/asesor/assign", "/asesor/close"):
        assert f'action="{action}"' in html


def test_unlinked_advisor_can_use_inbox_and_case(env_factory, panel):
    """R2: bandeja y caso funcionan sin Telegram vinculado."""
    env = env_factory()
    panel.login(env, role="asesor", telegram_user_id=None)
    panel.link_case(env, "case-1")
    env.handover.case_list = [panel.case_item("case-1", "open")]
    assert env.client.get("/asesor/cases").status_code == 200
    assert env.client.get("/asesor/cases/case-1").status_code == 200


def test_no_telegram_not_linked_message_remains():
    """R2: el error `telegram_not_linked` ya no existe en el panel de asesores."""
    assert "telegram_not_linked" not in advisor_panel.ERROR_MESSAGES
    html = advisor_panel.render_advisor_home("csrf")
    assert "Telegram" not in html
