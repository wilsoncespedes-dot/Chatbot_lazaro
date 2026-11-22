"""R28–R35, R40: página de prueba del canal SIMULADO en ambos paneles."""
from __future__ import annotations

import html
from datetime import datetime, timezone

import pytest
from lazaro_contracts import ChannelInfo, MailboxEntry

from orchestrator.adapters.simulator import FakeSimulatorClient

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
CHANNEL = "tiktok-simulado"
ADMIN_PATH = "/admin/simulador"
ADVISOR_PATH = "/asesor/simulador"
TOKEN = "svc-token"


def _channel(
    channel_id: str = CHANNEL,
    name: str = "TikTok",
    adapter_type: str = "simulado",
) -> ChannelInfo:
    return ChannelInfo(
        id=channel_id,
        name=name,
        adapter_type=adapter_type,
        icon="chat",
        color="#1B6FA8",
        config={},
        active=True,
        configured=True,
        has_secrets=True,
        managed_by_environment=False,
        created_at=NOW,
    )


def _entry(
    entry_id: int,
    kind: str,
    text: str,
    destination: str = "cliente-demo",
) -> MailboxEntry:
    return MailboxEntry(
        id=entry_id,
        channel=CHANNEL,
        destination=destination,
        kind=kind,
        text=text,
        created_at=NOW,
    )


def _install(env, *, channels=None, entries=None, fail: bool = False):
    client = FakeSimulatorClient(
        channels=channels or [_channel()],
        entries=entries or [],
        fail=fail,
    )
    env.adapters.simulator = client
    return client


def _admin(env, panel):
    panel.login_admin(env)
    return env


def _supervisor(env, panel):
    panel.login(env, "supervisor", username="sup1")
    return env


def test_admin_and_supervisor_can_open_the_simulated_page(env, panel):
    """R28: admin en /admin y supervisor en /asesor obtienen 200."""
    _install(env)
    _admin(env, panel)
    admin_page = env.client.get(ADMIN_PATH)
    assert admin_page.status_code == 200
    assert "SIMULADO" in admin_page.text
    assert f'href="{ADMIN_PATH}"' in env.client.get("/admin").text

    _supervisor(env, panel)
    supervisor_page = env.client.get(ADVISOR_PATH)
    assert supervisor_page.status_code == 200


@pytest.mark.parametrize("role", ["asesor", "responsable_datos", "cliente"])
def test_non_allowed_roles_are_rejected_without_calling_the_gateway(env, panel, role):
    """R28, R31: asesor/responsable/cliente no acceden ni en GET ni en POST."""
    client = _install(env)
    panel.login(env, role, username=f"{role}1")
    for method, path in (
        ("get", ADVISOR_PATH),
        ("post", ADVISOR_PATH),
        ("get", ADMIN_PATH),
        ("post", ADMIN_PATH),
    ):
        if method == "get":
            response = env.client.get(path, follow_redirects=False)
        else:
            response = env.client.post(
                path,
                data={
                    "csrf_token": panel.CSRF,
                    "canal": CHANNEL,
                    "usuario": "cliente-demo",
                    "texto": "Hola",
                },
                follow_redirects=False,
            )
        assert response.status_code in (303, 403)
    assert client.calls == []


@pytest.mark.parametrize("path,location", [(ADMIN_PATH, "/admin/login"), (ADVISOR_PATH, "/asesor/login")])
def test_anonymous_redirects_to_the_panel_login_without_calling_the_gateway(
    env, path, location
):
    """R28: sin sesión redirige al acceso del panel correspondiente."""
    client = _install(env)
    response = env.client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == location
    assert client.calls == []


def test_page_shows_simulado_title_heading_and_label_even_if_name_lacks_it(env, panel):
    """R29, R40: título, encabezado y etiqueta contienen SIMULADO."""
    _install(env, channels=[_channel(name="TikTok")])
    _admin(env, panel)
    page = env.client.get(ADMIN_PATH)
    assert "<title>Simulador [SIMULADO]</title>" in page.text
    assert "<h2>Simulador [SIMULADO]</h2>" in page.text
    assert "TikTok [SIMULADO]" in page.text


def test_page_without_simulated_channels_shows_notice_without_form(env, panel):
    """R29: sin canales simulados hay aviso y no formulario."""
    _install(env, channels=[_channel("telegram", "Telegram", "telegram")])
    _admin(env, panel)
    page = env.client.get(ADMIN_PATH)
    assert page.status_code == 200
    assert "Todavía no hay canales simulados" in page.text
    assert f'action="{ADMIN_PATH}"' not in page.text


def test_non_simulated_channels_are_not_listed(env, panel):
    """R29: solo se listan canales con adapter_type = simulado."""
    _install(
        env,
        channels=[
            _channel(),
            _channel("telegram", "Telegram", "telegram"),
            _channel("generico", "Genérico", "webhook_generico"),
        ],
    )
    _admin(env, panel)
    page = env.client.get(ADMIN_PATH)
    assert CHANNEL in page.text
    assert "telegram" not in page.text
    assert "generico" not in page.text


@pytest.mark.parametrize("csrf", [None, "", "incorrecto"])
def test_post_with_invalid_csrf_is_forbidden_and_calls_nothing(env, panel, csrf):
    """R31: CSRF ausente o incorrecto responde la negativa del panel."""
    client = _install(env)
    _admin(env, panel)
    data = {
        "canal": CHANNEL,
        "usuario": "cliente-demo",
        "texto": "Hola",
    }
    if csrf is not None:
        data["csrf_token"] = csrf
    response = env.client.post(ADMIN_PATH, data=data, follow_redirects=False)
    assert response.status_code == 403
    assert client.calls == []


@pytest.mark.parametrize(
    "data",
    [
        {"canal": CHANNEL, "usuario": "con espacios", "texto": "Hola"},
        {"canal": CHANNEL, "usuario": "", "texto": "Hola"},
        {"canal": CHANNEL, "usuario": "a" * 65, "texto": "Hola"},
        {"canal": CHANNEL, "usuario": "cliente-demo", "texto": ""},
        {"canal": CHANNEL, "usuario": "cliente-demo", "texto": "x" * 4097},
    ],
)
def test_invalid_external_id_or_text_is_422_without_calling_the_gateway(
    env, panel, data
):
    """R31: id o texto inválidos no llaman al gateway y responden 422."""
    client = _install(env)
    _admin(env, panel)
    response = env.client.post(
        ADMIN_PATH, data={**data, "csrf_token": panel.CSRF}, follow_redirects=False
    )
    assert response.status_code == 422
    assert "error" in response.text
    assert client.calls == []


def test_channel_outside_the_simulated_list_is_422_without_simulate(env, panel):
    """R31: un canal fuera de la lista se rechaza sin llamar a /simulate."""
    client = _install(env)
    _admin(env, panel)
    response = env.client.post(
        ADMIN_PATH,
        data={
            "csrf_token": panel.CSRF,
            "canal": "telegram",
            "usuario": "cliente-demo",
            "texto": "Hola",
        },
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert not any(call[0] == "simulate" for call in client.calls)


def test_valid_post_calls_simulate_and_redirects_with_channel_and_user(env, panel):
    """R30: POST válido llama a /simulate y responde 303 con canal y usuario."""
    client = _install(env)
    _admin(env, panel)
    response = env.client.post(
        ADMIN_PATH,
        data={
            "csrf_token": panel.CSRF,
            "canal": CHANNEL,
            "usuario": "cliente-demo",
            "texto": "Hola",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"{ADMIN_PATH}?canal={CHANNEL}&usuario=cliente-demo"
    )
    assert client.calls[-1] == ("simulate", CHANNEL, "cliente-demo", "Hola")


def test_supervisor_post_also_calls_simulate_and_redirects(env, panel):
    """R28, R30: el supervisor usa la misma página desde /asesor."""
    client = _install(env)
    _supervisor(env, panel)
    response = env.client.post(
        ADVISOR_PATH,
        data={
            "csrf_token": panel.CSRF,
            "canal": CHANNEL,
            "usuario": "cliente-demo",
            "texto": "Hola",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"{ADVISOR_PATH}?canal={CHANNEL}&usuario=cliente-demo"
    )
    assert client.calls[-1][0] == "simulate"


def test_conversation_shows_client_reply_and_rejection_in_order(env, panel):
    """R32, R33: orden del buzón, nota de #65 y rechazo no es respuesta del bot."""
    _install(
        env,
        entries=[
            _entry(1, "client", "Hola, quiero información"),
            _entry(2, "reply", "Hola, con gusto te ayudo."),
            _entry(3, "rejected", "El orquestador respondió 422."),
        ],
    )
    _admin(env, panel)
    page = env.client.get(
        f"{ADMIN_PATH}?canal={CHANNEL}&usuario=cliente-demo"
    )
    assert page.status_code == 200
    text = page.text
    assert text.index("Cliente de prueba") < text.index("Plataforma (bot o asesor)")
    assert text.index("Plataforma (bot o asesor)") < text.index("Rechazo")
    assert "El orquestador no procesó el mensaje: El orquestador respondió 422." in text
    assert "Hasta #65" not in text


def test_conversation_escapes_every_message(env, panel):
    """R32: el texto del buzón se escapa y no se emite como HTML."""
    _install(
        env,
        entries=[
            _entry(1, "client", "<script>alert(1)</script>"),
            _entry(2, "reply", "<img src=x onerror=alert(2)>"),
        ],
    )
    _admin(env, panel)
    page = env.client.get(f"{ADMIN_PATH}?canal={CHANNEL}&usuario=cliente-demo")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
    assert "<img src=x onerror=alert(2)>" not in page.text
    assert html.escape("<img src=x onerror=alert(2)>") in page.text


def test_gateway_failure_shows_503_without_token_or_traceback(env, panel):
    """R34: gateway caído -> 503, sin token de servicio ni trazas."""
    _install(env, fail=True)
    _admin(env, panel)
    response = env.client.get(ADMIN_PATH)
    assert response.status_code == 503
    assert "no está disponible" in response.text
    assert TOKEN not in response.text
    assert "Traceback" not in response.text


def test_gateway_failure_on_post_is_503(env, panel):
    """R34: el fallo al simular también responde 503 y no filtra el token."""
    _install(env, fail=True)
    _admin(env, panel)
    response = env.client.post(
        ADMIN_PATH,
        data={
            "csrf_token": panel.CSRF,
            "canal": CHANNEL,
            "usuario": "cliente-demo",
            "texto": "Hola",
        },
        follow_redirects=False,
    )
    assert response.status_code == 503
    assert TOKEN not in response.text
