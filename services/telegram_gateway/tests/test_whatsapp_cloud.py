"""Pruebas del adaptador real de WhatsApp Cloud API (#43), sin red."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from lazaro_contracts import (
    ListBlock,
    LinkBlock,
    OptionsBlock,
    TemplateBlock,
    TextBlock,
)

from telegram_gateway.adapters.telegram import FakeTelegramClient, TelegramChannelAdapter
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.adapters.whatsapp_cloud import (
    WhatsAppCloudAdapter,
    WhatsAppCloudConfig,
)
from telegram_gateway.adapters.whatsapp_window import FakeWhatsAppWindowStore
from telegram_gateway.domain import (
    ChannelSendFailed,
    ChannelWindowClosed,
    TemplateNotApproved,
    send_response,
)

NOW = datetime(2026, 11, 3, 16, 0, 0, tzinfo=timezone.utc)
DESTINATION = "573001112233"
ACCESS_TOKEN = "ACCESS-TOKEN-VALUE"
MESSAGES_URL = "https://graph.test/v21.0/PN-1/messages"


def make_adapter(handler, *, window=None, now=NOW):
    window = window or FakeWhatsAppWindowStore()
    return WhatsAppCloudAdapter(
        WhatsAppCloudConfig(
            access_token=ACCESS_TOKEN,
            phone_number_id="PN-1",
            graph_base_url="https://graph.test/",
            api_version="v21.0",
            template_language="es",
            interactive_body_text="Elige una opción:",
            window_hours=24,
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
        window,
        lambda: now,
    )


def open_window() -> FakeWhatsAppWindowStore:
    window = FakeWhatsAppWindowStore()
    window.values[DESTINATION] = NOW - timedelta(hours=1)
    return window


def ok_handler(calls: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})

    return handler


def payload_of(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ── R28-R31, R42, R61: ventana y capacidades ────────────────────────────────


def test_capabilities_for_opens_window_with_recent_inbound():
    """R28: un entrante hace 1 h mantiene la ventana abierta."""
    adapter = make_adapter(ok_handler([]), window=open_window())
    capabilities = adapter.capabilities_for(DESTINATION)
    assert capabilities.free_text_allowed is True
    assert capabilities.requires_template is False


def test_capabilities_for_closes_at_24_hours_or_without_inbound():
    """R29: a las 24 h exactas y sin entrante la ventana está cerrada."""
    window = FakeWhatsAppWindowStore()
    window.values[DESTINATION] = NOW - timedelta(hours=24)
    adapter = make_adapter(ok_handler([]), window=window)
    assert adapter.capabilities_for(DESTINATION).free_text_allowed is False
    assert adapter.capabilities_for("otro").requires_template is True


def test_capabilities_without_destination_is_closed():
    """R30: capabilities() = ventana cerrada."""
    adapter = make_adapter(ok_handler([]), window=open_window())
    capabilities = adapter.capabilities()
    assert capabilities.free_text_allowed is False
    assert capabilities.requires_template is True


def test_send_response_uses_capabilities_for_when_available():
    """R31: el núcleo pregunta por el destino concreto."""
    adapter = make_adapter(ok_handler([]))
    with pytest.raises(ChannelWindowClosed):
        send_response(adapter, DESTINATION, [TextBlock(type="text", text="Hola")])


def test_send_response_falls_back_to_capabilities_for_telegram_and_fake():
    """R61: los adaptadores sin capabilities_for siguen usando capabilities()."""
    telegram = TelegramChannelAdapter(FakeTelegramClient())
    fake_whatsapp = FakeWhatsAppAdapter(window_open=True)
    assert (
        send_response(telegram, "77", [TextBlock(type="text", text="Hola")])
        == "sent"
    )
    assert (
        send_response(fake_whatsapp, DESTINATION, [TextBlock(type="text", text="Hola")])
        == "sent"
    )


def test_window_store_failure_is_treated_as_open_with_warning(caplog):
    """R42: si el almacén falla se avisa y se trata como abierta."""
    adapter = make_adapter(
        ok_handler([]), window=FakeWhatsAppWindowStore(fail=True)
    )
    with caplog.at_level(logging.WARNING):
        capabilities = adapter.capabilities_for(DESTINATION)
    assert capabilities.free_text_allowed is True
    assert any("ventana" in record.getMessage().lower() for record in caplog.records)
    assert DESTINATION not in "\n".join(r.getMessage() for r in caplog.records)


def test_window_store_failure_does_not_block_sending():
    """R42: el envío continúa y delega la validación al orquestador/Meta."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(
        ok_handler(calls), window=FakeWhatsAppWindowStore(fail=True)
    )
    assert adapter.send(DESTINATION, [TextBlock(type="text", text="Hola")]) == "sent"
    assert len(calls) == 1


# ── R32-R40, R54-R58, R62: envío ────────────────────────────────────────────


def test_text_inside_window_has_exact_url_headers_and_body():
    """R32, R62: un único POST con Bearer y el cuerpo exacto de Meta."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls), window=open_window())
    assert adapter.send(DESTINATION, [TextBlock(type="text", text="Hola")]) == "sent"
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == MESSAGES_URL
    assert request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert payload_of(request) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": DESTINATION,
        "type": "text",
        "text": {"body": "Hola", "preview_url": False},
    }


def test_text_outside_window_makes_no_request():
    """R33: fuera de ventana se lanza ChannelWindowClosed sin HTTP."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls))
    with pytest.raises(ChannelWindowClosed):
        adapter.send(DESTINATION, [TextBlock(type="text", text="Hola")])
    assert calls == []


def test_template_inside_and_outside_window_includes_variables_in_order():
    """R34: la plantilla lleva idioma y parámetros en orden."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls))
    block = TemplateBlock(type="template", name="aviso", variables=["uno", "dos"])
    assert adapter.send(DESTINATION, [block]) == "sent"
    payload = payload_of(calls[0])
    assert payload["type"] == "template"
    assert payload["template"] == {
        "name": "aviso",
        "language": {"code": "es"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "uno"},
                    {"type": "text", "text": "dos"},
                ],
            }
        ],
    }


def test_template_without_variables_omits_components():
    """R35: sin variables no se incluye components."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls))
    adapter.send(DESTINATION, [TemplateBlock(type="template", name="aviso")])
    assert "components" not in payload_of(calls[0])["template"]


def test_options_with_ids_merge_previous_text_as_interactive_body():
    """R36, R37, R54: botones con id:proof y texto previo como cuerpo."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls), window=open_window())
    blocks = [
        TextBlock(type="text", text="¿Aceptas?"),
        OptionsBlock(
            type="options",
            options=["Acepto", "No"],
            option_ids=["privacy.accept", "privacy.reject"],
            option_proofs=["p1", "p2"],
        ),
    ]
    assert adapter.send(DESTINATION, blocks) == "sent"
    assert len(calls) == 1
    payload = payload_of(calls[0])
    assert payload["type"] == "interactive"
    assert payload["interactive"] == {
        "type": "button",
        "body": {"text": "¿Aceptas?"},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": "privacy.accept:p1", "title": "Acepto"},
                },
                {
                    "type": "reply",
                    "reply": {"id": "privacy.reject:p2", "title": "No"},
                },
            ]
        },
    }


def test_long_previous_text_uses_default_interactive_body():
    """R55: un texto previo de más de 1024 no se usa como cuerpo."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls), window=open_window())
    blocks = [
        TextBlock(type="text", text="x" * 1025),
        OptionsBlock(type="options", options=["Sí"], option_ids=["opt"]),
    ]
    adapter.send(DESTINATION, blocks)
    assert len(calls) == 2
    assert payload_of(calls[0])["type"] == "text"
    assert payload_of(calls[1])["interactive"]["body"]["text"] == "Elige una opción:"


def test_too_long_reply_id_fails_without_request():
    """R38: un reply.id de más de 256 no llega a Meta."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls), window=open_window())
    blocks = [
        OptionsBlock(
            type="options",
            options=["Opción"],
            option_ids=["a" * 128],
            option_proofs=["b" * 128],
        )
    ]
    with pytest.raises(ChannelSendFailed):
        adapter.send(DESTINATION, blocks)
    assert calls == []


def test_options_without_ids_list_and_link_are_sent_as_text():
    """R39: opciones sin ids, lista y enlace se representan como texto."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls), window=open_window())
    blocks = [
        OptionsBlock(type="options", options=["Sí", "No"]),
        ListBlock(type="list", options=["Uno", "Dos", "Tres", "Cuatro"]),
        LinkBlock(type="link", text="Ayuda", url="https://example.com/ayuda"),
    ]
    adapter.send(DESTINATION, blocks)
    assert [payload_of(call)["type"] for call in calls] == ["text", "text", "text"]
    assert payload_of(calls[0])["text"] == {"body": "Sí\nNo", "preview_url": False}
    assert "1. Uno" in payload_of(calls[1])["text"]["body"]
    assert payload_of(calls[2])["text"] == {
        "body": "Ayuda: https://example.com/ayuda",
        "preview_url": True,
    }


def test_multiple_blocks_are_sent_in_order_and_return_sent():
    """R40, R56: varios bloques en orden y todas 2xx → sent."""
    calls: list[httpx.Request] = []
    adapter = make_adapter(ok_handler(calls), window=open_window())
    blocks = [
        TextBlock(type="text", text="Uno"),
        TextBlock(type="text", text="Dos"),
        TextBlock(type="text", text="Tres"),
    ]
    assert adapter.send(DESTINATION, blocks) == "sent"
    assert [payload_of(call)["text"]["body"] for call in calls] == [
        "Uno",
        "Dos",
        "Tres",
    ]


def test_failure_stops_following_blocks_without_retry():
    """R41, R57, R58: al fallar el segundo no se envía el tercero ni se repite."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(
                400, json={"error": {"code": 100, "message": "detalle interno"}}
            )
        return httpx.Response(200, json={"messages": []})

    adapter = make_adapter(handler, window=open_window())
    with pytest.raises(ChannelSendFailed):
        adapter.send(
            DESTINATION,
            [
                TextBlock(type="text", text="Uno"),
                TextBlock(type="text", text="Dos"),
                TextBlock(type="text", text="Tres"),
            ],
        )
    assert len(calls) == 2


# ── R43-R48, R59: traducción de errores y estados ───────────────────────────


@pytest.mark.parametrize("code", [132000, 132001, 132005, 132007, 132012, 132015, 132016])
def test_template_error_codes_become_template_not_approved(code):
    """R44: los códigos de plantilla se traducen a TemplateNotApproved."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": code}})

    adapter = make_adapter(handler, window=open_window())
    with pytest.raises(TemplateNotApproved):
        adapter.send(DESTINATION, [TemplateBlock(type="template", name="aviso")])


def test_window_error_code_becomes_channel_window_closed():
    """R43: 131047 se traduce a ChannelWindowClosed."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 131047}})

    adapter = make_adapter(handler, window=open_window())
    with pytest.raises(ChannelWindowClosed):
        adapter.send(DESTINATION, [TextBlock(type="text", text="Hola")])


@pytest.mark.parametrize(
    "status_code, body",
    [
        (401, {"error": {"code": 190}}),
        (429, {"error": {"code": 130429}}),
        (500, {"error": {"code": 100}}),
        (502, None),
    ],
)
def test_other_errors_become_channel_send_failed(status_code, body):
    """R45: otros códigos, no JSON y fallos de red se traducen a 502."""
    def handler(request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status_code, content=b"no es json")
        return httpx.Response(status_code, json=body)

    adapter = make_adapter(handler, window=open_window())
    with pytest.raises(ChannelSendFailed):
        adapter.send(DESTINATION, [TextBlock(type="text", text="Hola")])


def test_network_errors_become_channel_send_failed():
    """R45: ConnectError y ReadTimeout se traducen a ChannelSendFailed."""
    for error in (httpx.ConnectError("boom"), httpx.ReadTimeout("boom")):
        def handler(request: httpx.Request, error=error) -> httpx.Response:
            raise error

        adapter = make_adapter(handler, window=open_window())
        with pytest.raises(ChannelSendFailed) as info:
            adapter.send(DESTINATION, [TextBlock(type="text", text="Hola")])
        assert "boom" not in str(info.value)


def test_error_log_has_codes_but_not_secrets_or_body(caplog):
    """R46, R59: el log lleva estado/código/subcódigo/fbtrace, sin cuerpo."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": 132001,
                    "error_subcode": 2494010,
                    "fbtrace_id": "TRACE-1",
                    "message": "detalle-secreto-de-meta",
                }
            },
        )

    adapter = make_adapter(handler, window=open_window())
    with caplog.at_level(logging.ERROR):
        with pytest.raises(TemplateNotApproved) as info:
            adapter.send(DESTINATION, [TemplateBlock(type="template", name="aviso")])
    log = "\n".join(record.getMessage() for record in caplog.records)
    assert "400" in log and "132001" in log and "2494010" in log and "TRACE-1" in log
    assert "detalle-secreto-de-meta" not in log
    assert "detalle-secreto-de-meta" not in str(info.value)
    assert ACCESS_TOKEN not in log and DESTINATION not in log


def test_logs_never_include_destination_or_text():
    """R6: ni el wa_id ni el texto aparecen en logs de envío."""
    import logging as logging_module

    records: list[str] = []

    class Capture(logging_module.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging_module.getLogger("telegram_gateway.adapters.whatsapp_cloud")
    handler_log = Capture()
    logger.addHandler(handler_log)
    try:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": {"code": 100}})

        adapter = make_adapter(handler, window=open_window())
        with pytest.raises(ChannelSendFailed):
            adapter.send(DESTINATION, [TextBlock(type="text", text="texto-privado")])
    finally:
        logger.removeHandler(handler_log)
    log = "\n".join(records)
    assert DESTINATION not in log and "texto-privado" not in log


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("sent", "sent"),
        ("delivered", "delivered"),
        ("read", "read"),
        ("failed", "failed"),
        ("  DELIVERED ", "delivered"),
        ("deleted", "failed"),
        ("", "failed"),
    ],
)
def test_delivery_status_vocabulary(raw, expected):
    """R48: estados traducidos al vocabulario cerrado."""
    adapter = make_adapter(ok_handler([]))
    assert adapter.delivery_status(raw) == expected
