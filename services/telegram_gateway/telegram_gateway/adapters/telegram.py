"""Adaptador de Telegram (Bot API) con versión falsa."""
from __future__ import annotations

from typing import Protocol

import httpx

from ..domain import TelegramError


class TelegramClient(Protocol):
    def send_message(self, chat_id: int, text: str) -> None:  # lanza TelegramError
        ...


class HttpTelegramClient:
    def __init__(self, bot_token: str, timeout: float = 10) -> None:
        self._bot_token = bot_token
        self._timeout = timeout

    def send_message(self, chat_id: int, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            response = httpx.post(
                url, json={"chat_id": chat_id, "text": text}, timeout=self._timeout
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
        self.fail = fail

    def send_message(self, chat_id: int, text: str) -> None:
        if self.fail:
            raise TelegramError("Telegram no disponible.")
        self.sent.append((chat_id, text))
