"""Bandeja del panel de asesores multicanal (#41)."""
from __future__ import annotations

from datetime import timedelta

from orchestrator.accounts import hash_token


def test_inbox_shows_both_channels_and_respects_role(env_factory, panel):
    """R1-R6: solo casos del asesor, con canal, estado, espera, ventana y cliente."""
    env = env_factory()
    panel.login(env)
    client = env.repo.create_profile("cliente1", "cliente", "hash", panel.NOW)
    telegram = panel.link_case(
        env, "case-tg", profile_id=client.id, created_at=panel.NOW - timedelta(minutes=30)
    )
    panel.add_message(env, telegram, "advisor", "buenas", panel.NOW - timedelta(minutes=20))
    panel.add_message(env, telegram, "user", "hola", panel.NOW - timedelta(minutes=10))
    whatsapp = panel.link_case(
        env, "case-wa", channel="whatsapp", user="57300", chat="57301"
    )
    panel.add_message(env, whatsapp, "user", "hola", panel.NOW - timedelta(hours=1))
    env.handover.case_list = [
        panel.case_item("case-tg", "open", created_at=panel.NOW - timedelta(minutes=30)),
        panel.case_item(
            "case-wa", "assigned", ["reply", "close"],
            created_at=panel.NOW - timedelta(minutes=20),
        ),
    ]

    response = env.client.get("/asesor/cases")

    assert response.status_code == 200
    assert env.handover.listed == ["700"]
    for text in (
        "case-tg",
        "telegram",
        "case-wa",
        "whatsapp",
        "Sin asignar",
        "Mío",
        "10 min",
        "No aplica",
        "Abierta",
        "cliente1",
        "Sin autenticar",
    ):
        assert text in response.text
    assert response.text.index("case-tg") < response.text.index("case-wa")


def test_inbox_filters_by_channel_and_assignment(env_factory, panel):
    """R7: los filtros se aplican juntos."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-tg", created_at=panel.NOW)
    panel.link_case(env, "case-wa", channel="whatsapp", user="57300", chat="57301")
    env.handover.case_list = [
        panel.case_item("case-tg", "open", created_at=panel.NOW),
        panel.case_item("case-wa", "assigned", ["reply", "close"], created_at=panel.NOW),
    ]

    response = env.client.get("/asesor/cases?canal=whatsapp&asignacion=mias")

    assert response.status_code == 200
    assert "case-wa" in response.text
    assert "case-tg" not in response.text


def test_invalid_filter_is_422_without_calling_handover(env_factory, panel):
    """R8: un filtro inválido responde 422 sin consultar handover."""
    env = env_factory()
    panel.login(env)
    response = env.client.get("/asesor/cases?canal=email")
    assert response.status_code == 422
    assert 'data-code="validation_error"' in response.text
    assert env.handover.listed == []


def test_inbox_orders_by_created_at_and_tolerates_unlinked_case(env_factory, panel):
    """R9, R10: orden ascendente y fila `desconocido` sin contacto."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-new", created_at=panel.NOW)
    env.handover.case_list = [
        panel.case_item("case-new", created_at=panel.NOW + timedelta(minutes=1)),
        panel.case_item("case-old", created_at=panel.NOW),
        panel.case_item("case-unlinked", created_at=panel.NOW + timedelta(minutes=2)),
    ]

    response = env.client.get("/asesor/cases")

    assert response.status_code == 200
    assert response.text.index("case-old") < response.text.index("case-new")
    assert "case-unlinked" in response.text
    assert "desconocido" in response.text


def test_non_advisor_session_redirects_without_listing(env_factory, panel):
    """R11: una sesión admin no abre el panel de asesores."""
    env = env_factory()
    panel.login_admin(env)
    response = env.client.get("/asesor/cases", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"
    assert env.handover.listed == []


def test_meta_refresh_is_configurable(env_factory, panel):
    """R12: con valor > 0 aparece <meta refresh>; con 0 no."""
    env = env_factory(advisor_inbox_refresh_seconds=30)
    panel.login(env)
    env.handover.case_list = []
    assert 'http-equiv="refresh"' in env.client.get("/asesor/cases").text

    env.settings.advisor_inbox_refresh_seconds = 0
    assert 'http-equiv="refresh"' not in env.client.get("/asesor/cases").text


def test_inbox_uses_advisor_id_from_session(env_factory, panel):
    """R1: el listado consulta handover con el advisor_id de la sesión."""
    env = env_factory()
    profile = panel.login(env, telegram_user_id=701)
    env.handover.case_list = []
    env.client.get("/asesor/cases")
    assert env.handover.listed == ["701"]
    assert hash_token("asesor-session") in env.repo.sessions
    assert profile.telegram_user_id == 701
