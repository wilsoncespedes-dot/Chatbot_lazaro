"""Configuración del servicio telegram_gateway leída de variables de entorno."""
from __future__ import annotations

import re

from lazaro_contracts import DEFAULT_SIGNATURE_WINDOW_SECONDS
from lazaro_contracts.production import (
    ProductionConfigError,
    is_valid_webhook_secret,
    normalize_service_url,
    parse_app_env,
    production_problems,
)
from pydantic import Field, SecretStr, field_validator, model_validator
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
    database_url: str = ""
    channel_secrets_key: SecretStr = SecretStr("")
    redis_url: str = "redis://redis:6379/0"
    orchestrator_url: str = "http://orchestrator:8000"
    dedup_ttl_seconds: int = 86400
    healthcheck_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    http_timeout_seconds: float = 10
    telegram_answer_callback_timeout_seconds: float = 3.0
    message_grouping_enabled: bool = True
    message_grouping_window_seconds: float = 2.0
    message_grouping_max_wait_seconds: float = 8.0
    message_grouping_max_messages: int = 10
    message_grouping_buffer_ttl_seconds: int = 300
    message_grouping_lease_seconds: float = 30.0
    message_grouping_max_attempts: int = 3
    message_grouping_poll_seconds: float = 0.5
    message_grouping_accept_phrase: str = ""
    message_grouping_reject_phrase: str = ""

    # WhatsApp Cloud API (#43)
    whatsapp_enabled: bool = False
    whatsapp_access_token: SecretStr = SecretStr("")
    whatsapp_app_secret: SecretStr = SecretStr("")
    whatsapp_verify_token: SecretStr = SecretStr("")
    whatsapp_phone_number_id: str = ""
    whatsapp_graph_base_url: str = "https://graph.facebook.com"
    whatsapp_graph_api_version: str = "v21.0"
    whatsapp_template_language: str = "es"
    whatsapp_interactive_body_text: str = "Elige una opción:"
    whatsapp_window_hours: int = 24

    # TikTok Business Messaging (fase 6). Acceso sujeto a autorización de TikTok.
    tiktok_enabled: bool = False
    tiktok_client_key: str = ""
    tiktok_client_secret: SecretStr = SecretStr("")
    # Secreto con el que se verifica `TikTok-Signature`. Vacío = se rechaza todo
    # webhook de TikTok con 401 (fallo cerrado), aunque el canal esté habilitado.
    tiktok_webhook_secret: SecretStr = SecretStr("")
    # `open_id` devuelto por el OAuth de la cuenta de TikTok.
    tiktok_business_id: str = ""
    # Solo para el primer arranque: después el refresh token rotado vive cifrado
    # en `canales.config_secreta` y es el que se usa.
    tiktok_refresh_token: SecretStr = SecretStr("")
    tiktok_token_url: str = (
        "https://business-api.tiktok.com/open_api/v1.3/tt_user/oauth2/refresh_token/"
    )
    tiktok_send_url: str = (
        "https://business-api.tiktok.com/open_api/v1.3/business/message/send/"
    )
    tiktok_token_refresh_margin_seconds: int = Field(300, ge=30, le=3600)
    tiktok_signature_tolerance_seconds: int = Field(300, ge=30, le=3600)

    # Webhook genérico firmado (#62)
    webhook_signature_window_seconds: int = Field(
        DEFAULT_SIGNATURE_WINDOW_SECONDS, ge=1, le=3600
    )
    webhook_max_body_bytes: int = Field(1_048_576, ge=1024, le=10_485_760)
    webhook_allow_private_callbacks: bool = False

    # Buzón del canal simulado (#63): solo pruebas, retención y tope por canal.
    simulated_mailbox_retention_seconds: int = Field(3600, ge=60, le=86400)
    simulated_mailbox_max_entries: int = Field(500, ge=10, le=5000)

    # Fase 2: cola de reintento hacia el orquestador (espera creciente).
    inbound_retry_base_seconds: float = Field(2.0, gt=0, le=60)
    inbound_retry_max_delay_seconds: float = Field(300.0, gt=0, le=3600)
    inbound_retry_max_age_seconds: int = Field(172_800, ge=60, le=1_209_600)
    inbound_retry_poll_seconds: float = Field(1.0, gt=0, le=60)
    inbound_retry_lease_seconds: float = Field(60.0, gt=0, le=3600)
    inbound_retry_batch_size: int = Field(50, ge=1, le=500)

    @field_validator("telegram_answer_callback_timeout_seconds")
    @classmethod
    def _validate_answer_callback_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(
                "TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS debe ser mayor que 0"
            )
        return value

    @field_validator("whatsapp_graph_base_url")
    @classmethod
    def _normalize_graph_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("whatsapp_graph_api_version")
    @classmethod
    def _validate_graph_api_version(cls, value: str) -> str:
        if not re.fullmatch(r"v\d+\.\d+", value):
            raise ValueError("WHATSAPP_GRAPH_API_VERSION no tiene el formato v<mayor>.<menor>")
        return value

    @field_validator("whatsapp_template_language")
    @classmethod
    def _validate_template_language(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z]{2}(_[A-Z]{2})?", value):
            raise ValueError("WHATSAPP_TEMPLATE_LANGUAGE no tiene un formato válido")
        return value

    @field_validator("whatsapp_interactive_body_text")
    @classmethod
    def _validate_interactive_body_text(cls, value: str) -> str:
        if not 1 <= len(value) <= 1024:
            raise ValueError("WHATSAPP_INTERACTIVE_BODY_TEXT debe tener entre 1 y 1024 caracteres")
        return value

    @field_validator("whatsapp_window_hours")
    @classmethod
    def _validate_window_hours(cls, value: int) -> int:
        if not 1 <= value <= 24:
            raise ValueError("WHATSAPP_WINDOW_HOURS debe estar entre 1 y 24")
        return value

    @model_validator(mode="after")
    def _validate_whatsapp(self) -> "Settings":
        if not self.whatsapp_enabled:
            return self
        missing: list[str] = []
        if not self.whatsapp_access_token.get_secret_value():
            missing.append("WHATSAPP_ACCESS_TOKEN")
        if not self.whatsapp_app_secret.get_secret_value():
            missing.append("WHATSAPP_APP_SECRET")
        if not self.whatsapp_verify_token.get_secret_value():
            missing.append("WHATSAPP_VERIFY_TOKEN")
        if not self.whatsapp_phone_number_id:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if missing:
            raise ValueError(
                "configuración de WhatsApp incompleta: faltan " + ", ".join(missing)
            )
        return self

    @model_validator(mode="after")
    def _validate_tiktok(self) -> "Settings":
        """R1: el canal solo arranca habilitado con credenciales y cifrado disponibles."""
        if not self.tiktok_enabled:
            return self
        missing: list[str] = []
        if not self.tiktok_client_key:
            missing.append("TIKTOK_CLIENT_KEY")
        if not self.tiktok_client_secret.get_secret_value():
            missing.append("TIKTOK_CLIENT_SECRET")
        if not self.tiktok_business_id:
            missing.append("TIKTOK_BUSINESS_ID")
        if not self.channel_secrets_key.get_secret_value():
            missing.append("CHANNEL_SECRETS_KEY")
        for name, url in (
            ("TIKTOK_TOKEN_URL", self.tiktok_token_url),
            ("TIKTOK_SEND_URL", self.tiktok_send_url),
        ):
            if not url.startswith("https://"):
                missing.append(name)
        if missing:
            raise ValueError(
                "configuración de TikTok incompleta: faltan " + ", ".join(missing)
            )
        return self

    @model_validator(mode="after")
    def _validate_message_grouping(self) -> "Settings":
        problems: list[str] = []
        if self.message_grouping_window_seconds <= 0:
            problems.append("MESSAGE_GROUPING_WINDOW_SECONDS")
        if self.message_grouping_max_wait_seconds < self.message_grouping_window_seconds:
            problems.append("MESSAGE_GROUPING_MAX_WAIT_SECONDS")
        if self.message_grouping_max_messages < 1:
            problems.append("MESSAGE_GROUPING_MAX_MESSAGES")
        if self.message_grouping_max_attempts < 1:
            problems.append("MESSAGE_GROUPING_MAX_ATTEMPTS")
        if self.message_grouping_poll_seconds <= 0:
            problems.append("MESSAGE_GROUPING_POLL_SECONDS")
        if self.message_grouping_lease_seconds <= self.http_timeout_seconds:
            problems.append("MESSAGE_GROUPING_LEASE_SECONDS")
        if self.message_grouping_buffer_ttl_seconds <= (
            self.message_grouping_max_wait_seconds + self.message_grouping_lease_seconds
        ):
            problems.append("MESSAGE_GROUPING_BUFFER_TTL_SECONDS")
        if problems:
            raise ValueError(
                "configuración de agrupación inválida: " + ", ".join(problems)
            )
        return self

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

    @model_validator(mode="after")
    def _validate_webhook_callbacks(self) -> "Settings":
        if self.app_env == "production" and self.webhook_allow_private_callbacks:
            raise ProductionConfigError(["WEBHOOK_ALLOW_PRIVATE_CALLBACKS"])
        return self
