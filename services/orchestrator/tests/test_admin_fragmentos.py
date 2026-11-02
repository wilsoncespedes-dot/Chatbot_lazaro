"""Tests de #22 panel_fragmentos: vistas de manuales/fragmentos y adaptador del RAG."""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import (
    ChunkItem,
    ChunkUpdateResponse,
    ManualSummary,
    ManualUploadResponse,
)

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient, HttpRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.config import Settings
from orchestrator.domain import Adapters, RagRejected, ServiceUnavailable
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token-centinela"
PASSWORD = "clave-segura-123"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
INTERNAL_HEADERS = {"X-Service-Token": SERVICE_TOKEN}
CHUNK_TEXT = "Para reiniciar el equipo, mantenga pulsado el botón."


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    settings: Settings
    adapters: Adapters
    rag: FakeRagClient
    clock: list[datetime] = field(default_factory=lambda: [FIXED_NOW])


def _items() -> list[ChunkItem]:
    return [
        ChunkItem(
            chunk_id="c1",
            manual_id="m1",
            manual="Manual Uno",
            order=1,
            text=CHUNK_TEXT,
            active=True,
        ),
        ChunkItem(
            chunk_id="c2",
            manual_id="m1",
            manual="Manual Uno",
            order=2,
            text="Las facturas rectificativas se emiten en contabilidad.",
            active=False,
        ),
    ]


@pytest.fixture()
def env() -> Env:
    settings = Settings(
        service_token=SERVICE_TOKEN,
        password_hash_iterations=100000,
        admin_cookie_secure=False,
        admin_session_ttl_minutes=60,
        admin_events_limit=50,
        admin_login_max_attempts=3,
        admin_login_window_minutes=15,
        admin_trust_proxy_headers=False,
        admin_manual_max_bytes=64,
    )
    clock = [FIXED_NOW]
    repo = FakeRepository()
    rag = FakeRagClient(
        manuals=[
            ManualSummary(manual_id="m1", name="Manual Uno", chunks=2),
            ManualSummary(manual_id="m2", name="Manual Dos", chunks=0),
        ],
        chunks={"m1": _items()},
        upload_response=ManualUploadResponse(manual_id="manual-nuevo", chunks=1),
        update_response=ChunkUpdateResponse(
            chunk_id="c1",
            manual_id="m1",
            manual="Manual Uno",
            order=1,
            text="texto nuevo",
            active=True,
        ),
        active_response=ChunkItem(
            chunk_id="c1",
            manual_id="m1",
            manual="Manual Uno",
            order=1,
            text=CHUNK_TEXT,
            active=False,
        ),
    )
    adapters = Adapters(
        repository=repo,
        rag=rag,
        llm=FakeLLM(reply=""),
        gateway=FakeGatewayClient(),
        handover=FakeHandoverClient(),
        db_query=FakeDbQuery(),
        clock=lambda: clock[0],
        new_id=lambda: "generated-id",
    )
    client = TestClient(create_app(settings, adapters))
    created = client.post(
        "/profiles",
        json={"username": "admin1", "role": "admin", "password": PASSWORD},
        headers=INTERNAL_HEADERS,
    )
    assert created.status_code == 201, created.text
    return Env(client=client, repo=repo, settings=settings, adapters=adapters, rag=rag,
               clock=clock)


def _login_ok(env: Env) -> None:
    response = env.client.post(
        "/admin/login",
        data={"username": "admin1", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def _csrf(env: Env) -> str:
    response = env.client.get("/admin")
    assert response.status_code == 200
    match = CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


def _secure_html(response) -> None:
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert "<script" not in response.text.lower()
    for value in re.findall(r'(?:src|href)="([^"]*)"', response.text):
        assert not value.startswith(("http://", "https://", "//"))


# ── Rutas del panel ─────────────────────────────────────────────────────────


def test_manuals_page_lists_manuals_and_upload_form(env):
    """R9: GET /admin/manuals muestra nombre, fragmentos, enlace y formulario."""
    _login_ok(env)
    response = env.client.get("/admin/manuals")

    assert response.status_code == 200
    assert env.rag.admin_calls == [("list_manuals",)]
    text = response.text
    assert "Manual Uno" in text and "Manual Dos" in text
    assert "2" in text
    assert 'href="/admin/manuals/m1"' in text
    assert 'href="/admin/manuals/m2"' in text
    assert 'name="name"' in text
    assert 'type="file"' in text and 'name="file"' in text
    assert 'action="/admin/manuals"' in text
    assert "Manuales" in text


def test_upload_manual_redirects_to_created_manual(env):
    """R10: POST /admin/manuals reenvía name/file y redirige 303 al manual creado."""
    _login_ok(env)
    csrf = _csrf(env)
    content = b"%PDF-1.4 datos"

    response = env.client.post(
        "/admin/manuals",
        files={"file": ("manual.pdf", content, "application/pdf")},
        data={"name": "Manual Nuevo", "csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/manuals/manual-nuevo"
    call = env.rag.admin_calls[-1]
    assert call == (
        "upload_manual",
        "Manual Nuevo",
        "manual.pdf",
        content,
        "application/pdf",
    )


def test_upload_manual_rejects_oversize_missing_and_invalid_without_calling_rag(env):
    """R11: tamaño -> 413; falta name/file o name inválido -> 422; sin llamada al RAG."""
    _login_ok(env)
    csrf = _csrf(env)
    env.settings.admin_manual_max_bytes = 10
    before = list(env.rag.admin_calls)

    too_big = env.client.post(
        "/admin/manuals",
        files={"file": ("grande.pdf", b"x" * 11, "application/pdf")},
        data={"name": "Grande", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert too_big.status_code == 413

    missing_file = env.client.post(
        "/admin/manuals",
        data={"name": "Sin archivo", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert missing_file.status_code == 422

    missing_name = env.client.post(
        "/admin/manuals",
        files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert missing_name.status_code == 422

    invalid_name = env.client.post(
        "/admin/manuals",
        files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
        data={"name": "a" * 201, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert invalid_name.status_code == 422
    assert env.rag.admin_calls == before


def test_manual_chunks_page_lists_order_text_state_and_forms(env):
    """R12: GET /admin/manuals/{id} muestra los fragmentos con edición y estado."""
    _login_ok(env)
    response = env.client.get("/admin/manuals/m1")

    assert response.status_code == 200
    assert ("list_chunks", "m1") in env.rag.admin_calls
    text = response.text
    assert CHUNK_TEXT in text
    assert "Las facturas rectificativas" in text
    assert "Sí" in text and "No" in text
    assert 'action="/admin/chunks/c1"' in text
    assert 'name="text"' in text
    assert 'action="/admin/chunks/c1/active"' in text
    assert "Desactivar" in text and "Activar" in text


def test_edit_chunk_redirects_to_its_manual(env):
    """R13: POST /admin/chunks/{id} llama a PATCH /chunks/{id} y redirige 303."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/chunks/c1",
        data={"text": "texto nuevo", "csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/manuals/m1"
    assert env.rag.admin_calls[-1] == ("update_chunk", "c1", "texto nuevo")


@pytest.mark.parametrize("text", ["", "   ", "\n\t "], ids=["empty", "spaces", "blank"])
def test_edit_chunk_rejects_blank_text_without_calling_rag(env, text):
    """R14: text ausente, vacío o solo espacios -> 422 sin llamar al RAG."""
    _login_ok(env)
    csrf = _csrf(env)
    before = list(env.rag.admin_calls)

    data = {"csrf_token": csrf}
    if text:
        data["text"] = text
    response = env.client.post(
        "/admin/chunks/c1", data=data, follow_redirects=False
    )
    assert response.status_code == 422
    assert env.rag.admin_calls == before


@pytest.mark.parametrize("active", ["true", "false"])
def test_toggle_chunk_active_redirects_to_manual(env, active):
    """R15: POST /admin/chunks/{id}/active llama al RAG con el booleano y redirige."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        f"/admin/chunks/c1/active",
        data={"active": active, "csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/manuals/m1"
    assert env.rag.admin_calls[-1] == ("set_chunk_active", "c1", active == "true")


@pytest.mark.parametrize("active", ["", "maybe", "1", "True", "false "])
def test_toggle_chunk_active_rejects_invalid_values_without_calling_rag(env, active):
    """R16: active distinto de true/false -> 422 sin llamar al RAG."""
    _login_ok(env)
    csrf = _csrf(env)
    before = list(env.rag.admin_calls)

    response = env.client.post(
        "/admin/chunks/c1/active",
        data={"active": active, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert env.rag.admin_calls == before


def test_rag_rejections_render_fixed_pages_with_same_status(env):
    """R17: 404/415/422 -> misma página HTML con mensaje fijo y sin cuerpo del RAG."""
    _login_ok(env)
    csrf = _csrf(env)

    env.rag.errors["list_chunks"] = RagRejected("not_found", 404)
    page_404 = env.client.get("/admin/manuals/desconocido")
    assert page_404.status_code == 404
    assert "No se encontró" in page_404.text
    assert "not_found" not in page_404.text

    env.rag.errors["upload_manual"] = RagRejected("unsupported_format", 415)
    page_415 = env.client.post(
        "/admin/manuals",
        files={"file": ("m.txt", b"datos", "text/plain")},
        data={"name": "Manual", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert page_415.status_code == 415
    assert "PDF" in page_415.text
    assert "unsupported_format" not in page_415.text

    env.rag.errors["update_chunk"] = RagRejected("validation_error", 422)
    page_422 = env.client.post(
        "/admin/chunks/c1",
        data={"text": "texto", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert page_422.status_code == 422
    assert "datos enviados" in page_422.text
    assert "validation_error" not in page_422.text


@pytest.mark.parametrize(
    "operation",
    ["list_manuals", "list_chunks", "upload_manual", "update_chunk", "set_chunk_active"],
)
def test_rag_unavailable_renders_502_without_details(env, operation):
    """R18: RAG caído, 401/5xx o cuerpo inválido -> 502 con página fija."""
    _login_ok(env)
    csrf = _csrf(env)
    env.rag.errors[operation] = ServiceUnavailable("detalle interno")

    if operation == "list_manuals":
        response = env.client.get("/admin/manuals")
    elif operation == "list_chunks":
        response = env.client.get("/admin/manuals/m1")
    elif operation == "upload_manual":
        response = env.client.post(
            "/admin/manuals",
            files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
            data={"name": "Manual", "csrf_token": csrf},
            follow_redirects=False,
        )
    elif operation == "update_chunk":
        response = env.client.post(
            "/admin/chunks/c1",
            data={"text": "texto", "csrf_token": csrf},
            follow_redirects=False,
        )
    else:
        response = env.client.post(
            "/admin/chunks/c1/active",
            data={"active": "true", "csrf_token": csrf},
            follow_redirects=False,
        )

    assert response.status_code == 502
    assert "detalle interno" not in response.text
    assert "no está disponible" in response.text


def test_new_admin_routes_redirect_without_session_before_calling_rag(env):
    """R19: sin sesión admin -> 303 a /admin/login sin llamar al RAG."""
    requests = [
        ("get", "/admin/manuals", {}),
        ("get", "/admin/manuals/m1", {}),
        ("post", "/admin/manuals", {"data": {"name": "Manual"}}),
        ("post", "/admin/chunks/c1", {"data": {"text": "texto"}}),
        ("post", "/admin/chunks/c1/active", {"data": {"active": "true"}}),
    ]
    for method, path, kwargs in requests:
        response = env.client.request(
            method, path, follow_redirects=False, **kwargs
        )
        assert response.status_code == 303, path
        assert response.headers["location"] == "/admin/login"
    assert env.rag.admin_calls == []


@pytest.mark.parametrize("csrf_value", [None, "token-equivocado"])
def test_new_admin_posts_require_csrf_before_calling_rag(env, csrf_value):
    """R20: POST sin csrf o con otro token -> 403 sin llamar al RAG."""
    _login_ok(env)
    before = list(env.rag.admin_calls)

    def form(extra: dict) -> dict:
        data = dict(extra)
        if csrf_value is not None:
            data["csrf_token"] = csrf_value
        return data

    responses = [
        env.client.post(
            "/admin/manuals",
            files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
            data=form({"name": "Manual"}),
            follow_redirects=False,
        ),
        env.client.post(
            "/admin/chunks/c1", data=form({"text": "texto"}), follow_redirects=False
        ),
        env.client.post(
            "/admin/chunks/c1/active",
            data=form({"active": "true"}),
            follow_redirects=False,
        ),
    ]
    assert [response.status_code for response in responses] == [403, 403, 403]
    assert env.rag.admin_calls == before


def test_service_token_never_reaches_the_browser(env):
    """R21: SERVICE_TOKEN no aparece en cuerpo, cabeceras ni cookies de las vistas."""
    _login_ok(env)
    csrf = _csrf(env)
    responses = [
        env.client.get("/admin/manuals"),
        env.client.get("/admin/manuals/m1"),
        env.client.post(
            "/admin/manuals",
            files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
            data={"name": "Manual", "csrf_token": csrf},
            follow_redirects=False,
        ),
    ]
    env.settings.admin_manual_max_bytes = 2
    responses.append(
        env.client.post(
            "/admin/manuals",
            files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
            data={"name": "Manual", "csrf_token": csrf},
            follow_redirects=False,
        )
    )
    responses.append(
        env.client.post(
            "/admin/chunks/c1", data={"csrf_token": csrf}, follow_redirects=False
        )
    )
    responses.append(
        env.client.post(
            "/admin/chunks/c1/active",
            data={"active": "malo", "csrf_token": csrf},
            follow_redirects=False,
        )
    )
    env.rag.errors["list_chunks"] = RagRejected("not_found", 404)
    responses.append(env.client.get("/admin/manuals/no-existe"))
    env.rag.errors["list_manuals"] = ServiceUnavailable("x")
    responses.append(env.client.get("/admin/manuals"))

    for response in responses:
        haystack = response.text + str(response.headers) + str(response.cookies)
        assert SERVICE_TOKEN not in haystack


def test_new_admin_html_has_security_headers_and_no_external_resources(env):
    """R22: las respuestas HTML nuevas llevan CSP, nosniff, no-store y nada externo."""
    _login_ok(env)
    csrf = _csrf(env)
    responses = [
        env.client.get("/admin/manuals"),
        env.client.get("/admin/manuals/m1"),
        env.client.post(
            "/admin/chunks/c1", data={"csrf_token": csrf}, follow_redirects=False
        ),
        env.client.post(
            "/admin/chunks/c1/active",
            data={"active": "malo", "csrf_token": csrf},
            follow_redirects=False,
        ),
    ]
    env.settings.admin_manual_max_bytes = 2
    responses.append(
        env.client.post(
            "/admin/manuals",
            files={"file": ("m.pdf", b"%PDF-1.4", "application/pdf")},
            data={"name": "Manual", "csrf_token": csrf},
            follow_redirects=False,
        )
    )
    env.rag.errors["list_chunks"] = RagRejected("not_found", 404)
    responses.append(env.client.get("/admin/manuals/no-existe"))
    env.rag.errors["list_manuals"] = ServiceUnavailable("x")
    responses.append(env.client.get("/admin/manuals"))

    for response in responses:
        assert response.status_code in {200, 404, 413, 422, 502}
        _secure_html(response)


# ── Adaptador HttpRagClient ─────────────────────────────────────────────────


@pytest.fixture()
def http_calls(monkeypatch):
    requests: list[tuple[httpx.Request, float]] = []
    queues: dict[str, deque] = defaultdict(deque)

    def handler(request: httpx.Request) -> httpx.Response:
        return queues[request.method].popleft()

    def fake(method: str):
        def inner(url, *, timeout=None, **kwargs):
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                request = client.build_request(method, url, **kwargs)
                requests.append((request, timeout))
                return client.send(request)

        return inner

    for method in ("get", "post", "patch"):
        monkeypatch.setattr(httpx, method, fake(method.upper()))
    return requests, queues


def _chunk_json(**changes) -> dict:
    data = {
        "chunk_id": "c1",
        "manual_id": "m1",
        "manual": "Manual Uno",
        "order": 1,
        "text": "texto",
        "active": True,
    }
    data.update(changes)
    return data


def test_http_rag_list_manuals_sends_token_and_parses_list(http_calls):
    """R10: GET /manuals con X-Service-Token y validación del contrato."""
    requests, queues = http_calls
    queues["GET"].append(
        httpx.Response(
            200, json=[{"manual_id": "m1", "name": "Manual Uno", "chunks": 2}]
        )
    )

    result = HttpRagClient("http://rag:8000/", "tok", 3).list_manuals()

    assert result[0].manual_id == "m1" and result[0].chunks == 2
    request, timeout = requests[0]
    assert str(request.url) == "http://rag:8000/manuals"
    assert request.headers["X-Service-Token"] == "tok"
    assert timeout == 3


def test_http_rag_list_chunks_escapes_the_manual_id(http_calls):
    """R10: el id se escapa en la URL de GET /manuals/{id}/chunks."""
    requests, queues = http_calls
    queues["GET"].append(httpx.Response(200, json=[]))

    assert HttpRagClient("http://rag", "tok").list_chunks("m/1") == []
    assert "m%2F1" in str(requests[0][0].url)


def test_http_rag_upload_manual_sends_multipart_and_token(http_calls):
    """R10: POST /manuals multipart con token y archivo."""
    requests, queues = http_calls
    queues["POST"].append(
        httpx.Response(201, json={"manual_id": "m1", "chunks": 2})
    )

    result = HttpRagClient("http://rag", "tok", 2).upload_manual(
        "Manual Uno", "manual.pdf", b"%PDF-1.4 datos", "application/pdf"
    )

    assert result.manual_id == "m1" and result.chunks == 2
    request, timeout = requests[0]
    assert request.method == "POST"
    assert request.headers["X-Service-Token"] == "tok"
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="name"' in request.content
    assert b'filename="manual.pdf"' in request.content
    assert timeout == 2


def test_http_rag_update_chunk_sends_json_and_escapes_id(http_calls):
    """R13: PATCH /chunks/{id} con token y el texto en JSON."""
    requests, queues = http_calls
    queues["PATCH"].append(httpx.Response(200, json=_chunk_json(text="nuevo")))

    result = HttpRagClient("http://rag", "tok").update_chunk("c/1", "nuevo")

    assert result.text == "nuevo"
    request, _ = requests[0]
    assert "c%2F1" in str(request.url)
    assert request.headers["X-Service-Token"] == "tok"
    assert json.loads(request.content) == {"text": "nuevo"}


def test_http_rag_set_chunk_active_sends_boolean(http_calls):
    """R15: PATCH /chunks/{id}/active con el booleano en JSON."""
    requests, queues = http_calls
    queues["PATCH"].append(httpx.Response(200, json=_chunk_json(active=False)))

    result = HttpRagClient("http://rag", "tok").set_chunk_active("c1", False)

    assert result.active is False
    request, _ = requests[0]
    assert request.headers["X-Service-Token"] == "tok"
    assert json.loads(request.content) == {"active": False}


def test_http_rag_maps_404_415_and_422_to_rag_rejected(http_calls):
    """R17: RAG 404/415/422 -> RagRejected con el mismo status y código."""
    requests, queues = http_calls
    client = HttpRagClient("http://rag", "tok")

    queues["GET"].append(
        httpx.Response(404, json={"error": "not_found", "message": "no"})
    )
    with pytest.raises(RagRejected) as not_found:
        client.list_chunks("no-existe")
    assert (not_found.value.status_code, not_found.value.code) == (404, "not_found")

    queues["POST"].append(
        httpx.Response(
            415, json={"error": "unsupported_format", "message": "formato"}
        )
    )
    with pytest.raises(RagRejected) as unsupported:
        client.upload_manual("M", "m.txt", b"x", "text/plain")
    assert (unsupported.value.status_code, unsupported.value.code) == (
        415,
        "unsupported_format",
    )

    queues["PATCH"].append(
        httpx.Response(422, json={"error": "validation_error", "message": "mal"})
    )
    with pytest.raises(RagRejected) as invalid:
        client.update_chunk("c1", "x")
    assert (invalid.value.status_code, invalid.value.code) == (422, "validation_error")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": "unauthorized", "message": "token"}),
        httpx.Response(500, text="error"),
        httpx.Response(200, json={"raro": 1}),
        httpx.Response(404, json={"error": "otro", "message": "x"}),
    ],
    ids=["401", "500", "invalid_body", "invalid_error_code"],
)
def test_http_rag_turns_other_failures_into_service_unavailable(http_calls, response):
    """R18: 401, 5xx o cuerpo que no valida -> ServiceUnavailable (502 en la vista)."""
    requests, queues = http_calls
    queues["GET"].append(response)
    with pytest.raises(ServiceUnavailable):
        HttpRagClient("http://rag", "tok").list_manuals()
