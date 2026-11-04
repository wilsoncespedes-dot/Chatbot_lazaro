"""Vista de conversación del panel multicanal (#41)."""
from __future__ import annotations

from datetime import timedelta

from orchestrator.domain import ClientCredential


def _client_profile(env, panel, username: str = "cliente1"):
    return env.repo.create_profile(username, "cliente", "hash", panel.NOW)


def _credential(env, panel, profile_id: str):
    env.repo.client_credentials[profile_id] = ClientCredential(
        profile_id=profile_id,
        valid_from=panel.NOW - timedelta(days=1),
        valid_until=panel.NOW + timedelta(days=10),
    )


def test_authorization_happens_before_reading_case_data(env_factory, monkeypatch, panel):
    """R40, R41: una denegación no lee mensajes, memoria ni datos del cliente."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.authorize_error = "forbidden"
    calls: list[str] = []

    def boom(*args, **kwargs):
        calls.append("read")
        raise AssertionError("no debe leer")

    monkeypatch.setattr(env.repo, "case_messages", boom)
    monkeypatch.setattr(env.repo, "last_privacy_decision", boom)

    response = env.client.get("/asesor/cases/case-1")

    assert response.status_code == 403
    assert calls == []


def test_history_respects_lookback_limit_labels_and_order(env_factory, panel):
    """R42, R43: historial desde el lookback, con etiquetas por rol y en orden."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "FUERA-DEL-LOOKBACK", panel.NOW - timedelta(hours=2))
    panel.add_message(env, contact, "user", "mensaje cliente", panel.NOW - timedelta(minutes=30))
    panel.add_message(env, contact, "bot", "mensaje bot", panel.NOW - timedelta(minutes=20))
    panel.add_message(env, contact, "advisor", "mensaje asesor", panel.NOW - timedelta(minutes=10))

    response = env.client.get("/asesor/cases/case-1")

    assert response.status_code == 200
    assert "FUERA-DEL-LOOKBACK" not in response.text
    assert response.text.index("Cliente") < response.text.index("mensaje cliente")
    for label in ("Cliente", "Bot", "Asesor"):
        assert label in response.text
    assert response.text.index("mensaje cliente") < response.text.index("mensaje bot")
    assert response.text.index("mensaje bot") < response.text.index("mensaje asesor")


def test_foreign_session_windows_are_hidden_with_and_without_profile(env_factory, panel):
    """R44: los mensajes dentro de la ventana de sesión de otro cliente no se muestran."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env, panel)
    contact = panel.link_case(env, "case-1", profile_id=client.id, created_at=panel.NOW - timedelta(hours=2))
    panel.add_message(env, contact, "user", "DENTRO-DE-VENTANA-AJENA", panel.NOW - timedelta(minutes=30))
    panel.add_client_session(
        env, "s2", "otro-perfil", contact.id, panel.NOW - timedelta(hours=1), panel.NOW
    )
    response = env.client.get("/asesor/cases/case-1")
    assert "DENTRO-DE-VENTANA-AJENA" not in response.text

    env2 = env_factory()
    panel.login(env2)
    contact2 = panel.link_case(env2, "case-1", profile_id=None, created_at=panel.NOW - timedelta(hours=2))
    panel.add_message(env2, contact2, "user", "DENTRO-DE-VENTANA", panel.NOW - timedelta(minutes=30))
    panel.add_client_session(
        env2, "s3", "otro-perfil", contact2.id, panel.NOW - timedelta(hours=1), panel.NOW
    )
    response2 = env2.client.get("/asesor/cases/case-1")
    assert "DENTRO-DE-VENTANA" not in response2.text


def test_memory_and_summaries_are_shown_and_client_data_is_masked(env_factory, panel):
    """R45, R46: memoria/resúmenes y datos permitidos con identificador enmascarado."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env, panel)
    _credential(env, panel, client.id)
    env.repo.set_client_memory(client.id, ("Prefiere correo",), "s1", panel.NOW)
    env.repo.upsert_conversation_summary(
        "s1", client.id, "c1", "whatsapp", "Resumen visible", "session_end", panel.NOW
    )
    contact = panel.link_case(
        env,
        "case-1",
        channel="whatsapp",
        user="573001234",
        chat="573001235",
        profile_id=client.id,
    )
    env.repo.add_privacy_decision(
        "whatsapp",
        "573001234",
        "v1",
        "sha",
        "accepted",
        "msg-1",
        "accept",
        panel.NOW,
    )
    response = env.client.get("/asesor/cases/case-1")
    assert response.status_code == 200
    for text in ("Prefiere correo", "Resumen visible", "cliente1", "…1234", "whatsapp"):
        assert text in response.text
    assert "573001234" not in response.text
    assert contact.external_user_id == "573001234"


def test_case_without_profile_shows_no_client_and_no_memory(env_factory, panel):
    """R47: sin perfil solo se muestra `Sin cliente autenticado`, sin memoria."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1", profile_id=None)
    response = env.client.get("/asesor/cases/case-1")
    assert response.status_code == 200
    assert "Sin cliente autenticado" in response.text
    assert "Memoria y resúmenes" not in response.text


def test_all_texts_are_escaped(env_factory, panel):
    """R48: mensajes, memoria, nombres y plantillas se escapan con html.escape."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env, panel, "cli<b>")
    contact = panel.link_case(env, "case-1", profile_id=client.id, created_at=panel.NOW - timedelta(hours=2))
    env.repo.set_client_memory(client.id, ("<script>m</script>",), "s1", panel.NOW)
    panel.add_message(env, contact, "user", "<script>alert(1)</script>", panel.NOW - timedelta(minutes=10))
    response = env.client.get("/asesor/cases/case-1")
    assert response.status_code == 200
    assert "&lt;script&gt;" in response.text
    assert "<script>" not in response.text
    assert "cli&lt;b&gt;" in response.text


def test_transfer_targets_include_presence(env_factory, panel):
    """R49: se ofrecen los demás asesores con su presencia efectiva."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    target = panel.make_profile(env, "destino", "asesor", 222)
    panel.set_presence(env, target.id, "available")
    response = env.client.get("/asesor/cases/case-1")
    assert response.status_code == 200
    assert "destino" in response.text
    assert "available" in response.text


def test_memory_route_and_whatsapp_contact_remain_available(env_factory, panel):
    """R73: `/memoria` sigue respondiendo y el canal WhatsApp del caso llega a la vista."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env, panel)
    panel.link_case(env, "case-1", channel="whatsapp", user="57300", chat="57301",
              profile_id=client.id)
    memory = env.client.get("/asesor/cases/case-1/memoria")
    assert memory.status_code == 200
    view = env.client.get("/asesor/cases/case-1")
    assert view.status_code == 200
    assert "whatsapp" in view.text
