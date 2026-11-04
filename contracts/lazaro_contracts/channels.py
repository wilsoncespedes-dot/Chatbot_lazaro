"""Modelos comunes de canal: mensaje normalizado, capacidades y respuesta abstracta."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, RootModel, StringConstraints, model_validator

from .common import ContractModel, MessageText

Channel = Literal["telegram", "whatsapp"]
MessageKind = Literal["text", "button", "unsupported"]
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

    @model_validator(mode="after")
    def _content_matches_kind(self) -> "NormalizedMessage":
        if self.kind == "text" and not self.text:
            raise ValueError("kind=text exige text")
        if self.kind == "button" and not self.button_id:
            raise ValueError("kind=button exige button_id")
        if self.button_proof is not None and self.kind != "button":
            raise ValueError("button_proof solo existe en kind=button")
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


ResponseBlock = Annotated[
    TextBlock | OptionsBlock | ListBlock | LinkBlock | TemplateBlock,
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
