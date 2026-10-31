"""Tests del esqueleto del servicio rag (feature esqueleto_servicios)."""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lazaro_contracts import ErrorResponse, HealthResponse
from pydantic import BaseModel

from rag.config import Settings
from rag.domain import DomainError
from rag.main import create_app

SVC = "rag"
PORT = "8003"
TOKEN = "test-token"
HEADERS = {"X-Service-Token": TOKEN}
ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = Path(__file__).resolve().parents[1]


class _Echo(BaseModel):
    name: str


class _Teapot(DomainError):
    code = "teapot"
    status_code = 418


def _block(text: str, key: str, indent: int) -> str:
    """Devuelve las líneas hijas de `key:` situada exactamente en la columna `indent`."""
    lines = text.splitlines()
    prefix = " " * indent + key + ":"
    for i, line in enumerate(lines):
        stripped = line.split("#", 1)[0].rstrip()
        if stripped == prefix or stripped.startswith(prefix + " "):
            block = [line]
            for nxt in lines[i + 1:]:
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                block.append(nxt)
            return "\n".join(block)
    return ""


def _compose_service_block() -> str:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services = _block(compose, "services", 0)
    block = _block(services, SVC, 2)
    assert block, f"{SVC} no está en docker-compose.yml"
    return block


def _build_app() -> FastAPI:
    app = create_app(Settings(service_token=TOKEN))

    @app.post("/_test/echo")
    async def echo(body: _Echo) -> _Echo:
        return body

    @app.get("/_test/boom")
    async def boom():
        raise RuntimeError("secreto-interno")

    @app.get("/_test/domain")
    async def domain():
        raise _Teapot("soy una tetera")

    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app())


@pytest.fixture()
def client_no_raise() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def _assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"] == code
    return body


def test_service_layout_exists():
    """R1: la carpeta del servicio tiene la forma de architecture.md."""
    pkg = SERVICE_DIR / SVC
    for rel in [
        pkg / "__init__.py",
        pkg / "main.py",
        pkg / "config.py",
        pkg / "domain.py",
        pkg / "adapters" / "__init__.py",
        SERVICE_DIR / "requirements.txt",
        SERVICE_DIR / "Dockerfile",
        SERVICE_DIR / "tests",
    ]:
        assert rel.exists(), rel


def test_create_app_returns_fastapi():
    """R2: create_app devuelve una instancia de FastAPI (con y sin settings)."""
    assert isinstance(create_app(), FastAPI)
    assert isinstance(create_app(Settings(service_token="x")), FastAPI)


def test_module_exposes_fastapi_app():
    """R3: el módulo main expone `app` como FastAPI."""
    module = importlib.import_module(f"{SVC}.main")
    assert isinstance(module.app, FastAPI)


def test_settings_reads_service_token_from_env(monkeypatch):
    """R4: Settings lee service_token de SERVICE_TOKEN."""
    monkeypatch.setenv("SERVICE_TOKEN", "desde-entorno")
    assert Settings().service_token == "desde-entorno"


def test_requirements_txt_matches_design():
    """R5: requirements.txt tiene exactamente las dependencias del design con cota doble."""
    lines = [
        ln.strip()
        for ln in (SERVICE_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    names = sorted(re.split(r"[<>=]", ln)[0] for ln in lines)
    assert names == sorted([
        "fastapi", "pydantic", "pydantic-settings", "uvicorn",
        "httpx", "pg8000", "pypdf", "python-docx", "python-multipart",
    ])
    for ln in lines:
        assert ">=" in ln and "<" in ln, ln


def test_dockerfile_base_image_and_cmd():
    """R6: Dockerfile con base, copias, instalación y CMD esperados."""
    text = (SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim\s*$", text, re.M)
    assert "COPY contracts/lazaro_contracts" in text
    assert f"COPY services/{SVC}/{SVC}" in text
    assert f"services/{SVC}/requirements.txt" in text
    assert "pip install" in text
    assert (
        f'CMD ["uvicorn", "{SVC}.main:app", "--host", "0.0.0.0", "--port", "8000"]' in text
    )


def test_health_returns_ok_without_token(client):
    """R8, R38: /health responde 200 sin token."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": SVC}


def test_health_body_matches_contract(client):
    """R9: el cuerpo de /health valida contra HealthResponse."""
    HealthResponse.model_validate(client.get("/health").json())


def test_health_ignores_wrong_token(client):
    """R10: /health con token incorrecto sigue siendo 200."""
    response = client.get("/health", headers={"X-Service-Token": "mal"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": SVC}


def test_missing_token_returns_401(client):
    """R11, R38: ruta protegida sin token -> 401 unauthorized."""
    _assert_error(client.get("/_test/domain"), 401, "unauthorized")


def test_wrong_token_returns_401(client):
    """R12: token distinto -> 401 unauthorized."""
    response = client.get("/_test/domain", headers={"X-Service-Token": "otro"})
    _assert_error(response, 401, "unauthorized")


def test_unknown_route_without_token_returns_401_not_404(client):
    """R13: ruta inexistente sin token -> 401, no 404."""
    _assert_error(client.get("/no-existe"), 401, "unauthorized")


def test_post_without_token_returns_401(client):
    """R14: POST sin token -> 401 unauthorized."""
    _assert_error(client.post("/_test/echo", json={"name": "a"}), 401, "unauthorized")


def test_empty_configured_token_rejects_everything():
    """R15: con SERVICE_TOKEN vacío todo lo protegido da 401, incluso con cabecera vacía."""
    client = TestClient(create_app(Settings(service_token="")))
    _assert_error(client.get("/no-existe"), 401, "unauthorized")
    _assert_error(client.get("/no-existe", headers={"X-Service-Token": ""}), 401, "unauthorized")


def test_valid_token_passes_auth(client):
    """R16: con token válido la petición llega al enrutado (no es 401)."""
    assert client.get("/_test/domain", headers=HEADERS).status_code != 401
    assert client.get("/no-existe", headers=HEADERS).status_code != 401


def test_unknown_route_with_token_returns_not_found_error(client):
    """R17: ruta inexistente con token -> 404 not_found."""
    _assert_error(client.get("/no-existe", headers=HEADERS), 404, "not_found")


def test_invalid_body_returns_validation_error(client):
    """R18: cuerpo inválido -> 422 validation_error."""
    response = client.post("/_test/echo", json={"otro": 1}, headers=HEADERS)
    _assert_error(response, 422, "validation_error")


def test_unhandled_exception_returns_internal_error(client_no_raise):
    """R19: excepción no controlada -> 500 internal_error."""
    _assert_error(client_no_raise.get("/_test/boom", headers=HEADERS), 500, "internal_error")


def test_domain_error_maps_to_its_code_and_status(client):
    """R20: DomainError -> status_code y code de la subclase, message del texto."""
    response = client.get("/_test/domain", headers=HEADERS)
    body = _assert_error(response, 418, "teapot")
    assert body["message"] == "soy una tetera"


def test_compose_service_reads_env_file():
    """R24: el servicio declara env_file con .env en compose."""
    match = re.search(r"^\s+env_file:\s*\[([^\]]*)\]\s*$", _compose_service_block(), re.M)
    assert match
    assert ".env" in [item.strip() for item in match.group(1).split(",")]


def test_compose_service_publishes_expected_port():
    """R26: el servicio publica su puerto del host sobre el 8000 interno."""
    pattern = rf"^\s+ports:\s*\[.*[\"']?{PORT}:8000[\"']?.*\]\s*$"
    assert re.search(pattern, _compose_service_block(), re.M)


def test_compose_service_builds_from_root_with_own_dockerfile():
    """R27: build con contexto raíz y el Dockerfile propio."""
    match = re.search(r"^\s+build:\s*\{(.*)\}\s*$", _compose_service_block(), re.M)
    assert match
    content = match.group(1)
    assert re.search(r"context:\s*\.\s*(,|$)", content)
    assert re.search(rf"dockerfile:\s*services/{SVC}/Dockerfile\s*(,|$)", content)


def test_settings_fields_are_in_env_example():
    """R30: cada campo de Settings tiene su línea NOMBRE=... en .env.example."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        ln.split("=", 1)[0].strip()
        for ln in text.splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    }
    for field in Settings.model_fields:
        assert field.upper() in declared, field


def test_module_app_imports_without_service_token(monkeypatch):
    """R41: importar main sin SERVICE_TOKEN no lanza excepciones."""
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    module = importlib.import_module(f"{SVC}.main")
    importlib.reload(module)
    assert isinstance(module.app, FastAPI)


def test_unhandled_exception_message_hides_details(client_no_raise):
    """R42: el message del 500 no incluye el texto de la excepción original."""
    response = client_no_raise.get("/_test/boom", headers=HEADERS)
    assert "secreto-interno" not in response.json()["message"]
    assert "secreto-interno" not in response.text
