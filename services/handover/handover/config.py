"""Configuración del servicio handover leída de variables de entorno."""
from __future__ import annotations

import re

from lazaro_contracts import DEFAULT_CASE_LIST_LIMIT, MAX_CASE_LIST_LIMIT
from lazaro_contracts.production import (
    ProductionConfigError,
    normalize_service_url,
    parse_app_env,
    production_problems,
)
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_HANDOVER_TIMEOUT_REPLY = (
    "Todavía no hay un asesor disponible. Tu consulta sigue registrada y te "
    "responderemos en cuanto sea posible."
)

REQUIRED_IN_PRODUCTION = (
    "SERVICE_TOKEN",
    "DATABASE_URL",
    "TELEGRAM_GATEWAY_URL",
    "PRIVACY_RETENTION_DAYS",
    "PRIVACY_ACTIVE_CASE_MAX_DAYS",
)

_INTEGER_PATTERN = re.compile(r"-?[0-9]+")


def parse_advisor_chat_ids(raw: str) -> list[int]:
    """Ids de ADVISOR_CHAT_IDS en orden; lanza ValueError si una entrada no es válida."""
    ids: list[int] = []
    seen: dict[int, int] = {}
    for position, item in enumerate(raw.split(","), start=1):
        entry = item.strip()
        if entry == "":
            continue
        if not _INTEGER_PATTERN.fullmatch(entry):
            raise ValueError(
                f"ADVISOR_CHAT_IDS: la entrada {position} ('{entry}') no es un entero"
            )
        value = int(entry)
        if value in seen:
            raise ValueError(
                f"ADVISOR_CHAT_IDS: la entrada {position} repite el id de la entrada "
                f"{seen[value]}"
            )
        seen[value] = position
        ids.append(value)
    return ids


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    service_token: str = ""
    database_url: str = ""
    telegram_gateway_url: str = ""
    advisor_chat_ids: str = ""
    handover_timeout_seconds: int = Field(default=300, ge=1)
    handover_timeout_reply: str = DEFAULT_HANDOVER_TIMEOUT_REPLY
    case_list_limit: int = Field(
        default=DEFAULT_CASE_LIST_LIMIT, ge=1, le=MAX_CASE_LIST_LIMIT
    )
    http_timeout_seconds: float = 10
    privacy_retention_days: str = ""
    privacy_active_case_max_days: str = ""

    @field_validator("advisor_chat_ids")
    @classmethod
    def _validate_advisor_chat_ids(cls, value: str) -> str:
        parse_advisor_chat_ids(value)
        return value

    @field_validator("privacy_retention_days", "privacy_active_case_max_days")
    @classmethod
    def _validate_privacy_days(cls, value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        try:
            days = int(text)
        except ValueError:
            raise ValueError("debe ser un entero >= 1") from None
        if days < 1:
            raise ValueError("debe ser un entero >= 1")
        return text

    @model_validator(mode="after")
    def _validate_active_case_limit(self) -> "Settings":
        if (
            self.privacy_retention_days
            and self.privacy_active_case_max_days
            and int(self.privacy_active_case_max_days) >= int(self.privacy_retention_days)
        ):
            raise ValueError(
                "PRIVACY_ACTIVE_CASE_MAX_DAYS debe ser menor que PRIVACY_RETENTION_DAYS"
            )
        return self

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        self.app_env = parse_app_env(self.app_env)
        self.telegram_gateway_url = normalize_service_url(self.telegram_gateway_url)
        if self.app_env != "production":
            return self
        problems = production_problems(self.model_dump(), REQUIRED_IN_PRODUCTION)
        if problems:
            raise ProductionConfigError(problems)
        return self

    @property
    def advisor_ids(self) -> list[int]:
        """Chat ids de `ADVISOR_CHAT_IDS` ya validados al construir `Settings`."""
        return parse_advisor_chat_ids(self.advisor_chat_ids)

    @property
    def retention_days(self) -> int | None:
        if not self.privacy_retention_days:
            return None
        return int(self.privacy_retention_days)

    @property
    def active_case_max_days(self) -> int | None:
        if not self.privacy_active_case_max_days:
            return None
        return int(self.privacy_active_case_max_days)

    @property
    def retention_configured(self) -> bool:
        return self.retention_days is not None and self.active_case_max_days is not None
