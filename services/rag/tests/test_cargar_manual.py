"""Tests de scripts/cargar_manual.py (httpx.MockTransport, sin red)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "cargar_manual.py"
_spec = importlib.util.spec_from_file_location("cargar_manual", SCRIPT)
cargar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cargar)


@pytest.fixture()
def manual(tmp_path):
    path = tmp_path / "guia.pdf"
    path.write_bytes(b"%PDF-1.4 contenido")
    return path


@pytest.fixture()
def env_vars(monkeypatch):
    monkeypatch.setenv("RAG_URL", "http://rag:8000")
    monkeypatch.setenv("SERVICE_TOKEN", "tok")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_script_posts_multipart_with_token(manual, env_vars):
    """R19: POST {RAG_URL}/manuals multipart con file, name y X-Service-Token."""
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Service-Token")
        seen["ctype"] = request.headers.get("content-type", "")
        seen["body"] = request.read()
        return httpx.Response(201, json={"manual_id": "abc", "chunks": 3})

    code = cargar.main([str(manual), "--nombre", "Guía"], client=_client(handler))
    assert code == 0
    assert seen["url"] == "http://rag:8000/manuals"
    assert seen["token"] == "tok"
    assert seen["ctype"].startswith("multipart/form-data")
    assert b'name="file"' in seen["body"] and b'name="name"' in seen["body"]
    assert "Guía".encode() in seen["body"] and b"%PDF-1.4 contenido" in seen["body"]


def test_script_prints_manual_id_and_chunks(manual, env_vars, capsys):
    """R19: imprime manual_id y chunks con salida 0."""
    client = _client(lambda r: httpx.Response(201, json={"manual_id": "abc", "chunks": 3}))
    assert cargar.main([str(manual), "--nombre", "G"], client=client) == 0
    out = capsys.readouterr().out
    assert "abc" in out and "3" in out


def test_script_exits_nonzero_on_error_response(manual, env_vars, capsys):
    """R20: respuesta de error -> salida != 0 y error/message en stderr."""
    client = _client(
        lambda r: httpx.Response(415, json={"error": "unsupported_format", "message": "no es PDF"})
    )
    assert cargar.main([str(manual), "--nombre", "G"], client=client) != 0
    err = capsys.readouterr().err
    assert "unsupported_format" in err and "no es PDF" in err


def test_script_exits_nonzero_when_rag_unreachable(manual, env_vars, capsys):
    """R20: rag no alcanzable -> salida != 0 con la causa en stderr."""

    def boom(request):
        raise httpx.ConnectError("sin conexión")

    assert cargar.main([str(manual), "--nombre", "G"], client=_client(boom)) != 0
    assert "sin conexión" in capsys.readouterr().err


def test_script_fails_when_file_missing(tmp_path, env_vars):
    """R21: ruta inexistente -> salida != 0 sin enviar petición."""
    calls = []
    client = _client(lambda r: calls.append(r) or httpx.Response(201, json={}))
    assert cargar.main([str(tmp_path / "no.pdf"), "--nombre", "G"], client=client) != 0
    assert calls == []


def test_script_fails_when_env_missing(manual, monkeypatch):
    """R21: sin RAG_URL o SERVICE_TOKEN -> salida != 0 sin enviar petición."""
    calls = []
    client = _client(lambda r: calls.append(r) or httpx.Response(201, json={}))
    monkeypatch.delenv("RAG_URL", raising=False)
    monkeypatch.setenv("SERVICE_TOKEN", "tok")
    assert cargar.main([str(manual), "--nombre", "G"], client=client) != 0
    monkeypatch.setenv("RAG_URL", "http://rag:8000")
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    assert cargar.main([str(manual), "--nombre", "G"], client=client) != 0
    assert calls == []
