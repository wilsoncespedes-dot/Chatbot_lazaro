"""Contrato de canal abierto: slug, multimedia, metadata, dirección e imagen (#60)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

import lazaro_contracts
from lazaro_contracts import (
    CHANNEL_ID_PATTERN,
    DEFAULT_SIGNATURE_WINDOW_SECONDS,
    LAZARO_SIGNATURE_HEADER,
    LAZARO_TIMESTAMP_HEADER,
    MAX_ATTACHMENTS,
    MAX_ATTACHMENT_SIZE_BYTES,
    MAX_CHANNEL_ID_LENGTH,
    MAX_IMAGE_ALT_LENGTH,
    MAX_METADATA_BYTES,
    MAX_METADATA_DEPTH,
    MAX_URL_LENGTH,
    MIN_CHANNEL_ID_LENGTH,
    Attachment,
    AttachmentKind,
    ChannelCapabilities,
    ChannelSendRequest,
    HttpsUrl,
    ImageBlock,
    MessageDirection,
    MessageKind,
    NormalizedMessage,
    ResponseBlocks,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
RECEIVED_AT = "2026-11-03T16:05:12Z"
HISTORICAL_KEYS = {
    "channel",
    "external_user_id",
    "external_chat_id",
    "external_message_id",
    "kind",
    "text",
    "button_id",
    "button_proof",
    "received_at",
}
VALID_LONG_URL = "https://x.example.com/" + "a" * (
    MAX_URL_LENGTH - len("https://x.example.com/")
)
TOO_LONG_URL = "https://x.example.com/" + "a" * (
    MAX_URL_LENGTH + 1 - len("https://x.example.com/")
)


def _message(**changes):
    data = {
        "channel": "whatsapp",
        "external_user_id": "573001112233",
        "external_chat_id": "573001112233",
        "external_message_id": "wamid-1",
        "kind": "text",
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }
    data.update(changes)
    return data


def _attachment(**changes):
    data = {"type": "image", "mime_type": "image/jpeg"}
    data.update(changes)
    return data


def _send_request(**changes):
    data = {
        "channel": "whatsapp",
        "destination": "57300",
        "blocks": [{"type": "text", "text": "Hola"}],
    }
    data.update(changes)
    return data


def _metadata_size(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _nested(depth: int) -> dict:
    value: dict = {}
    for _ in range(depth - 1):
        value = {"a": value}
    return value


def _with_url(model, url: str):
    if model is Attachment:
        return Attachment.model_validate(_attachment(url=url))
    return ImageBlock.model_validate(
        {"type": "image", "url": url, "alt_text": "alternativo"}
    )


# ── R1, R2: identificador de canal ──────────────────────────────────────────


@pytest.mark.parametrize(
    "channel",
    ["telegram", "whatsapp", "canal-externo", "tiktok_simulado", "n8n", "wa", "a" * 32],
)
def test_channel_accepts_valid_slugs(channel: str):
    """R1: cualquier slug de canal válido se acepta en ambos modelos."""
    message = NormalizedMessage.model_validate(_message(channel=channel))
    request = ChannelSendRequest.model_validate(_send_request(channel=channel))
    assert message.channel == channel
    assert request.channel == channel


@pytest.mark.parametrize(
    "channel",
    [
        "",
        "t",
        "a" * 33,
        "Telegram",
        "tele gram",
        "-tg",
        "tg-",
        "tg--x",
        "tg_-x",
        "1canal",
        "canal.externo",
        "canal/x",
        "ñandu",
        "telegram\n",
        5,
    ],
)
def test_channel_rejects_invalid_slugs(channel):
    """R2: un channel que no es slug se rechaza en ambos modelos."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(channel=channel))
    with pytest.raises(ValidationError):
        ChannelSendRequest.model_validate(_send_request(channel=channel))


# ── R3-R8: tipos y adjuntos ─────────────────────────────────────────────────


def test_message_kind_has_exactly_six_values():
    """R3: MessageKind admite texto, botón, no soportado e imagen, archivo y audio."""
    assert set(get_args(MessageKind)) == {
        "text",
        "button",
        "unsupported",
        "image",
        "file",
        "audio",
    }


def test_unknown_kind_video_is_rejected():
    """R3: cualquier tipo fuera de los seis valores se rechaza."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(kind="video"))


@pytest.mark.parametrize("kind", ["image", "file", "audio"])
def test_media_kind_requires_attachment(kind: str):
    """R4: un tipo multimedia sin adjuntos no es válido."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(kind=kind, text=None))


def test_attachment_type_must_match_kind():
    """R5: el tipo del adjunto debe coincidir con el tipo del mensaje."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(
            _message(
                kind="image",
                text=None,
                attachments=[_attachment(type="file", mime_type="application/pdf")],
            )
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "text", "text": "Hola"},
        {"kind": "button", "text": None, "button_id": "acepto"},
        {"kind": "unsupported", "text": None},
    ],
)
def test_non_media_kind_rejects_attachments(changes: dict):
    """R6: solo los tipos multimedia llevan adjuntos."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(
            _message(**changes, attachments=[_attachment()])
        )


def test_media_kind_accepts_optional_caption():
    """R7: un tipo multimedia se acepta sin texto y con un pie de adjunto."""
    without_caption = NormalizedMessage.model_validate(
        _message(kind="image", text=None, attachments=[_attachment()])
    )
    with_caption = NormalizedMessage.model_validate(
        _message(kind="image", text="Pie de la imagen", attachments=[_attachment()])
    )
    assert without_caption.text is None
    assert with_caption.text == "Pie de la imagen"


def test_attachments_are_limited_to_ten():
    """R8: hasta diez adjuntos por mensaje."""
    ten = [_attachment() for _ in range(MAX_ATTACHMENTS)]
    NormalizedMessage.model_validate(_message(kind="image", text=None, attachments=ten))
    eleven = [_attachment() for _ in range(MAX_ATTACHMENTS + 1)]
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(
            _message(kind="image", text=None, attachments=eleven)
        )


def test_attachment_accepts_minimal_and_full_fields():
    """R9: solo type y mime_type son obligatorios; nombre, tamaño y url opcionales."""
    minimal = Attachment.model_validate(_attachment())
    full = Attachment.model_validate(
        _attachment(
            name="foto.jpg",
            size_bytes=2048,
            url="https://x.example.com/a.jpg",
        )
    )
    assert minimal.name is None and minimal.size_bytes is None and minimal.url is None
    assert (full.name, full.size_bytes) == ("foto.jpg", 2048)


def test_attachment_mime_type_rules():
    """R10: el mime_type cumple el patrón y mide entre 3 y 255 caracteres."""
    valid = [
        "image/jpeg",
        "application/pdf",
        "audio/ogg; codecs=opus",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    for mime_type in valid:
        Attachment.model_validate(_attachment(mime_type=mime_type))
    invalid = [
        "jpeg",
        "image/",
        "/jpeg",
        "image jpeg",
        "image/jpeg\n",
        "image/" + "a" * 250,
    ]
    for mime_type in invalid:
        with pytest.raises(ValidationError):
            Attachment.model_validate(_attachment(mime_type=mime_type))


def test_attachment_name_rules():
    """R11: el nombre no está vacío, no es ruta y no lleva controles."""
    Attachment.model_validate(_attachment(name="foto ñandú.jpg"))
    Attachment.model_validate(_attachment(name="a" * 255))
    for name in ("", "a" * 256, "../x", "a\\b", "a\x00b", "a\nb"):
        with pytest.raises(ValidationError):
            Attachment.model_validate(_attachment(name=name))


def test_attachment_size_rules():
    """R12: size_bytes entre 0 y 2 GiB."""
    Attachment.model_validate(_attachment(size_bytes=0))
    Attachment.model_validate(_attachment(size_bytes=MAX_ATTACHMENT_SIZE_BYTES))
    for size in (-1, MAX_ATTACHMENT_SIZE_BYTES + 1):
        with pytest.raises(ValidationError):
            Attachment.model_validate(_attachment(size_bytes=size))


@pytest.mark.parametrize("model", [Attachment, ImageBlock])
def test_https_url_rules(model):
    """R13, R23: la url debe ser https, sin credenciales, espacios ni controles."""
    for url in (
        "https://x.example.com/a.jpg",
        "HTTPS://x.example.com/a",
        VALID_LONG_URL,
    ):
        _with_url(model, url)
    for url in (
        "http://x.example.com/a",
        "https://",
        "ftp://x.example.com",
        "javascript:alert(1)",
        "https://user:pw@x.example.com/a",
        "https://x.example.com/a b",
        "https://x.example.com/a\n",
        TOO_LONG_URL,
    ):
        with pytest.raises(ValidationError):
            _with_url(model, url)


@pytest.mark.parametrize("field", ["data", "content", "bytes"])
def test_attachment_rejects_binary_fields(field: str):
    """R14: un adjunto nunca transporta el binario."""
    with pytest.raises(ValidationError):
        Attachment.model_validate(_attachment(**{field: "binario"}))


# ── R15-R18: metadata ───────────────────────────────────────────────────────


def test_metadata_defaults_to_empty_object_and_accepts_json():
    """R15: metadata es un objeto JSON y por defecto {}."""
    default = NormalizedMessage.model_validate(_message())
    explicit = NormalizedMessage.model_validate(
        _message(metadata={"plataforma": "n8n", "banderas": [True, None, 1]})
    )
    assert default.metadata == {}
    assert explicit.metadata == {"plataforma": "n8n", "banderas": [True, None, 1]}


def test_metadata_size_limit():
    """R15, R16: hasta 4096 bytes en JSON compacto UTF-8."""
    exact = {"k": "x" * (MAX_METADATA_BYTES - len('{"k":""}'))}
    multibyte = {"k": "ñ" * ((MAX_METADATA_BYTES - len('{"k":""}')) // 2)}
    assert _metadata_size(exact) == MAX_METADATA_BYTES
    assert _metadata_size(multibyte) == MAX_METADATA_BYTES
    NormalizedMessage.model_validate(_message(metadata=exact))
    NormalizedMessage.model_validate(_message(metadata=multibyte))
    too_big = {"k": "x" * (MAX_METADATA_BYTES - len('{"k":""}') + 1)}
    assert _metadata_size(too_big) == MAX_METADATA_BYTES + 1
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(metadata=too_big))


def test_metadata_depth_limit():
    """R15, R17: profundidad máxima 5; el objeto raíz cuenta 1."""
    NormalizedMessage.model_validate(_message(metadata=_nested(MAX_METADATA_DEPTH)))
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(
            _message(metadata=_nested(MAX_METADATA_DEPTH + 1))
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"x": ((((((((1,),),),),),),),)},
        {"x": {1: "a"}},
    ],
)
def test_metadata_rejects_non_json_python_values(metadata):
    """R17, R18: valores de Python que no son JSON no son metadata válida."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(metadata=metadata))


def test_metadata_rejects_deeply_nested_python_dict():
    """R17: 100 000 niveles dan ValidationError, nunca RecursionError."""
    metadata: dict = {}
    for _ in range(100_000):
        metadata = {"a": metadata}
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(metadata=metadata))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_metadata_rejects_non_json_numbers(value):
    """R17: NaN e Infinity no son números JSON válidos."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(metadata={"valor": value}))


@pytest.mark.parametrize("metadata", [[1, 2], "texto", 5, None])
def test_metadata_must_be_object(metadata):
    """R18: una lista, texto, número o null no es metadata válida."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate_json(
            json.dumps(_message(metadata=metadata))
        )


# ── R19, R20: dirección ─────────────────────────────────────────────────────


def test_direction_defaults_to_inbound_and_accepts_outbound():
    """R19: direction solo admite inbound y outbound; por defecto inbound."""
    default = NormalizedMessage.model_validate(_message())
    outbound = NormalizedMessage.model_validate(_message(direction="outbound"))
    assert default.direction == "inbound"
    assert outbound.direction == "outbound"
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(direction="saliente"))


def test_outbound_rejects_button_and_unsupported():
    """R20: un mensaje saliente solo puede ser texto o multimedia."""
    for changes in (
        {"kind": "button", "text": None, "button_id": "acepto"},
        {"kind": "unsupported", "text": None},
    ):
        with pytest.raises(ValidationError):
            NormalizedMessage.model_validate(_message(direction="outbound", **changes))
    NormalizedMessage.model_validate(_message(direction="outbound"))
    NormalizedMessage.model_validate(
        _message(
            direction="outbound",
            kind="image",
            text=None,
            attachments=[_attachment()],
        )
    )


# ── R21: capacidades ────────────────────────────────────────────────────────


def _capabilities(**changes):
    data = {
        "free_text_allowed": True,
        "max_options": 3,
        "min_list_options": 4,
        "max_list_options": 10,
        "supports_links": True,
        "requires_template": False,
    }
    data.update(changes)
    return data


def test_capabilities_new_fields_have_defaults():
    """R21: botones true; imágenes, archivos y audio false por defecto."""
    default = ChannelCapabilities.model_validate(_capabilities())
    assert default.supports_buttons is True
    assert default.supports_images is False
    assert default.supports_files is False
    assert default.supports_audio is False
    explicit = ChannelCapabilities.model_validate(
        _capabilities(
            supports_buttons=False,
            supports_images=True,
            supports_files=True,
            supports_audio=True,
        )
    )
    assert explicit.supports_buttons is False
    assert explicit.supports_images is True
    assert explicit.supports_files is True
    assert explicit.supports_audio is True


# ── R22, R23: bloque imagen ─────────────────────────────────────────────────


def test_image_block_is_part_of_response_blocks():
    """R22: ImageBlock es un bloque de respuesta y no cuenta como enlace."""
    image = {
        "type": "image",
        "url": "https://x.example.com/a.jpg",
        "alt_text": "Foto del producto",
    }
    blocks = ResponseBlocks.model_validate(
        [
            {"type": "text", "text": "Mira:"},
            image,
            dict(image, url="https://x.example.com/b.jpg"),
            {"type": "link", "text": "Abrir", "url": "https://example.com"},
        ]
    )
    assert sum(isinstance(block, ImageBlock) for block in blocks.root) == 2
    request = ChannelSendRequest.model_validate(
        _send_request(blocks=[{"type": "text", "text": "Mira:"}, image])
    )
    assert isinstance(request.blocks[1], ImageBlock)


def test_image_block_rejects_missing_or_invalid_fields():
    """R23: url y alt_text son obligatorios y respetan sus límites."""
    ImageBlock.model_validate(
        {
            "type": "image",
            "url": "https://x.example.com/a.jpg",
            "alt_text": "a" * MAX_IMAGE_ALT_LENGTH,
        }
    )
    for block in (
        {"type": "image", "alt_text": "alternativo"},
        {"type": "image", "url": "https://x.example.com/a.jpg"},
        {"type": "image", "url": "https://x.example.com/a.jpg", "alt_text": ""},
        {
            "type": "image",
            "url": "https://x.example.com/a.jpg",
            "alt_text": "a" * (MAX_IMAGE_ALT_LENGTH + 1),
        },
    ):
        with pytest.raises(ValidationError):
            ImageBlock.model_validate(block)


# ── R24-R26: compatibilidad y serialización ────────────────────────────────


@pytest.mark.parametrize(
    "filename,model",
    [
        ("normalized_message.json", NormalizedMessage),
        ("normalized_button_message.json", NormalizedMessage),
        ("channel_send_request.json", ChannelSendRequest),
        ("channel_capabilities.json", ChannelCapabilities),
        ("response_blocks.json", ResponseBlocks),
    ],
)
def test_historical_payloads_validate_with_defaults(filename: str, model):
    """R24: los ejemplos actuales validan con los valores por defecto nuevos."""
    text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
    parsed = model.model_validate_json(text)
    if model is NormalizedMessage:
        assert parsed.attachments == []
        assert parsed.metadata == {}
        assert parsed.direction == "inbound"
    if model is ChannelCapabilities:
        assert parsed.supports_buttons is True
        assert parsed.supports_images is False
        assert parsed.supports_files is False
        assert parsed.supports_audio is False


@pytest.mark.parametrize(
    "filename", ["normalized_message.json", "normalized_button_message.json"]
)
def test_serialization_omits_default_new_fields(filename: str):
    """R25: sin datos nuevos, el JSON contiene exactamente las claves históricas."""
    text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
    message = NormalizedMessage.model_validate_json(text)
    assert set(message.model_dump()) == HISTORICAL_KEYS
    assert set(json.loads(message.model_dump_json())) == HISTORICAL_KEYS


def test_serialization_keeps_non_default_fields_and_round_trips():
    """R26: con adjunto, metadata y outbound, los campos salen y se revalidan."""
    original = NormalizedMessage.model_validate(
        _message(
            direction="outbound",
            kind="image",
            text=None,
            attachments=[_attachment()],
            metadata={"plataforma": "n8n"},
        )
    )
    dumped = original.model_dump()
    assert {"direction", "attachments", "metadata"} <= set(dumped)
    assert NormalizedMessage.model_validate_json(original.model_dump_json()) == original


# ── R27, R48: exportaciones y adjunto obligatorio ──────────────────────────


def test_new_names_are_exported_with_contract_values():
    """R27: los nombres nuevos están en __all__ y sus constantes tienen el valor pactado."""
    names = {
        "Attachment": Attachment,
        "AttachmentKind": AttachmentKind,
        "MessageDirection": MessageDirection,
        "ImageBlock": ImageBlock,
        "HttpsUrl": HttpsUrl,
        "CHANNEL_ID_PATTERN": CHANNEL_ID_PATTERN,
        "MIN_CHANNEL_ID_LENGTH": MIN_CHANNEL_ID_LENGTH,
        "MAX_CHANNEL_ID_LENGTH": MAX_CHANNEL_ID_LENGTH,
        "MAX_ATTACHMENTS": MAX_ATTACHMENTS,
        "MAX_ATTACHMENT_SIZE_BYTES": MAX_ATTACHMENT_SIZE_BYTES,
        "MAX_METADATA_BYTES": MAX_METADATA_BYTES,
        "MAX_METADATA_DEPTH": MAX_METADATA_DEPTH,
        "MAX_URL_LENGTH": MAX_URL_LENGTH,
        "MAX_IMAGE_ALT_LENGTH": MAX_IMAGE_ALT_LENGTH,
        "LAZARO_TIMESTAMP_HEADER": LAZARO_TIMESTAMP_HEADER,
        "LAZARO_SIGNATURE_HEADER": LAZARO_SIGNATURE_HEADER,
        "DEFAULT_SIGNATURE_WINDOW_SECONDS": DEFAULT_SIGNATURE_WINDOW_SECONDS,
    }
    assert set(names) <= set(lazaro_contracts.__all__)
    expected_values = {
        "CHANNEL_ID_PATTERN": r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$",
        "MIN_CHANNEL_ID_LENGTH": 2,
        "MAX_CHANNEL_ID_LENGTH": 32,
        "MAX_ATTACHMENTS": 10,
        "MAX_ATTACHMENT_SIZE_BYTES": 2147483648,
        "MAX_METADATA_BYTES": 4096,
        "MAX_METADATA_DEPTH": 5,
        "MAX_URL_LENGTH": 2048,
        "MAX_IMAGE_ALT_LENGTH": 1024,
        "LAZARO_TIMESTAMP_HEADER": "X-Lazaro-Timestamp",
        "LAZARO_SIGNATURE_HEADER": "X-Lazaro-Signature",
        "DEFAULT_SIGNATURE_WINDOW_SECONDS": 300,
    }
    for name, value in expected_values.items():
        assert getattr(lazaro_contracts, name) == value


def test_attachment_requires_type_and_mime_type():
    """R48: un adjunto sin type o sin mime_type se rechaza."""
    with pytest.raises(ValidationError):
        Attachment.model_validate({"mime_type": "image/jpeg"})
    with pytest.raises(ValidationError):
        Attachment.model_validate({"type": "image"})
