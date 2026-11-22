"""R41-R45, R48: validación anti-SSRF y conexión a la IP ya validada."""
from __future__ import annotations

import httpx
import pytest

from telegram_gateway.adapters.callback import HttpCallbackClient
from telegram_gateway.domain import CallbackNetworkError
from telegram_gateway.url_guard import (
    CallbackUrlRejected,
    is_blocked_address,
    validate_callback_url,
)

PUBLIC = "93.184.216.34"


def _never_called(_host: str) -> list[str]:
    raise AssertionError("el resolvedor no debe consultarse para una IP literal")


def _host_url(address: str) -> str:
    if ":" in address:
        return f"https://[{address}]/callback"
    return f"https://{address}/callback"


@pytest.mark.parametrize(
    "url",
    [
        "http://callback.example.com/hook",
        "file:///etc/passwd",
        "ftp://callback.example.com/hook",
        "https:///sin-host",
        "https://usuario@callback.example.com/hook",
        "https://usuario:clave@callback.example.com/hook",
        "https://callback.example.com:puerto/hook",
        "https://callback.example.com/" + "a" * 2048,
    ],
)
def test_validate_callback_url_rejects_invalid_syntax(url):
    """R41: solo https con host, sin credenciales y hasta 2048 caracteres."""
    with pytest.raises(CallbackUrlRejected):
        validate_callback_url(url, lambda host: [PUBLIC])


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.5",
        "127.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd00::1",
        "::ffff:127.0.0.1",
    ],
)
def test_blocked_address_classes_are_rejected(address):
    """R42: cada clase de dirección bloqueada se reconoce como tal."""
    assert is_blocked_address(address) is True
    with pytest.raises(CallbackUrlRejected):
        validate_callback_url(_host_url(address), _never_called)


def test_public_literal_is_accepted_without_calling_resolver():
    """R44: una IP literal pública se valida sin consultar al resolvedor."""
    host, addresses = validate_callback_url(
        f"https://{PUBLIC}/callback", _never_called
    )
    assert host == PUBLIC
    assert addresses == [PUBLIC]


def test_all_resolved_addresses_must_be_public():
    """R43: si una dirección resuelta está bloqueada se rechaza el host."""
    with pytest.raises(CallbackUrlRejected):
        validate_callback_url(
            "https://callback.example.com/hook",
            lambda host: [PUBLIC, "10.0.0.5"],
        )


def test_host_without_resolution_is_rejected():
    """R44: un host que no resuelve no se puede validar."""
    with pytest.raises(CallbackUrlRejected):
        validate_callback_url("https://callback.example.com/hook", lambda host: [])


def test_public_host_resolves_and_is_accepted():
    """R41-R44: un host público con todas sus direcciones públicas se acepta."""
    host, addresses = validate_callback_url(
        "https://callback.example.com/hook", lambda value: [PUBLIC]
    )
    assert host == "callback.example.com"
    assert addresses == [PUBLIC]


def test_development_mode_allows_http_and_private_addresses():
    """R48: el modo de desarrollo admite http y direcciones bloqueadas."""
    host, addresses = validate_callback_url(
        "http://127.0.0.1:9000/hook", _never_called, allow_private=True
    )
    assert host == "127.0.0.1"
    assert addresses == ["127.0.0.1"]


def test_http_callback_client_connects_to_validated_ip_with_original_host():
    """R45: se conecta a la IP validada conservando Host/SNI y sin redirecciones."""
    seen: list[httpx.Request] = []
    resolutions: list[str] = []

    def resolver(host: str) -> list[str]:
        resolutions.append(host)
        return [PUBLIC]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    client = HttpCallbackClient(
        5, resolver=resolver, transport=httpx.MockTransport(handler)
    )
    status = client.post(
        "https://callback.example.com/lazaro/callback?flujo=soporte",
        b'{"hola":true}',
        {"Content-Type": "application/json"},
    )
    assert status == 200
    assert resolutions == ["callback.example.com"]
    assert len(seen) == 1
    request = seen[0]
    assert request.url.host == PUBLIC
    assert request.url.path == "/lazaro/callback"
    assert request.headers["host"] == "callback.example.com"
    assert request.extensions.get("sni_hostname") == "callback.example.com"


def test_http_callback_client_does_not_follow_redirects():
    """R38: un 3xx no se sigue; se devuelve el código tal cual."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://otro.example.com"})

    client = HttpCallbackClient(
        5, resolver=lambda host: [PUBLIC], transport=httpx.MockTransport(handler)
    )
    status = client.post("https://callback.example.com/hook", b"{}", {})
    assert status == 302
    assert len(calls) == 1


def test_http_callback_client_wraps_network_errors():
    """R39: un error de red se convierte en CallbackNetworkError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = HttpCallbackClient(
        5, resolver=lambda host: [PUBLIC], transport=httpx.MockTransport(handler)
    )
    with pytest.raises(CallbackNetworkError):
        client.post("https://callback.example.com/hook", b"{}", {})


def test_http_callback_client_rejects_blocked_url_before_requesting():
    """R46: una URL bloqueada se rechaza sin hacer ninguna petición."""
    requested = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200)

    client = HttpCallbackClient(
        5,
        resolver=lambda host: ["10.0.0.5"],
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(CallbackUrlRejected):
        client.post("https://callback.example.com/hook", b"{}", {})
    assert requested is False
