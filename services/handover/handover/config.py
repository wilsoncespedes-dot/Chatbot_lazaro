"""Configuración del servicio handover leída de variables de entorno."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_HANDOVER_TIMEOUT_REPLY = (
    "Todavía no hay un asesor disponible. Tu consulta sigue registrada y te "
    "responderemos en cuanto sea posible."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_token: str = ""
    database_url: str = ""
    telegram_gateway_url: str = ""
    advisor_chat_ids: str = ""
    handover_timeout_seconds: int = Field(default=300, ge=1)
    handover_timeout_reply: str = DEFAULT_HANDOVER_TIMEOUT_REPLY
    http_timeout_seconds: float = 10

    @property
    def advisor_ids(self) -> list[int]:
        """Chat ids de `ADVISOR_CHAT_IDS`; las entradas vacías o no numéricas se descartan."""
        ids: list[int] = []
        for item in self.advisor_chat_ids.split(","):
            try:
                ids.append(int(item.strip()))
            except ValueError:
                continue
        return ids
