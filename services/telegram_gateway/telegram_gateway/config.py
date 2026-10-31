"""Configuración del servicio telegram_gateway leída de variables de entorno."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_bot_token: str = ""
    redis_url: str = "redis://redis:6379/0"
    orchestrator_url: str = "http://orchestrator:8000"
    dedup_ttl_seconds: int = 86400
    http_timeout_seconds: float = 10
    non_text_reply: str = "Por ahora solo puedo leer mensajes de texto."
