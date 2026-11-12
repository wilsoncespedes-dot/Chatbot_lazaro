"""Constantes, tipos base y modelos comunes a todas las rutas del contrato."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

SERVICE_TOKEN_HEADER = "X-Service-Token"
# S9: límite de sendMessage de Telegram.
MAX_TEXT_LENGTH = 4096
# S2: últimos mensajes que viajan en POST /handover.
MAX_LAST_MESSAGES = 10
# S9: límites de entrada sin fijar en ninguna feature.
MAX_TOP_K = 20
MAX_IDENTIFIER_LENGTH = 64
MAX_MANUAL_NAME_LENGTH = 200
# S14: límite por defecto y máximo del listado de casos de un asesor.
DEFAULT_CASE_LIST_LIMIT = 50
MAX_CASE_LIST_LIMIT = 200

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
    """Respuesta de GET /health en todos los servicios.

    `dependencies` solo aparece cuando una dependencia crítica no responde y el
    servicio devuelve HTTP 503; nunca incluye URLs, credenciales ni DSN.
    """

    status: Literal["ok", "unhealthy"]
    service: Annotated[str, StringConstraints(min_length=1)]
    dependencies: dict[str, Literal["unavailable"]] | None = None

    @model_validator(mode="after")
    def _validate_dependencies_consistency(self) -> "HealthResponse":
        """R2: unhealthy exige dependencias fallidas; ok no las admite."""
        if self.status == "unhealthy":
            if not self.dependencies:
                raise ValueError(
                    "status 'unhealthy' requires a non-empty dependencies map"
                )
        elif self.dependencies is not None:
            raise ValueError("status 'ok' must not include dependencies")
        return self
