"""Adaptador del LLM: texto simple y chat completions con herramientas (#74)."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

import httpx

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...

    def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: Sequence[Any],
        call_tool: Callable[[str, dict[str, Any]], str],
        max_steps: int,
    ) -> str: ...


def _tool_payload(tools: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


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

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("llm_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("LLM no disponible.") from None

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = self._post(payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.error("llm_error code=invalid_response")
            raise ServiceUnavailable("LLM no disponible.") from None
        return content if isinstance(content, str) else ""

    def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: Sequence[Any],
        call_tool: Callable[[str, dict[str, Any]], str],
        max_steps: int,
    ) -> str:
        """R20, R25: envía `tools` y respeta el máximo de llamadas."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        tool_payload = _tool_payload(tools)
        steps = 0
        while True:
            payload: dict[str, Any] = {"model": self._model, "messages": messages}
            if steps < max_steps:
                payload["tools"] = tool_payload
            data = self._post(payload)
            try:
                message = data["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                logger.error("llm_error code=invalid_response")
                raise ServiceUnavailable("LLM no disponible.") from None
            if not isinstance(message, dict):
                raise ServiceUnavailable("LLM no disponible.")
            tool_calls = message.get("tool_calls") or []
            if not tool_calls or steps >= max_steps:
                content = message.get("content")
                return content if isinstance(content, str) else ""
            remaining = max_steps - steps
            if len(tool_calls) > remaining:
                # No se pueden atender todas sin superar el límite: se ejecutan
                # las permitidas y se corta sin otra petición al modelo.
                for call in tool_calls[:remaining]:
                    self._run_tool_call(call, call_tool)
                    steps += 1
                content = message.get("content")
                return content if isinstance(content, str) else ""
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                if steps >= max_steps:
                    break
                output = self._run_tool_call(call, call_tool)
                steps += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": output,
                    }
                )

    @staticmethod
    def _run_tool_call(
        call: Any, call_tool: Callable[[str, dict[str, Any]], str]
    ) -> str:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            return "{}"
        name = function.get("name")
        if not isinstance(name, str):
            return "{}"
        raw_arguments = function.get("arguments") or "{}"
        try:
            arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else dict(raw_arguments)
            )
        except (ValueError, TypeError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        return call_tool(name, arguments)


@dataclass
class ToolStep:
    name: str
    args: dict[str, Any]


class FakeLLM:
    def __init__(self, reply: str = "respuesta del modelo", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ServiceUnavailable("LLM caído")
        return self.reply

    def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: Sequence[Any],
        call_tool: Callable[[str, dict[str, Any]], str],
        max_steps: int,
    ) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ServiceUnavailable("LLM caído")
        return self.reply


class ScriptedLLM:
    """Devuelve en orden las respuestas de una cola; útil para router + RAG/SQL."""

    def __init__(
        self,
        replies: list[str] | None = None,
        tool_steps: list[ToolStep] | None = None,
        final_reply: str = "",
    ) -> None:
        self.replies = list(replies or [])
        self.tool_steps = list(tool_steps or [])
        self.final_reply = final_reply
        self.calls: list[tuple[str, str]] = []
        self.tool_calls: list[tuple[str, dict[str, Any], str]] = []
        self.fail = False
        self.default_reply = ""

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ServiceUnavailable("LLM caído")
        if self.replies:
            return self.replies.pop(0)
        return self.default_reply

    def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: Sequence[Any],
        call_tool: Callable[[str, dict[str, Any]], str],
        max_steps: int,
    ) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ServiceUnavailable("LLM caído")
        for step in self.tool_steps:
            if len(self.tool_calls) >= max_steps:
                break
            output = call_tool(step.name, dict(step.args))
            self.tool_calls.append((step.name, dict(step.args), output))
        return self.final_reply

