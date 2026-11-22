"""ID de cliente en el panel: botones, búsqueda, roles y ausencia de secretos (#73)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.domain import ClientSession, ConversationState, create_client

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD = "clave-segura-123"


def _env(env_factory):
    return env_factory(password_scrypt_n=16384)


def _client(env, username: str = "cliente1"):
    return create_client(
        username,
        PASSWORD,
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )


def _case(env, panel, client, case_id: str = "case-1", user: str = "10"):
    contact = env.repo.get_or_create_channel_contact("telegram", user, "100", NOW)
    env.handover.case_list = [panel.case_item(case_id)]
    env.repo.link_case(case_id, contact.id, NOW, profile_id=client.profile_id)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    return contact


def test_case_detail_shows_id_with_copy_button(env_factory, panel):
    """R15: la ficha del cliente del detalle del caso muestra el ID y «Copiar»."""
    env = _env(env_factory)
    client = _client(env)
    _case(env, panel, client)
    panel.login(env, "asesor")

    html = env.client.get("/asesor/cases/case-1").text

    assert client.public_id in html
    assert f'data-copy="{client.public_id}"' in html
    assert "Copiar" in html


def test_case_inbox_shows_id_and_copy_button(env_factory, panel):
    """R16: cada fila de la bandeja de casos muestra el ID del cliente autenticado."""
    env = _env(env_factory)
    client = _client(env)
    _case(env, panel, client)
    panel.login(env, "asesor")

    html = env.client.get("/asesor/cases").text

    assert client.public_id in html
    assert f'data-copy="{client.public_id}"' in html


def test_conversation_inbox_shows_id_and_copy_button(env_factory, panel):
    """R16: la bandeja de conversaciones muestra el ID con botón copiar."""
    env = _env(env_factory)
    client = _client(env)
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    env.repo.add_message(contact.id, "user", "hola", NOW)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=client.profile_id,
        contact_id=contact.id,
        started_at=NOW,
        last_activity_at=NOW,
    )
    panel.login(env, "asesor")

    html = env.client.get("/asesor/conversaciones").text

    assert client.public_id in html
    assert f'data-copy="{client.public_id}"' in html


def test_conversation_header_and_admin_clients_show_id(env_factory, panel):
    """R17: encabezado de la conversación y lista de Clientes del admin."""
    env = _env(env_factory)
    client = _client(env)
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    env.repo.add_message(contact.id, "user", "hola", NOW)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=client.profile_id,
        contact_id=contact.id,
        started_at=NOW,
        last_activity_at=NOW,
    )
    panel.login(env, "asesor")
    html = env.client.get(f"/asesor/conversaciones/{contact.id}").text
    assert client.public_id in html and f'data-copy="{client.public_id}"' in html

    env.client.cookies.clear()
    panel.login_admin(env)
    admin_html = env.client.get("/admin/clientes").text
    assert client.public_id in admin_html
    assert f'data-copy="{client.public_id}"' in admin_html


def test_copy_script_is_same_origin_without_inline_handlers(env_factory, panel):
    """R18: botón `data-copy` y script propio sin `onclick` ni cambios de CSP."""
    env = _env(env_factory)
    client = _client(env)
    _case(env, panel, client)
    panel.login(env, "asesor")

    html = env.client.get("/asesor/cases/case-1").text
    assert '<script src="/panel/copiar.js" defer></script>' in html
    assert "onclick=" not in html
    response = env.client.get("/panel/copiar.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "navigator.clipboard" in response.text
    assert "onclick" not in response.text


def _linked_client(env, username: str = "cliente1"):
    client = _client(env, username)
    contact = env.repo.get_or_create_channel_contact(
        "telegram", "573001112233", "57300999", NOW
    )
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    env.repo.identidades_cliente[("telegram", "573001112233")] = (
        client.profile_id,
        NOW,
    )
    return client, contact


def test_advisor_searches_by_normalized_id(env_factory, panel):
    """R19, R21: el ID en minúsculas con guiones encuentra al cliente y sus enlaces."""
    env = _env(env_factory)
    client, contact = _linked_client(env)
    panel.login(env, "asesor")

    response = env.client.get(
        "/asesor/clientes", params={"q": client.public_id.lower()}
    )

    assert response.status_code == 200
    assert client.username in response.text
    assert client.public_id in response.text
    assert f"/asesor/conversaciones/{contact.id}" in response.text


def test_admin_filters_by_normalized_id(env_factory, panel):
    """R20, R21: el admin filtra la lista y acepta espacios y minúsculas."""
    env = _env(env_factory)
    first = _client(env, "cliente1")
    _client(env, "cliente2")
    panel.login_admin(env)

    query = f" {first.public_id.lower().replace('-', ' ')} "
    html = env.client.get("/admin/clientes", params={"q": query}).text

    assert "cliente1" in html
    assert "cliente2" not in html


def test_invalid_id_and_no_results_return_200_messages(env_factory, panel):
    """R22, R23: ID inválido y sin resultados son respuestas 200 informativas."""
    env = _env(env_factory)
    panel.login(env, "asesor")

    invalid = env.client.get("/asesor/clientes", params={"q": "0O0O-1111"})
    assert invalid.status_code == 200 and "ID no válido" in invalid.text

    missing = env.client.get("/asesor/clientes", params={"q": "ABCD-2345"})
    assert missing.status_code == 200 and "Sin resultados" in missing.text

    env.client.cookies.clear()
    panel.login_admin(env)
    admin_invalid = env.client.get("/admin/clientes", params={"q": "0O0O-1111"})
    assert admin_invalid.status_code == 200 and "ID no válido" in admin_invalid.text


def test_search_requires_a_panel_session(env_factory):
    """R24: sin sesión de panel la búsqueda redirige al login correspondiente."""
    env = _env(env_factory)

    advisor = env.client.get(
        "/asesor/clientes", params={"q": "ABCD-2345"}, follow_redirects=False
    )
    assert advisor.status_code == 303 and advisor.headers["location"] == "/asesor/login"

    admin = env.client.get(
        "/admin/clientes", params={"q": "ABCD-2345"}, follow_redirects=False
    )
    assert admin.status_code == 303 and admin.headers["location"] == "/admin/login"


def test_search_never_shows_password_hash_or_unmasked_external_id(env_factory, panel):
    """R25: el resultado no expone hash ni el id externo completo."""
    env = _env(env_factory)
    client, _contact = _linked_client(env)
    panel.login(env, "asesor")

    html = env.client.get("/asesor/clientes", params={"q": client.public_id}).text

    assert "573001112233" not in html
    assert "…2233" in html
    assert "hash" not in html.lower()
    assert PASSWORD not in html
