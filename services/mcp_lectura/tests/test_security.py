"""Seguridad del servidor MCP: token, salud y red interna (#74)."""
from __future__ import annotations

from pathlib import Path

import yaml
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_lectura.adapters import FakeAuditSink, FakeDemoOffers, FakeRagSearch
from mcp_lectura.config import Settings
from mcp_lectura.main import create_app
from mcp_lectura.server import McpDeps

ROOT = Path(__file__).resolve().parents[3]


async def _mcp_endpoint(_):
    return JSONResponse({"jsonrpc": "2.0", "id": 1, "result": {}})


def _fake_mcp_app() -> Starlette:
    return Starlette(routes=[Route("/mcp", _mcp_endpoint, methods=["POST"])])


def _client() -> tuple[TestClient, FakeAuditSink]:
    settings = Settings(_env_file=None, service_token="tok", rag_url="http://rag")
    audit = FakeAuditSink()
    deps = McpDeps(
        rag=FakeRagSearch(), offers=FakeDemoOffers(), audit=audit
    )
    return TestClient(create_app(settings, deps, mcp_app=_fake_mcp_app())), audit


def test_missing_token_401():
    """R6: sin `X-Service-Token` responde 401 y no ejecuta herramientas."""
    client, audit = _client()
    response = client.post("/mcp", json={})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert audit.records == []


def test_wrong_token_401():
    """R6: un token incorrecto responde 401 y no ejecuta herramientas."""
    client, audit = _client()
    response = client.post(
        "/mcp", json={}, headers={"X-Service-Token": "otro"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert audit.records == []


def test_valid_token_reaches_the_mcp_app():
    """R6: con token válido la petición llega al servidor MCP."""
    client, _ = _client()
    response = client.post(
        "/mcp", json={}, headers={"X-Service-Token": "tok"}
    )
    assert response.status_code == 200


def test_health_without_token():
    """R7: `/health` es público y no lista herramientas ni datos."""
    client, _ = _client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mcp_lectura"}
    assert "buscar_manuales" not in response.text
    assert "ofertas" not in response.text


def test_compose_publishes_no_port():
    """R8: `mcp_lectura` solo es accesible por la red interna de compose."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["mcp_lectura"]
    assert "ports" not in service
    assert "8000" in service["expose"]
