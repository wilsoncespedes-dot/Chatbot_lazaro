"""R10–R18 (#65): directorio de canales por HTTP, política derivada y caché."""
from __future__ import annotations

import logging

import httpx
import pytest
from fakes import channel_info
from lazaro_contracts import SERVICE_TOKEN_HEADER, ChannelListResponse

from orchestrator.adapters.channels import FakeChannelDirectory, HttpChannelDirectory
from orchestrator.channels import default_policy, policy_from_info
from orchestrator.domain import ServiceUnavailable

BASE = "http://gateway:8001"
TOKEN = "svc-token"


def _listing(*infos) -> dict:
    return ChannelListResponse(channels=list(infos), adapter_types=[]).model_dump(mode="json")


class _Http:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or _listing(channel_info("whatsapp", windowed=True, consent_mode="boton"))
        self.calls: list[tuple[str, dict]] = []
        self.fail = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if self.fail:
            raise httpx.ConnectError("sin red")
        return httpx.Response(200, json=self.payload, request=httpx.Request("GET", url))


@pytest.fixture()
def http(monkeypatch):
    fake = _Http()
    monkeypatch.setattr(httpx, "get", fake.get)
    return fake


def _directory(now: list[float], ttl: float = 30) -> HttpChannelDirectory:
    return HttpChannelDirectory(BASE + "/", TOKEN, ttl, clock=lambda: now[0])


def test_directory_calls_gateway_channels_with_service_token(http):
    """R10: GET /channels del gateway con X-Service-Token."""
    policy = _directory([0.0]).policy("whatsapp")
    assert http.calls == [(f"{BASE}/channels", {SERVICE_TOKEN_HEADER: TOKEN})]
    assert policy.windowed is True
    assert policy.consent_mode == "boton"


def test_windowed_policy_requires_both_capabilities():
    """R11, R12: con ventana solo si free_text_allowed=false y requires_template=true."""
    assert policy_from_info(channel_info("ca", windowed=True)).windowed is True
    assert policy_from_info(channel_info("cb", windowed=False)).windowed is False
    assert policy_from_info(channel_info("cc", capabilities=None)).windowed is False
    half = channel_info("cd", windowed=True).capabilities.model_copy(
        update={"requires_template": False}
    )
    assert policy_from_info(channel_info("cd", capabilities=half)).windowed is False


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("texto", "texto"), ("boton", "boton"), (None, "texto"), ("voz", "texto")],
)
def test_consent_mode_comes_from_config_with_texto_default(mode, expected):
    """R13, S3: modo de config.consent_mode; ausente o inválido es `texto`."""
    info = channel_info("canal-x", consent_mode=None)
    if mode is not None:
        info = info.model_copy(update={"config": {"consent_mode": mode}})
    assert policy_from_info(info).consent_mode == expected


def test_unknown_channel_gets_default_policy(http):
    """R14: id ausente → sin ventana, `texto` y nombre igual al id."""
    policy = _directory([0.0]).policy("tiktok")
    assert policy == default_policy("tiktok")
    assert (policy.windowed, policy.consent_mode, policy.name) == (False, "texto", "tiktok")


def test_directory_reuses_copy_while_ttl_is_fresh(http):
    """R15: dentro del TTL no se vuelve a llamar a GET /channels."""
    now = [100.0]
    directory = _directory(now, ttl=30)
    directory.policy("whatsapp")
    now[0] += 29.9
    directory.list_policies()
    directory.policy("otro")
    assert len(http.calls) == 1
    now[0] += 0.2
    directory.policy("whatsapp")
    assert len(http.calls) == 2


def test_directory_uses_stale_copy_and_warns_without_personal_data(http, caplog):
    """R16: si falla con copia previa, usa la copia y registra channel_directory_stale."""
    now = [0.0]
    directory = _directory(now, ttl=1)
    directory.policy("whatsapp")
    http.fail = True
    now[0] += 5
    with caplog.at_level(logging.WARNING):
        policy = directory.policy("whatsapp")
    assert policy.windowed is True
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("channel_directory_stale code=ConnectError") for m in messages)
    assert all(TOKEN not in m for m in messages)


def test_directory_without_copy_raises_service_unavailable(http):
    """R17: sin copia previa el fallo es ServiceUnavailable."""
    http.fail = True
    with pytest.raises(ServiceUnavailable):
        _directory([0.0]).policy("whatsapp")


def test_invalid_response_counts_as_failure(http):
    """R17: una respuesta que no valida contra el contrato no se usa."""
    http.payload = {"channels": [{"id": "x"}], "adapter_types": []}
    with pytest.raises(ServiceUnavailable):
        _directory([0.0]).list_policies()


def test_list_policies_orders_active_first():
    infos = [
        channel_info("b-inactivo", active=False),
        channel_info("a-activo"),
    ]
    assert [p.id for p in FakeChannelDirectory(infos).list_policies()] == ["a-activo", "b-inactivo"]


def test_post_messages_answers_upstream_error_when_directory_is_down(env):
    """R18: sin directorio, POST /messages responde upstream_error y no encola."""
    env.adapters.channels = FakeChannelDirectory(fail=True)
    response = env.client.post(
        "/messages",
        json={
            "channel": "simulado",
            "external_user_id": "u-1",
            "external_chat_id": "u-1",
            "external_message_id": "m-1",
            "kind": "text",
            "text": "Hola",
            "received_at": "2026-01-02T03:04:00+00:00",
        },
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"
    assert env.repo.claim_inbound(env.adapters.clock(), 30) is None
