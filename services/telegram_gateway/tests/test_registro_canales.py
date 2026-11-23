"""R5–R14: puerto Canal, factories registradas y adaptadores existentes."""
from __future__ import annotations

import httpx
from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import (
    ChannelCapabilities,
    ImageBlock,
    LinkBlock,
    NormalizedMessage,
    OptionsBlock,
    TextBlock,
)

from telegram_gateway.adapters.channels import (
    FacebookMessengerChannel,
    InstagramMessagingChannel,
    SimuladoChannel,
    TelegramChannel,
    WhatsAppCloudChannel,
)
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.adapters.whatsapp_cloud import (
    WhatsAppCloudAdapter,
    WhatsAppCloudConfig,
)
from telegram_gateway.adapters.whatsapp_window import FakeWhatsAppWindowStore
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    ChannelRecord,
    extract_callback,
    extract_incoming,
    normalize_callback,
    normalize_incoming,
)
from telegram_gateway.ports.canal import Canal
from telegram_gateway.registry import (
    CHANNEL_REGISTRY,
    ChannelContext,
    ChannelRegistry,
    DuplicateAdapterType,
    UnknownAdapterType,
)
from telegram_gateway.whatsapp_cloud import normalize_message

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
DESTINATION = "573001112233"


def _adapters(*, whatsapp=None) -> Adapters:
    return Adapters(
        telegram=FakeTelegramClient(),
        dedup=object(),
        orchestrator=object(),
        clock=lambda: NOW,
        whatsapp=whatsapp,
    )


def _record(adapter_type: str = "telegram") -> ChannelRecord:
    return ChannelRecord(
        id="canal-test",
        name="Canal test",
        adapter_type=adapter_type,
        icon="chat",
        color="#1B6FA8",
        config={},
        active=True,
        created_at=NOW,
        has_secrets=False,
        active_follows_environment=True,
    )


def _cloud_adapter(*, window_open: bool = False) -> WhatsAppCloudAdapter:
    window = FakeWhatsAppWindowStore()
    if window_open:
        window.values[DESTINATION] = NOW - timedelta(hours=1)
    return WhatsAppCloudAdapter(
        WhatsAppCloudConfig(
            access_token="test-token",
            phone_number_id="phone-1",
            graph_base_url="https://graph.example.test",
            api_version="v21.0",
            template_language="es",
            interactive_body_text="Elige una opción:",
            window_hours=24,
        ),
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
        window,
        lambda: NOW,
    )


def test_channel_adapters_implement_runtime_checkable_port():
    """R5: los adaptadores Telegram y WhatsApp implementan Canal."""
    telegram = TelegramChannel(FakeTelegramClient(), lambda: NOW)
    whatsapp = WhatsAppCloudChannel(FakeWhatsAppAdapter(), lambda: NOW)
    assert isinstance(telegram, Canal)
    assert isinstance(whatsapp, Canal)


def test_registry_registers_and_resolves_factory():
    """R6: register(<tipo>) hace que get(<tipo>) devuelva la factory."""
    registry = ChannelRegistry()

    @registry.register("canal_test")
    class TestFactory:
        managed_by_environment = False

    assert registry.get("canal_test") is TestFactory
    assert registry.adapter_types() == ("canal_test",)
    assert registry.creatable_types() == ("canal_test",)


def test_registry_rejects_duplicate_and_keeps_original_factory():
    """R7: un tipo duplicado falla cerrado y no reemplaza la factory original."""
    registry = ChannelRegistry()

    @registry.register("canal_test")
    class OriginalFactory:
        managed_by_environment = False

    with pytest.raises(DuplicateAdapterType):

        @registry.register("canal_test")
        class ReplacementFactory:
            managed_by_environment = False

    assert registry.get("canal_test") is OriginalFactory


@pytest.mark.parametrize("adapter_type", ["x", "Canal", "bad--slug", "9canal", "x" * 33])
def test_registry_rejects_invalid_adapter_type(adapter_type):
    """R6, R7: el registry solo admite slugs de canal únicos."""
    with pytest.raises(ValueError):
        ChannelRegistry().register(adapter_type)


def test_registry_unknown_type_raises_explicit_error():
    """R8: pedir una factory inexistente lanza UnknownAdapterType."""
    with pytest.raises(UnknownAdapterType):
        ChannelRegistry().get("canal-no-registrado")


def test_default_registry_contains_environment_and_generic_adapters():
    """R9, R31: el registry global incluye Telegram, WhatsApp, genérico, simulado
    y los canales de TikTok y Meta gestionados por el entorno."""
    assert CHANNEL_REGISTRY.adapter_types() == (
        "telegram",
        "webhook_generico",
        "whatsapp_cloud",
        "simulado",
        "gmail_api",
        "tiktok",
        "meta_messenger",
        "meta_instagram",
    )
    assert CHANNEL_REGISTRY.get("telegram") is TelegramChannel
    assert CHANNEL_REGISTRY.get("whatsapp_cloud") is WhatsAppCloudChannel
    assert CHANNEL_REGISTRY.get("simulado") is SimuladoChannel
    assert CHANNEL_REGISTRY.get("meta_messenger") is FacebookMessengerChannel
    assert CHANNEL_REGISTRY.get("meta_instagram") is InstagramMessagingChannel
    assert CHANNEL_REGISTRY.creatable_types() == (
        "webhook_generico", "simulado", "gmail_api"
    )


def test_registry_copy_is_isolated_from_default():
    """R9: un registry copiado permite registrar tipos de prueba sin tocar el global."""
    registry = CHANNEL_REGISTRY.copy()

    @registry.register("canal_test")
    class TestFactory:
        managed_by_environment = False

    assert "canal_test" in registry.adapter_types()
    assert "canal_test" not in CHANNEL_REGISTRY.adapter_types()


def test_telegram_channel_normalizes_text_non_text_and_callback_like_webhook():
    """R12: Telegram conserva las normalizaciones actuales por el puerto."""
    adapter = TelegramChannel(FakeTelegramClient(), lambda: NOW)
    text_update = {
        "update_id": 10,
        "message": {
            "message_id": 90,
            "from": {"id": 55},
            "chat": {"id": 77},
            "text": "hola",
        },
    }
    incoming = extract_incoming(text_update)
    assert incoming is not None
    assert adapter.recibir_mensaje(text_update) == normalize_incoming(incoming, NOW)

    media_update = {
        "update_id": 11,
        "message": {"from": {"id": 55}, "chat": {"id": 77}, "photo": [{}]},
    }
    media = adapter.recibir_mensaje(media_update)
    assert media is not None and media.kind == "unsupported"

    callback_update = {
        "update_id": 12,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 55},
            "message": {"chat": {"id": 77}},
            "data": "acepto:proof-1",
        },
    }
    callback = extract_callback(callback_update)
    assert callback is not None
    assert adapter.recibir_mensaje(callback_update) == normalize_callback(callback, NOW)


def test_telegram_channel_returns_none_for_invalid_updates():
    """R12: payload inválido o sin mensaje válido devuelve None, sin propagar errores."""
    adapter = TelegramChannel(FakeTelegramClient(), lambda: NOW)
    assert adapter.recibir_mensaje({"update_id": "12"}) is None
    assert adapter.recibir_mensaje({"update_id": 12, "edited_message": {}}) is None
    assert adapter.recibir_mensaje({"update_id": 12, "message": {"text": "hola"}}) is None


@pytest.mark.parametrize(
    "message",
    [
        {
            "id": "wamid-1",
            "from": "57300",
            "type": "text",
            "text": {"body": "Hola"},
        },
        {
            "id": "wamid-2",
            "from": "57300",
            "type": "interactive",
            "interactive": {"button_reply": {"id": "acepto:proof-1"}},
        },
        {"id": "wamid-3", "from": "57300", "type": "image", "image": {}},
    ],
)
def test_whatsapp_channel_uses_meta_message_normalizer(message):
    """R12: WhatsApp Cloud normaliza con la función vigente para mensajes Meta."""
    adapter = WhatsAppCloudChannel(_cloud_adapter(), lambda: NOW)
    assert adapter.recibir_mensaje(message) == normalize_message(message, NOW)


def test_whatsapp_channel_returns_none_for_invalid_meta_messages():
    """R12: un payload Meta inválido devuelve None y no propaga excepciones."""
    adapter = WhatsAppCloudChannel(_cloud_adapter(), lambda: NOW)
    assert adapter.recibir_mensaje({"from": "57300"}) is None


def test_channels_identify_external_users_with_legacy_fallbacks():
    """R13: la identidad externa usa las reglas del payload de cada proveedor."""
    telegram = TelegramChannel(FakeTelegramClient(), lambda: NOW)
    assert telegram.identificar_usuario(
        {"update_id": 1, "message": {"chat": {"id": 70}, "from": {"id": 55}}}
    ) == "55"
    assert telegram.identificar_usuario(
        {"update_id": 2, "message": {"chat": {"id": 70}, "from": {}}}
    ) == "70"
    assert telegram.identificar_usuario(
        {
            "update_id": 3,
            "callback_query": {
                "from": {"id": 56},
                "message": {"chat": {"id": 70}},
                "data": "acepto",
            },
        }
    ) == "56"
    whatsapp = WhatsAppCloudChannel(_cloud_adapter(), lambda: NOW)
    assert whatsapp.identificar_usuario({"from": "57300"}) == "57300"
    assert whatsapp.identificar_usuario({}) is None


def test_channels_send_through_existing_clients():
    """R14: el puerto delega en el cliente actual de Telegram y WhatsApp."""
    telegram_client = FakeTelegramClient()
    telegram = TelegramChannel(telegram_client, lambda: NOW)
    blocks = [TextBlock(type="text", text="Hola")]
    assert telegram.enviar_mensaje("77", blocks) == "sent"
    assert telegram_client.sent == [(77, "Hola")]

    whatsapp_client = FakeWhatsAppAdapter()
    whatsapp = WhatsAppCloudChannel(whatsapp_client, lambda: NOW)
    assert whatsapp.enviar_mensaje(DESTINATION, blocks) == "sent"
    assert whatsapp_client.sent == [(DESTINATION, blocks)]


@pytest.mark.parametrize("window_open", [False, True])
def test_channel_capabilities_preserve_provider_window(window_open):
    """R11: el puerto informa capacidades explícitas y conserva ventana de WhatsApp."""
    telegram = TelegramChannel(FakeTelegramClient(), lambda: NOW).capacidades()
    whatsapp = WhatsAppCloudChannel(
        _cloud_adapter(window_open=window_open), lambda: NOW
    ).capacidades(DESTINATION)
    for capabilities in (telegram, whatsapp):
        assert capabilities.supports_buttons is True
        assert capabilities.supports_images is False
        assert capabilities.supports_files is False
        assert capabilities.supports_audio is False
    assert whatsapp.free_text_allowed is window_open
    assert whatsapp.requires_template is (not window_open)


def test_channel_factories_report_environment_availability():
    """R9, R11: Telegram está disponible y WhatsApp sigue la inyección del adaptador."""
    telegram_context = ChannelContext(Settings(), _adapters())
    whatsapp_context = ChannelContext(Settings(), _adapters(whatsapp=FakeWhatsAppAdapter()))
    assert TelegramChannel.is_available(telegram_context) is True
    assert WhatsAppCloudChannel.is_available(telegram_context) is False
    assert WhatsAppCloudChannel.is_available(whatsapp_context) is True
    assert isinstance(
        TelegramChannel.build(_record(), telegram_context, None), Canal
    )
    assert isinstance(
        WhatsAppCloudChannel.build(
            _record("whatsapp_cloud"), whatsapp_context, None
        ),
        Canal,
    )
