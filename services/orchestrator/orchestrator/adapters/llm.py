"""Adaptador del LLM: solo un texto de sistema y uno de usuario; sin herramientas."""
from __future__ import annotations

import logging
import uuid
from typing import Protocol

import httpx

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class HttpLLMClient:
    """Endpoint compatible con chat completions de `base_url`, sin SDK."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 10,
        session_header: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        # Algunos proveedores (p. ej. OpenCode Go) exigen un id de sesión
        # estable por cliente; vacío = no se envía.
        self._session_header = session_header.strip()
        self._session_id = uuid.uuid4().hex

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._session_header:
            headers[self._session_header] = self._session_id
        return headers

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("llm_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("LLM no disponible.") from None
        return content if isinstance(content, str) else ""


class FakeLLM:
    def __init__(self, reply: str = "respuesta del modelo", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ServiceUnavailable("LLM caído")
        return self.reply


class ScriptedLLM:
    """Devuelve en orden las respuestas de una cola; útil para router + RAG/SQL."""

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.calls: list[tuple[str, str]] = []
        self.fail = False
        self.default_reply = ""

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ServiceUnavailable("LLM caído")
        if self.replies:
            return self.replies.pop(0)
        return self.default_reply
