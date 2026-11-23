"""Validación pura del formulario de canales del panel admin (#66). Sin IO."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lazaro_contracts import (
    CHANNEL_ICONS,
    CHANNEL_ID_PATTERN,
    CONSENT_MODES,
    DEFAULT_CHANNEL_ICON,
    DEFAULT_CONSENT_MODE,
    MAX_CHANNEL_ID_LENGTH,
    MIN_CHANNEL_ID_LENGTH,
)
from lazaro_contracts.channel_registry import (
    CHANNEL_COLOR_PATTERN,
    CREDENTIAL_NAME_PATTERN,
    MAX_CHANNEL_CREDENTIALS,
    MAX_CHANNEL_NAME_LENGTH,
    MAX_CREDENTIAL_VALUE_LENGTH,
)

MIN_LABEL_CONTRAST = 4.5
LABEL_TEXT_COLOR = "#FFFFFF"
MAX_CALLBACK_URL_LENGTH = 2048
MAX_CONTACT_URL_LENGTH = 200


class ChannelFormError(ValueError):
    """El formulario no es válido; el mensaje es apto para mostrar al admin."""


@dataclass(frozen=True)
class ChannelForm:
    name: str
    icon: str
    color: str
    config: dict[str, str]
    credentials: dict[str, str] | None
    channel_id: str | None = None
    adapter_type: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


def _channel_luminance(hex_color: str) -> float:
    def linear(component: int) -> float:
        value = component / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast_ratio(first: str, second: str) -> float:
    """Razón de contraste WCAG 2.x entre dos colores `#RRGGBB`."""
    high, low = sorted((_channel_luminance(first), _channel_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def valid_color(value: str) -> bool:
    """R16: `#RRGGBB` con contraste ≥ 4.5:1 frente al texto blanco de la etiqueta."""
    if re.fullmatch(CHANNEL_COLOR_PATTERN, value) is None:
        return False
    return contrast_ratio(value, LABEL_TEXT_COLOR) >= MIN_LABEL_CONTRAST


def icon_glyph(icon: str) -> str:
    """R31: emoji del ícono; uno guardado fuera de la lista se muestra como `chat`."""
    return CHANNEL_ICONS.get(icon, CHANNEL_ICONS[DEFAULT_CHANNEL_ICON])


def parse_credentials(text: str) -> dict[str, str]:
    """R17: una credencial `nombre=valor` por línea; las líneas vacías se ignoran."""
    credentials: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or re.fullmatch(CREDENTIAL_NAME_PATTERN, name) is None:
            raise ChannelFormError("Cada credencial va en una línea como nombre=valor.")
        if not value or len(value) > MAX_CREDENTIAL_VALUE_LENGTH:
            raise ChannelFormError("El valor de una credencial no es válido.")
        if name in credentials:
            raise ChannelFormError("Hay credenciales repetidas.")
        credentials[name] = value
    if len(credentials) > MAX_CHANNEL_CREDENTIALS:
        raise ChannelFormError("Hay demasiadas credenciales.")
    return credentials


def channel_form(
    form: dict[str, str],
    *,
    creating: bool,
    current_config: dict | None = None,
    managed: bool = False,
) -> ChannelForm:
    """R13–R17: valida y normaliza el formulario de alta o edición."""
    name = form.get("name", "").strip()
    if not name or len(name) > MAX_CHANNEL_NAME_LENGTH or any(ord(c) < 32 for c in name):
        raise ChannelFormError("El nombre es obligatorio y admite hasta 60 caracteres.")
    icon = form.get("icon", "")
    if icon not in CHANNEL_ICONS:
        raise ChannelFormError("El ícono debe ser uno de la lista.")
    color = form.get("color", "").strip()
    if not valid_color(color):
        raise ChannelFormError(
            "El color debe ser #RRGGBB y tener contraste suficiente con texto blanco."
        )
    consent_mode = form.get("consent_mode", DEFAULT_CONSENT_MODE)
    if consent_mode not in CONSENT_MODES:
        raise ChannelFormError("El modo de consentimiento no es válido.")
    config = dict(current_config or {})
    config["consent_mode"] = consent_mode
    if "public" in form:
        if form.get("public") == "si":
            config["public"] = "true"
        else:
            config.pop("public", None)
    elif not creating:
        config.pop("public", None)
    if "contact_url" in form:
        contact_url = form.get("contact_url", "").strip()
        if contact_url:
            if (
                not contact_url.startswith("https://")
                or len(contact_url) > MAX_CONTACT_URL_LENGTH
            ):
                raise ChannelFormError(
                    "El enlace de contacto debe empezar por https:// y tener "
                    "200 caracteres como máximo."
                )
            config["contact_url"] = contact_url
        else:
            config.pop("contact_url", None)
    elif not creating:
        config.pop("contact_url", None)
    email_address = form.get("email_address", "").strip()
    if email_address:
        if (
            len(email_address) > 128
            or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email_address) is None
        ):
            raise ChannelFormError("El correo del canal debe ser válido.")
        config["email_address"] = email_address
    elif not creating:
        config.pop("email_address", None)
    callback_url = form.get("callback_url", "").strip()
    if not managed:
        if callback_url:
            if not callback_url.startswith("https://") or len(callback_url) > MAX_CALLBACK_URL_LENGTH:
                raise ChannelFormError("La URL de callback debe empezar por https://.")
            config["callback_url"] = callback_url
        elif form.get("clear_callback_url") == "si":
            config.pop("callback_url", None)
    credentials: dict[str, str] | None = None
    raw_credentials = form.get("credentials", "")
    if raw_credentials.strip() and not managed:
        credentials = parse_credentials(raw_credentials)
    if not creating:
        return ChannelForm(name, icon, color, config, credentials)
    channel_id = form.get("id", "").strip()
    if (
        not MIN_CHANNEL_ID_LENGTH <= len(channel_id) <= MAX_CHANNEL_ID_LENGTH
        or re.fullmatch(CHANNEL_ID_PATTERN, channel_id) is None
    ):
        raise ChannelFormError(
            "El id admite de 2 a 32 minúsculas, dígitos y separadores - o _."
        )
    adapter_type = form.get("adapter_type", "").strip()
    if not adapter_type:
        raise ChannelFormError("Elige un tipo de adaptador.")
    return ChannelForm(
        name, icon, color, config, credentials or {}, channel_id, adapter_type
    )


def webhook_url(base: str, channel_id: str) -> tuple[str, bool]:
    """R20: URL del webhook de entrada y si la base pública está configurada."""
    path = f"/webhooks/{channel_id}"
    base = base.strip().rstrip("/")
    if base.startswith("https://") and len(base) > len("https://"):
        return base + path, True
    return path, False
