"""Cliente LLM con herramientas conectado a la configuración (#74)."""
from __future__ import annotations

import json

import httpx

from orchestrator.adapters.llm import HttpLLMClient
from orchestrator.adapters.mcp import McpToolSpec


def test_tools_sent_to_configured_endpoint(monkeypatch):
    """R25: usa LLM_BASE_URL/LLM_MODEL/LLM_API_KEY y envía `tools`."""
    captured: list[dict] = []
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "ofertas_demo",
                                    "arguments": json.dumps({"destino": "Melgar"}),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {"choices": [{"message": {"role": "assistant", "content": "Hay ofertas"}}]},
    ]

    def fake_post(url, *, json=None, headers=None, timeout=None, **kwargs):
        captured.append(
            {"url": str(url), "body": json, "headers": dict(headers or {})}
        )
        # `raise_for_status` exige una request adjunta a la respuesta.
        return httpx.Response(
            200,
            json=responses.pop(0),
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    tool_calls: list[tuple[str, dict]] = []

    def call_tool(name, args):
        tool_calls.append((name, args))
        return json.dumps([{"destino": "Melgar"}])

    tool = McpToolSpec(
        name="ofertas_demo",
        description="Ofertas de demostración.",
        input_schema={
            "type": "object",
            "properties": {"destino": {"type": "string"}},
            "required": ["destino"],
        },
    )
    client = HttpLLMClient(
        "http://ollama:11434/v1", "ollama", "llama3.1", 5
    )

    answer = client.complete_with_tools(
        "sistema", "¿ofertas?", [tool], call_tool, 3
    )

    assert answer == "Hay ofertas"
    assert tool_calls == [("ofertas_demo", {"destino": "Melgar"})]
    assert captured[0]["url"] == "http://ollama:11434/v1/chat/completions"
    assert captured[0]["headers"]["Authorization"] == "Bearer ollama"
    first_body = captured[0]["body"]
    assert first_body["model"] == "llama3.1"
    assert first_body["tools"][0]["function"]["name"] == "ofertas_demo"
    assert first_body["tools"][0]["function"]["parameters"]["properties"][
        "destino"
    ] == {"type": "string"}
    second_messages = captured[1]["body"]["messages"]
    assert any(message["role"] == "tool" for message in second_messages)
