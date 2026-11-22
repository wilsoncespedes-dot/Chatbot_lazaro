"""Modelos comunes de canal: mensaje normalizado, capacidades y respuesta abstracta."""
from __future__ import annotations

import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    JsonValue,
    RootModel,
    StringConstraints,
    model_validator,
)

from .common import ContractModel, MessageText

CHANNEL_ID_PATTERN = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"
MIN_CHANNEL_ID_LENGTH = 2
MAX_CHANNEL_ID_LENGTH = 32
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_SIZE_BYTES = 2 * 1024**3
MAX_MIME_TYPE_LENGTH = 255
MAX_ATTACHMENT_NAME_LENGTH = 255
MAX_METADATA_BYTES = 4096
MAX_METADATA_DEPTH = 5
MAX_URL_LENGTH = 2048
MAX_IMAGE_ALT_LENGTH = 1024
MIME_TYPE_PATTERN = (
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*"
    r"(?:;[ -~]*)?$"
)

Channel = Annotated[
    str,
    StringConstraints(
        min_length=MIN_CHANNEL_ID_LENGTH,
        max_length=MAX_CHANNEL_ID_LENGTH,
        pattern=CHANNEL_ID_PATTERN,
    ),
]
MessageKind = Literal["text", "button", "unsupported", "image", "file", "audio"]
AttachmentKind = Literal["image", "file", "audio"]
MessageDirection = Literal["inbound", "outbound"]
DeliveryStatus = Literal["sent", "delivered", "read", "failed"]

# Especificación, «Respuesta abstracta»: opciones máximo 3 y 20 caracteres;
# lista de 4 a 10 opciones.
MAX_OPTION_COUNT = 3
MAX_OPTION_LENGTH = 20
MIN_LIST_OPTIONS = 4
MAX_LIST_OPTIONS = 10
MAX_EXTERNAL_ID_LENGTH = 128

ExternalIdentifier = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_EXTERNAL_ID_LENGTH)
]
OptionLabel = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_OPTION_LENGTH)
]
ListItem = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_EXTERNAL_ID_LENGTH)
]


def _check_https_url(value: str) -> str:
    """R13, R23: URL https, sin espacios, controles ni credenciales."""
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("la URL no es válida")
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ValueError("la URL no es válida") from exc
    if parts.scheme.lower() != "https" or not parts.hostname or "@" in parts.netloc:
        raise ValueError("la URL no es válida")
    return value


HttpsUrl = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_URL_LENGTH),
    AfterValidator(_check_https_url),
]


def _check_attachment_name(value: str) -> str:
    """R11: un nombre de archivo no es una ruta ni contiene controles."""
    if "/" in value or "\\" in value:
        raise ValueError("el nombre del adjunto no es válido")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("el nombre del adjunto no es válido")
    return value


def _json_depth(value: JsonValue) -> int:
    """R15, R17: el objeto raíz cuenta 1 y cada objeto o lista anidada suma 1."""
    max_depth = 1
    stack: list[tuple[JsonValue, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if isinstance(current, dict):
            max_depth = max(max_depth, depth)
            stack.extend(
                (child, depth + 1)
                for child in current.values()
                if isinstance(child, (dict, list))
            )
        elif isinstance(current, list):
            max_depth = max(max_depth, depth)
            stack.extend(
                (child, depth + 1)
                for child in current
                if isinstance(child, (dict, list))
            )
    return max_depth


def check_json_object(
    value: dict[str, JsonValue], max_bytes: int, max_depth: int
) -> dict[str, JsonValue]:
    """Valida el tamaño y la profundidad de un objeto JSON compacto."""
    try:
        size = len(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("el valor debe ser un objeto JSON") from exc
    if size > max_bytes:
        raise ValueError("el objeto JSON supera el tamaño máximo")
    if _json_depth(value) > max_depth:
        raise ValueError("el objeto JSON supera la profundidad máxima")
    return value


def _check_metadata(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """R15, R16, R17: JSON compacto de hasta 4096 bytes y profundidad 5."""
    try:
        return check_json_object(value, MAX_METADATA_BYTES, MAX_METADATA_DEPTH)
    except ValueError as exc:
        message = str(exc)
        if message == "el valor debe ser un objeto JSON":
            message = "metadata debe ser JSON"
        elif message == "el objeto JSON supera el tamaño máximo":
            message = "metadata supera el tamaño máximo"
        elif message == "el objeto JSON supera la profundidad máxima":
            message = "metadata supera la profundidad máxima"
        raise ValueError(message) from exc


class Attachment(ContractModel):
    """Metadatos de un adjunto; nunca el binario (extra="forbid")."""

    type: AttachmentKind
    mime_type: Annotated[
        str,
        StringConstraints(
            min_length=3,
            max_length=MAX_MIME_TYPE_LENGTH,
            pattern=MIME_TYPE_PATTERN,
        ),
    ]
    name: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=MAX_ATTACHMENT_NAME_LENGTH),
            AfterValidator(_check_attachment_name),
        ]
        | None
    ) = None
    size_bytes: (
        Annotated[int, Field(ge=0, le=MAX_ATTACHMENT_SIZE_BYTES)] | None
    ) = None
    url: HttpsUrl | None = None


class NormalizedMessage(ContractModel):
    """Mensaje entrante ya traducido por un adaptador de canal.

    La identidad interna (`client_id`) no viaja desde los adaptadores: la
    resolverá el flujo de identidad posterior.
    """

    channel: Channel
    external_user_id: ExternalIdentifier
    external_chat_id: ExternalIdentifier
    external_message_id: ExternalIdentifier
    kind: MessageKind
    text: MessageText | None = None
    button_id: ExternalIdentifier | None = None
    # S15: prueba HMAC de la versión/hash del aviso que originó el botón.
    button_proof: ExternalIdentifier | None = None
    received_at: AwareDatetime
    direction: MessageDirection = Field(
        default="inbound", exclude_if=lambda value: value == "inbound"
    )
    attachments: list[Attachment] = Field(
        default_factory=list,
        max_length=MAX_ATTACHMENTS,
        exclude_if=lambda value: not value,
    )
    metadata: Annotated[
        dict[str, JsonValue], AfterValidator(_check_metadata)
    ] = Field(default_factory=dict, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def _content_matches_kind(self) -> "NormalizedMessage":
        if self.kind == "text" and not self.text:
            raise ValueError("kind=text exige text")
        if self.kind == "button" and not self.button_id:
            raise ValueError("kind=button exige button_id")
        if self.button_proof is not None and self.kind != "button":
            raise ValueError("button_proof solo existe en kind=button")
        if self.kind in ("image", "file", "audio") and not self.attachments:
            raise ValueError("un tipo multimedia exige al menos un adjunto")
        if self.kind in ("image", "file", "audio") and any(
            attachment.type != self.kind for attachment in self.attachments
        ):
            raise ValueError("el tipo del adjunto debe coincidir con kind")
        if self.kind in ("text", "button", "unsupported") and self.attachments:
            raise ValueError("solo los tipos multimedia llevan adjuntos")
        if self.direction == "outbound" and self.kind in ("button", "unsupported"):
            raise ValueError("un mensaje saliente no puede ser button ni unsupported")
        return self


class TextBlock(ContractModel):
    type: Literal["text"]
    text: MessageText


class OptionsBlock(ContractModel):
    type: Literal["options"]
    options: Annotated[list[OptionLabel], Field(min_length=1, max_length=MAX_OPTION_COUNT)]
    # S15: metadatos opcionales para que el canal pinte botones interactivos.
    option_ids: list[ExternalIdentifier] | None = None
    option_proofs: list[ExternalIdentifier] | None = None

    @model_validator(mode="after")
    def _button_metadata_matches_options(self) -> "OptionsBlock":
        if self.option_ids is not None:
            if len(self.option_ids) != len(self.options):
                raise ValueError("option_ids debe tener el mismo tamaño que options")
            if len(set(self.option_ids)) != len(self.option_ids):
                raise ValueError("option_ids no puede repetirse")
        if self.option_proofs is not None:
            if self.option_ids is None:
                raise ValueError("option_proofs exige option_ids")
            if len(self.option_proofs) != len(self.option_ids):
                raise ValueError("option_proofs debe tener el mismo tamaño que option_ids")
        return self


class ListBlock(ContractModel):
    type: Literal["list"]
    options: Annotated[
        list[ListItem], Field(min_length=MIN_LIST_OPTIONS, max_length=MAX_LIST_OPTIONS)
    ]


class LinkBlock(ContractModel):
    type: Literal["link"]
    text: MessageText
    url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]


class TemplateBlock(ContractModel):
    type: Literal["template"]
    name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    variables: list[str] = Field(default_factory=list)


class ImageBlock(ContractModel):
    type: Literal["image"]
    url: HttpsUrl
    alt_text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_IMAGE_ALT_LENGTH)]


ResponseBlock = Annotated[
    TextBlock | OptionsBlock | ListBlock | LinkBlock | TemplateBlock | ImageBlock,
    Field(discriminator="type"),
]


class ResponseBlocks(RootModel[list[ResponseBlock]]):
    """Respuesta abstracta completa: al menos un bloque y como máximo un enlace."""

    @model_validator(mode="after")
    def _check_blocks(self) -> "ResponseBlocks":
        if not self.root:
            raise ValueError("la respuesta abstracta necesita al menos un bloque")
        links = sum(isinstance(block, LinkBlock) for block in self.root)
        if links > 1:
            raise ValueError("solo se permite un bloque de enlace por respuesta")
        return self


class ChannelCapabilities(ContractModel):
    """Lo que el canal puede representar en este momento."""

    free_text_allowed: bool
    max_options: Annotated[int, Field(ge=0, le=MAX_OPTION_COUNT)]
    min_list_options: Annotated[int, Field(ge=0, le=MAX_LIST_OPTIONS)]
    max_list_options: Annotated[int, Field(ge=0, le=MAX_LIST_OPTIONS)]
    supports_links: bool
    requires_template: bool
    supports_buttons: bool = True
    supports_images: bool = False
    supports_files: bool = False
    supports_audio: bool = False

    @model_validator(mode="after")
    def _list_bounds(self) -> "ChannelCapabilities":
        if self.min_list_options > self.max_list_options:
            raise ValueError("min_list_options no puede superar max_list_options")
        return self


class ChannelSendRequest(ContractModel):
    """Variante canónica de POST /send para cualquier canal."""

    channel: Channel
    destination: ExternalIdentifier
    blocks: Annotated[list[ResponseBlock], Field(min_length=1)]

    @model_validator(mode="after")
    def _at_most_one_link(self) -> "ChannelSendRequest":
        links = sum(isinstance(block, LinkBlock) for block in self.blocks)
        if links > 1:
            raise ValueError("solo se permite un bloque de enlace por respuesta")
        return self
