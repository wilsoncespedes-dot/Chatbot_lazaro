"""Adaptadores registrados como implementaciones del puerto Canal."""
from .telegram import TelegramChannel
from .webhook_generico import WebhookGenericoChannel
from .whatsapp_cloud import WhatsAppCloudChannel
from .simulado import SimuladoChannel
from .tiktok import TikTokChannel
from .meta_messenger import FacebookMessengerChannel, InstagramMessagingChannel

__all__ = [
    "TelegramChannel",
    "WebhookGenericoChannel",
    "WhatsAppCloudChannel",
    "SimuladoChannel",
    "TikTokChannel",
    "FacebookMessengerChannel",
    "InstagramMessagingChannel",
]
