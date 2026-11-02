"""Configuración del servicio telegram_gateway leída de variables de entorno."""
from __future__ import annotations

from lazaro_contracts.production import (
    ProductionConfigError,
    is_valid_webhook_secret,
    normalize_service_url,
    parse_app_env,
    production_problems,
)
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_IN_PRODUCTION = (
    "SERVICE_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "REDIS_URL",
    "ORCHESTRATOR_URL",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    service_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_bot_token: str = ""
    redis_url: str = "redis://redis:6379/0"
    orchestrator_url: str = "http://orchestrator:8000"
    dedup_ttl_seconds: int = 86400
    http_timeout_seconds: float = 10
    non_text_reply: str = "Por ahora solo puedo leer mensajes de texto."

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        self.app_env = parse_app_env(self.app_env)
        self.orchestrator_url = normalize_service_url(self.orchestrator_url)
        if self.app_env != "production":
            return self
        problems = production_problems(self.model_dump(), REQUIRED_IN_PRODUCTION)
        if (
            "TELEGRAM_WEBHOOK_SECRET" not in problems
            and not is_valid_webhook_secret(self.telegram_webhook_secret)
        ):
            problems.append("TELEGRAM_WEBHOOK_SECRET")
        if problems:
            raise ProductionConfigError(problems)
        return self
