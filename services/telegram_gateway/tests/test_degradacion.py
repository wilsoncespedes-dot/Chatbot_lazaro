"""R16–R21: degradación pura de bloques según capacidades del canal."""
from __future__ import annotations

from itertools import product

import pytest
from lazaro_contracts import (
    ChannelCapabilities,
    ImageBlock,
    LinkBlock,
    ListBlock,
    OptionsBlock,
    ResponseBlock,
    TextBlock,
)

from telegram_gateway.domain import (
    ChannelWindowClosed,
    degrade_blocks,
    prepare_blocks,
    send_response,
)


def _capabilities(**overrides) -> ChannelCapabilities:
    values = {
        "free_text_allowed": True,
        "max_options": 3,
        "min_list_options": 4,
        "max_list_options": 10,
        "supports_links": True,
        "requires_template": False,
        "supports_buttons": True,
        "supports_images": True,
        "supports_files": False,
        "supports_audio": False,
    }
    values.update(overrides)
    return ChannelCapabilities(**values)


def _options(count: int = 2) -> OptionsBlock:
    return OptionsBlock(
        type="options", options=[f"opción {i}" for i in range(1, count + 1)]
    )


def _list(count: int = 4) -> ListBlock:
    return ListBlock(
        type="list", options=[f"opción {i}" for i in range(1, count + 1)]
    )


def _image() -> ImageBlock:
    return ImageBlock(
        type="image",
        url="https://media.example.test/imagen.jpg",
        alt_text="Vista previa",
    )


def test_options_degrade_when_buttons_are_missing_or_limit_is_exceeded():
    """R16: opciones pasan a texto numerado sin botones o sobre max_options."""
    source = _options(2)
    assert degrade_blocks([source], _capabilities(supports_buttons=False)) == [
        TextBlock(type="text", text="1. opción 1\n2. opción 2")
    ]
    assert degrade_blocks([source], _capabilities(max_options=1)) == [
        TextBlock(type="text", text="1. opción 1\n2. opción 2")
    ]


@pytest.mark.parametrize(
    "count,minimum,maximum",
    [(4, 5, 10), (4, 0, 3)],
)
def test_lists_degrade_outside_capability_bounds(count, minimum, maximum):
    """R17: listas fuera de min_list_options/max_list_options pasan a texto numerado."""
    result = degrade_blocks(
        [_list(count)],
        _capabilities(min_list_options=minimum, max_list_options=maximum),
    )
    assert result == [
        TextBlock(
            type="text",
            text="\n".join(f"{index}. opción {index}" for index in range(1, count + 1)),
        )
    ]


@pytest.mark.parametrize("supports_links", [True, False])
def test_images_degrade_to_link_or_text(supports_links):
    """R18: una imagen sin capacidad se convierte en enlace o texto alternativo."""
    result = degrade_blocks(
        [_image()], _capabilities(supports_images=False, supports_links=supports_links)
    )
    if supports_links:
        assert result == [
            LinkBlock(
                type="link",
                text="Vista previa",
                url="https://media.example.test/imagen.jpg",
            )
        ]
    else:
        assert result == [
            TextBlock(
                type="text",
                text="Vista previa: https://media.example.test/imagen.jpg",
            )
        ]


@pytest.mark.parametrize("supports_links", [True, False])
def test_links_degrade_to_text_and_split_when_combined_text_is_too_long(supports_links):
    """R19: enlaces sin capacidad se representan en texto sin superar 4096 chars."""
    source = LinkBlock(
        type="link", text="x" * 4096, url="https://example.test/" + "y" * 100
    )
    if supports_links:
        assert degrade_blocks([source], _capabilities(supports_links=True)) == [source]
        return
    result = degrade_blocks([source], _capabilities(supports_links=False))
    assert result == [
        TextBlock(type="text", text=source.text),
        TextBlock(type="text", text=source.url),
    ]
    assert all(len(block.text) <= 4096 for block in result)


def test_degrade_blocks_is_pure_ordered_and_deterministic():
    """R20: no muta la entrada, conserva orden y produce el mismo resultado."""
    original: list[ResponseBlock] = [
        _options(),
        _list(),
        _image(),
        LinkBlock(type="link", text="Manual", url="https://example.test/manual"),
        TextBlock(type="text", text="Final"),
    ]
    snapshot = list(original)
    for buttons, images, links, bounds in product(
        (False, True), (False, True), (False, True), ((0, 3), (0, 10), (5, 10))
    ):
        minimum, maximum = bounds
        capabilities = _capabilities(
            supports_buttons=buttons,
            supports_images=images,
            supports_links=links,
            min_list_options=minimum,
            max_list_options=maximum,
            max_options=1,
        )
        first = degrade_blocks(original, capabilities)
        second = degrade_blocks(original, capabilities)
        assert first == second
        assert original == snapshot
        assert first[-1] == original[-1]


class _RecordingAdapter:
    def __init__(self, capabilities: ChannelCapabilities) -> None:
        self._capabilities = capabilities
        self.sent: list[ResponseBlock] = []

    def capabilities(self) -> ChannelCapabilities:
        return self._capabilities

    def send(self, destination: str, blocks: list[ResponseBlock]) -> str:
        self.sent.extend(blocks)
        return "sent"


def test_send_response_degrades_before_sending():
    """R21: send_response envía el enlace degradado en vez de rechazar la imagen."""
    adapter = _RecordingAdapter(_capabilities(supports_images=False))
    status = send_response(adapter, "destino", [_image()])
    assert status == "sent"
    assert adapter.sent == [
        LinkBlock(
            type="link",
            text="Vista previa",
            url="https://media.example.test/imagen.jpg",
        )
    ]


def test_prepare_blocks_applies_degradation_before_window_check():
    """R21: la imagen se degrada primero y luego respeta la ventana de texto libre."""
    with pytest.raises(ChannelWindowClosed):
        prepare_blocks(
            [_image()],
            _capabilities(supports_images=False, free_text_allowed=False),
        )
