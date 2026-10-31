"""Constantes, tipos base y modelos comunes a todas las rutas del contrato."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

SERVICE_TOKEN_HEADER = "X-Service-Token"
# S9: límite de sendMessage de Telegram.
MAX_TEXT_LENGTH = 4096
# S2: últimos mensajes que viajan en POST /handover.
MAX_LAST_MESSAGES = 10
# S9: límites de entrada sin fijar en ninguna feature.
MAX_TOP_K = 20
MAX_IDENTIFIER_LENGTH = 64
MAX_MANUAL_NAME_LENGTH = 200

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)]
MessageText = Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_LENGTH)]


class ContractModel(BaseModel):
    """Base de los modelos del contrato: rechaza campos no declarados."""

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(ContractModel):
    """Cuerpo de todo error: {"error": "<codigo>", "message": "<texto>"}."""

    error: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
    message: Annotated[str, StringConstraints(min_length=1)]


class HealthResponse(ContractModel):
    """Respuesta de GET /health en todos los servicios."""

    status: Literal["ok"]
    service: Annotated[str, StringConstraints(min_length=1)]
