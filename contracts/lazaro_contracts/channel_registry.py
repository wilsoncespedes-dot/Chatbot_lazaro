"""Modelos de contrato para el registro y la administración de canales."""
from __future__ import annotations

from typing import Annotated

from pydantic import (
    AwareDatetime,
    AfterValidator,
    Field,
    JsonValue,
    StrictBool,
    StringConstraints,
    model_validator,
)

from .channels import (
    Channel,
    ChannelCapabilities,
    check_json_object,
)
from .common import ContractModel

MAX_CHANNEL_NAME_LENGTH = 60
MAX_CHANNEL_ICON_LENGTH = 32
CHANNEL_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
MAX_CHANNEL_CONFIG_BYTES = 4096
MAX_CHANNEL_CONFIG_DEPTH = 5
MAX_CHANNEL_CREDENTIALS = 20
CREDENTIAL_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
MAX_CREDENTIAL_VALUE_LENGTH = 4096
CHANNEL_SECRET_PATTERN = r"^[A-Za-z0-9_-]{43}$"
CONSENT_MODES = ("texto", "boton")
DEFAULT_CONSENT_MODE = "texto"


def _check_display_text(value: str) -> str:
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ValueError("el texto no puede contener caracteres de control")
    return value


def _check_name(value: str) -> str:
    if not value.strip():
        raise ValueError("name no puede contener solo espacios")
    return _check_display_text(value)


def _check_config(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return check_json_object(value, MAX_CHANNEL_CONFIG_BYTES, MAX_CHANNEL_CONFIG_DEPTH)


def _check_request_config(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    value = _check_config(value)
    if "consent_mode" in value and value["consent_mode"] not in CONSENT_MODES:
        raise ValueError("consent_mode debe ser 'texto' o 'boton'")
    return value


ChannelName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_CHANNEL_NAME_LENGTH),
    AfterValidator(_check_name),
]
ChannelIcon = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_CHANNEL_ICON_LENGTH),
    AfterValidator(_check_display_text),
]
ChannelColor = Annotated[
    str,
    StringConstraints(pattern=CHANNEL_COLOR_PATTERN),
]
ChannelConfig = Annotated[dict[str, JsonValue], AfterValidator(_check_config)]
# En peticiones de alta/edición además se valida consent_mode. Al leer
# (ChannelInfo) no se valida: un valor guardado inválido se trata como «texto».
ChannelRequestConfig = Annotated[dict[str, JsonValue], AfterValidator(_check_request_config)]
CredentialName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=CREDENTIAL_NAME_PATTERN),
]
CredentialValue = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_CREDENTIAL_VALUE_LENGTH),
]
ChannelSecret = Annotated[
    str,
    StringConstraints(min_length=43, max_length=43, pattern=CHANNEL_SECRET_PATTERN),
]


class ChannelInfo(ContractModel):
    id: Channel
    name: ChannelName
    adapter_type: Channel
    icon: ChannelIcon
    color: ChannelColor
    config: ChannelConfig
    active: bool
    configured: bool
    has_secrets: bool
    managed_by_environment: bool
    created_at: AwareDatetime
    capabilities: ChannelCapabilities | None = None


class ChannelListResponse(ContractModel):
    channels: list[ChannelInfo]
    adapter_types: list[Channel]


class ChannelCreateRequest(ContractModel):
    id: Channel
    name: ChannelName
    adapter_type: Channel
    icon: ChannelIcon
    color: ChannelColor
    config: ChannelRequestConfig = Field(default_factory=dict)
    credentials: dict[CredentialName, CredentialValue] = Field(
        default_factory=dict, max_length=MAX_CHANNEL_CREDENTIALS
    )
    active: StrictBool = True


class ChannelCreateResponse(ContractModel):
    channel: ChannelInfo
    secret: ChannelSecret


class ChannelUpdateRequest(ContractModel):
    name: ChannelName | None = None
    icon: ChannelIcon | None = None
    color: ChannelColor | None = None
    config: ChannelRequestConfig | None = None
    credentials: dict[CredentialName, CredentialValue] | None = Field(
        default=None, max_length=MAX_CHANNEL_CREDENTIALS
    )

    @model_validator(mode="after")
    def _require_updates(self) -> "ChannelUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("se requiere al menos un campo para actualizar")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("los campos enviados no pueden ser null")
        return self


class ChannelActiveRequest(ContractModel):
    active: StrictBool


class ChannelSecretResponse(ContractModel):
    channel_id: Channel
    secret: ChannelSecret
