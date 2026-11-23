"""Cliente HTTP del Send API de Meta (Messenger e Instagram) y doble de prueba.

Fase 7: el Page Access Token no vive en el cliente; el canal lo descifra de
`canales.config_secreta` y lo pasa en cada envío (cabecera Bearer, nunca en URL).
"""
from __future__ import annotations

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

# PENDIENTE: confirmar con la doc oficial de Meta el límite real por mensaje (950
# bytes es conservador), la versión de Graph (`META_GRAPH_API_VERSION`), que
# Instagram responde por `/{PAGE_ID}/messages` con el Page token y que
# `is_reusable: false` acepta URLs firmadas con query string. Sin llamadas reales.
MAX_META_TEXT_BYTES = 950


class MetaMessagingApiError(Exception):
    """Fallo de red o de la API de Meta, sin cuerpo ni credenciales."""


class MetaMessagingApi(Protocol):
    def send_message(
        self, channel: str, recipient: str, text: str, page_token: str
    ) -> None: ...

    def send_image(
        self, channel: str, recipient: str, image_url: str, page_token: str
    ) -> None: ...


def split_meta_text(text: str, limit_bytes: int = MAX_META_TEXT_BYTES) -> list[str]:
    """Divide sin perder caracteres y respeta límites UTF-8 del Send API."""
    if limit_bytes < 1:
        raise ValueError("limit_bytes debe ser positivo")
    remaining = text
    parts: list[str] = []
    while remaining:
        used = 0
        cut = 0
        for index, char in enumerate(remaining):
            char_bytes = len(char.encode("utf-8"))
            if used + char_bytes > limit_bytes:
                break
            used += char_bytes
            cut = index + 1
        if cut == 0:
            raise ValueError("limit_bytes no admite un carácter UTF-8")
        if cut < len(remaining):
            boundary = max(
                remaining.rfind("\n", 0, cut),
                remaining.rfind(" ", 0, cut),
            )
            if boundary > 0:
                cut = boundary + 1
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    return parts


class HttpMetaMessagingApi:
    def __init__(
        self,
        graph_base_url: str,
        api_version: str,
        page_id: str,
        client: httpx.Client,
    ) -> None:
        self._messages_url = (
            f"{graph_base_url.rstrip('/')}/{api_version}/{page_id}/messages"
        )
        self._client = client

    def send_message(
        self, channel: str, recipient: str, text: str, page_token: str
    ) -> None:
        for part in split_meta_text(text):
            self._post(channel, recipient, {"text": part}, page_token)

    def send_image(
        self, channel: str, recipient: str, image_url: str, page_token: str
    ) -> None:
        # `is_reusable=False`: la URL firmada del gráfico caduca (fase 5).
        self._post(
            channel,
            recipient,
            {
                "attachment": {
                    "type": "image",
                    "payload": {"url": image_url, "is_reusable": False},
                }
            },
            page_token,
        )

    def _post(
        self,
        channel: str,
        recipient: str,
        message: dict,
        page_token: str,
    ) -> None:
        if not page_token:
            raise MetaMessagingApiError("missing_page_token")
        try:
            response = self._client.post(
                self._messages_url,
                json={
                    "recipient": {"id": recipient},
                    "messaging_type": "RESPONSE",
                    "message": message,
                },
                headers={"Authorization": f"Bearer {page_token}"},
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "meta_send_network_error channel=%s type=%s",
                channel,
                type(exc).__name__,
            )
            raise MetaMessagingApiError("network_error") from None
        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        error_code = (
            error.get("code")
            if isinstance(error, dict)
            and isinstance(error.get("code"), int)
            and not isinstance(error.get("code"), bool)
            else None
        )
        if response.status_code >= 400 or error is not None:
            logger.warning(
                "meta_send_failed channel=%s status=%s code=%s",
                channel,
                response.status_code,
                error_code,
            )
            raise MetaMessagingApiError("send_failed")


class FakeMetaMessagingApi:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str, str]] = []
        self.images: list[tuple[str, str, str]] = []
        self.tokens: list[str] = []

    def send_message(
        self, channel: str, recipient: str, text: str, page_token: str
    ) -> None:
        if self.fail:
            raise MetaMessagingApiError("send_failed")
        self.tokens.append(page_token)
        self.sent.append((channel, recipient, text))

    def send_image(
        self, channel: str, recipient: str, image_url: str, page_token: str
    ) -> None:
        if self.fail:
            raise MetaMessagingApiError("send_failed")
        self.tokens.append(page_token)
        self.images.append((channel, recipient, image_url))
