"""Política de canal derivada de lo que informa el gateway (#65). Puro, sin IO.

El núcleo del orquestador decide por capacidades y ajustes del canal, nunca por
su nombre: un canal *con ventana* es el que informa `free_text_allowed=false` y
`requires_template=true`; el modo de consentimiento sale de `config.consent_mode`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lazaro_contracts import CONSENT_MODES, DEFAULT_CONSENT_MODE, ChannelInfo

ConsentMode = Literal["texto", "boton"]
SIMULATED_ADAPTER_TYPE = "simulado"
SIMULATED_SUFFIX = "[SIMULADO]"

__all__ = [
    "DEFAULT_CONSENT_MODE",
    "ChannelPolicy",
    "ConsentMode",
    "SIMULATED_ADAPTER_TYPE",
    "SIMULATED_SUFFIX",
    "consent_mode",
    "default_policy",
    "is_windowed",
    "policy_from_info",
    "simulated_label",
]


def simulated_label(name: str) -> str:
    """Etiqueta del canal con la palabra SIMULADO, sin duplicarla."""
    label = (name or "").strip()
    if label.upper().endswith(SIMULATED_SUFFIX):
        return f"{label[: -len(SIMULATED_SUFFIX)].rstrip()} {SIMULATED_SUFFIX}"
    return f"{label} {SIMULATED_SUFFIX}"


@dataclass(frozen=True)
class ChannelPolicy:
    id: str
    name: str
    icon: str
    color: str
    active: bool
    windowed: bool
    consent_mode: ConsentMode
    supports_images: bool = False
    known: bool = True
    # #73: la bienvenida solo lista canales activos y marcados como públicos.
    public: bool = False
    contact_url: str = ""
    simulated: bool = False

    @property
    def text_consent(self) -> bool:
        return self.consent_mode == "texto"


def is_windowed(info: ChannelInfo) -> bool:
    """R11/R12: con ventana solo si las capacidades lo dicen explícitamente."""
    capabilities = info.capabilities
    return (
        capabilities is not None
        and not capabilities.free_text_allowed
        and capabilities.requires_template
    )


def consent_mode(info: ChannelInfo) -> ConsentMode:
    """R13 y S3: `config.consent_mode` válido o `texto`."""
    value = info.config.get("consent_mode")
    if isinstance(value, str) and value in CONSENT_MODES:
        return value  # type: ignore[return-value]
    return DEFAULT_CONSENT_MODE  # type: ignore[return-value]


def _config_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "si", "sí", "1", "on")
    return False


def policy_from_info(info: ChannelInfo) -> ChannelPolicy:
    return ChannelPolicy(
        id=info.id,
        name=info.name,
        icon=info.icon,
        color=info.color,
        active=info.active,
        windowed=is_windowed(info),
        consent_mode=consent_mode(info),
        supports_images=bool(
            info.capabilities is not None and info.capabilities.supports_images
        ),
        public=_config_flag(info.config.get("public")),
        contact_url=str(info.config.get("contact_url", "") or ""),
        simulated=info.adapter_type == SIMULATED_ADAPTER_TYPE,
    )


def default_policy(channel_id: str) -> ChannelPolicy:
    """R14: un id ausente del directorio es sin ventana, `texto` y se nombra por su id."""
    return ChannelPolicy(
        id=channel_id,
        name=channel_id,
        icon="chat",
        color="#5B6470",
        active=True,
        windowed=False,
        consent_mode=DEFAULT_CONSENT_MODE,  # type: ignore[arg-type]
        supports_images=False,
        known=False,
    )
