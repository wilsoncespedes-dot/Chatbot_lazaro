"""Adaptador de Telegram (Bot API) con versión falsa."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

import httpx
from lazaro_contracts import (
    MAX_LIST_OPTIONS,
    MAX_OPTION_COUNT,
    MAX_TEXT_LENGTH,
    MIN_LIST_OPTIONS,
    ChannelCapabilities,
    DeliveryStatus,
    LinkBlock,
    ListBlock,
    NormalizedMessage,
    OptionsBlock,
    ResponseBlock,
    TemplateBlock,
    TextBlock,
)

from ..domain import TelegramError, extract_incoming
from ..domain import normalize_incoming as normalize_update


class TelegramClient(Protocol):
    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> None:  # lanza TelegramError
        ...


class HttpTelegramClient:
    def __init__(self, bot_token: str, timeout: float = 10) -> None:
        self._bot_token = bot_token
        self._timeout = timeout

    def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        body: dict = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            body["reply_markup"] = reply_markup
        try:
            response = httpx.post(
                url, json=body, timeout=self._timeout
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # No se propaga la URL original (contiene el token del bot).
            raise TelegramError(
                f"Telegram respondió {exc.response.status_code} al enviar el mensaje."
            ) from None
        except httpx.HTTPError as exc:
            raise TelegramError(
                f"No se pudo contactar con Telegram ({type(exc).__name__})."
            ) from None


class FakeTelegramClient:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.reply_markups: list[dict | None] = []
        self.fail = fail

    def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> None:
        if self.fail:
            raise TelegramError("Telegram no disponible.")
        self.sent.append((chat_id, text))
        self.reply_markups.append(reply_markup)


def build_inline_keyboard(blocks: Sequence[ResponseBlock]) -> dict | None:
    """R38: pinta un teclado inline con los IDs y pruebas del bloque de opciones."""
    for block in blocks:
        if not isinstance(block, OptionsBlock):
            continue
        if block.option_ids is None:
            continue
        proofs = block.option_proofs or ["" for _ in block.option_ids]
        keyboard = [
            [
                {
                    "text": label,
                    "callback_data": f"{option_id}:{proof}"[:64],
                }
                for label, option_id, proof in zip(
                    block.options, block.option_ids, proofs
                )
            ]
        ]
        return {"inline_keyboard": keyboard}
    return None


def render_blocks(blocks: Sequence[ResponseBlock]) -> str:
    """R2, R10: representa los bloques como texto conservando su contenido."""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, OptionsBlock):
            parts.append("\n".join(block.options))
        elif isinstance(block, ListBlock):
            parts.append(
                "\n".join(f"{index}. {option}" for index, option in enumerate(block.options, 1))
            )
        elif isinstance(block, LinkBlock):
            parts.append(f"{block.text}: {block.url}")
        elif isinstance(block, TemplateBlock) and block.variables:
            parts.append(f"{block.name}: {', '.join(block.variables)}")
        elif isinstance(block, TemplateBlock):
            parts.append(block.name)
    return "\n".join(parts)[:MAX_TEXT_LENGTH]


class TelegramChannelAdapter:
    """Implementación de la interfaz común de canal sobre el cliente de Telegram."""

    channel = "telegram"

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            free_text_allowed=True,
            max_options=MAX_OPTION_COUNT,
            min_list_options=MIN_LIST_OPTIONS,
            max_list_options=MAX_LIST_OPTIONS,
            supports_links=True,
            requires_template=False,
        )

    def normalize_incoming(
        self, raw: dict, received_at: datetime
    ) -> NormalizedMessage | None:
        incoming = extract_incoming(raw)
        if incoming is None:
            return None
        return normalize_update(incoming, received_at)

    def send(
        self, destination: str, blocks: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        self._client.send_message(
            int(destination),
            render_blocks(blocks),
            reply_markup=build_inline_keyboard(blocks),
        )
        return "sent"

    def delivery_status(self, raw: str) -> DeliveryStatus:
        normalized = raw.strip().lower()
        if normalized in ("sent", "delivered", "read", "failed"):
            return normalized  # type: ignore[return-value]
        return "failed"
