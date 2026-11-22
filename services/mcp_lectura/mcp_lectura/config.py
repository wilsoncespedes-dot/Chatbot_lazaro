"""Configuración del servidor MCP de solo lectura leída de variables de entorno."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    service_token: str = ""
    rag_url: str = ""
    # Si MCP_DATABASE_URL está vacío se reutiliza DATABASE_URL.
    database_url: str = ""
    mcp_database_url: str = ""
    mcp_demo_seed: bool = False
    mcp_max_rows: int = Field(default=20, ge=1, le=100)
    http_timeout_seconds: float = Field(default=10, gt=0, le=60)

    @property
    def effective_database_url(self) -> str:
        return self.mcp_database_url.strip() or self.database_url.strip()
