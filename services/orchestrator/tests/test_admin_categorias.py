"""Tests del panel de categorías del clasificador (#25)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository, PostgresRepository, _SCHEMA
from orchestrator.classifier import Category
from orchestrator.config import Settings
from orchestrator.domain import Adapters
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token-centinela"
PASSWORD = "clave-segura-123"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
INTERNAL_HEADERS = {"X-Service-Token": SERVICE_TOKEN}


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    settings: Settings
    clock: list[datetime] = field(default_factory=lambda: [FIXED_NOW])


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
    )
    clock = [FIXED_NOW]
    repo = FakeRepository()
    counter = iter(range(1, 10_000))
    adapters = Adapters(
        repository=repo,
        rag=FakeRagClient(),
        llm=FakeLLM(reply=""),
        gateway=FakeGatewayClient(),
        handover=FakeHandoverClient(),
        db_query=FakeDbQuery(),
        clock=lambda: clock[0],
        new_id=lambda: f"gen-{next(counter)}",
    )
    client = TestClient(create_app(settings, adapters))
    created = client.post(
        "/profiles",
        json={"username": "admin1", "role": "admin", "password": PASSWORD},
        headers=INTERNAL_HEADERS,
    )
    assert created.status_code == 201, created.text
    return Env(client=client, repo=repo, settings=settings, clock=clock)


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


def _seed(
    env: Env,
    category_id: str = "cat-1",
    code: str = "facturacion",
    name: str = "Facturación",
    keywords: tuple[str, ...] = ("factura", "pago"),
    active: bool = True,
) -> Category:
    category = Category(
        id=category_id, code=code, name=name, keywords=keywords, active=active
    )
    assert env.repo.create_category(category, FIXED_NOW) is True
    return category


def _snapshot(env: Env) -> tuple:
    return dict(env.repo.categories), env.repo.classifier_threshold


def _secure_html(response) -> None:
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


# --- R1: listado --------------------------------------------------------------------


def test_categories_page_lists_active_and_inactive_with_threshold(env):
    """R1: lista todas las categorías y el umbral vigente."""
    _seed(env)
    _seed(env, "cat-2", "soporte", "Soporte", ("error",), active=False)
    env.repo.set_classifier_threshold(0.7)
    _login_ok(env)

    response = env.client.get("/admin/categories")

    assert response.status_code == 200
    text = response.text
    assert "facturacion" in text and "soporte" in text
    assert "Facturación" in text and "Soporte" in text
    assert "factura, pago" in text and "error" in text
    assert "Sí" in text and "No" in text
    assert "0.7" in text
    assert 'href="/admin/categories"' in text


def test_categories_page_uses_default_threshold_without_stored_value(env):
    """R1, R26: sin umbral guardado se muestra CLASSIFIER_DEFAULT_THRESHOLD."""
    _login_ok(env)
    response = env.client.get("/admin/categories")
    assert response.status_code == 200
    assert "0.6" in response.text


# --- R2, R3 y R4: alta, edición y estado -------------------------------------------


def test_create_category_redirects_and_stores_active(env):
    """R2: alta válida -> 303, categoría activa con nombre y keywords normalizados."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories",
        data={
            "csrf_token": csrf,
            "code": "facturacion",
            "name": "  Facturación  ",
            "keywords": "Factura, Pago",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/categories"
    stored = next(iter(env.repo.categories.values()))
    assert (stored.code, stored.name, stored.keywords) == (
        "facturacion",
        "Facturación",
        ("factura", "pago"),
    )
    assert stored.active is True


def test_update_category_keeps_code_and_active(env):
    """R3: la edición reemplaza nombre y keywords sin tocar code ni active."""
    _seed(env, active=False)
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/cat-1",
        data={"csrf_token": csrf, "name": "Cobros", "keywords": "cobro, recibo"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    stored = env.repo.categories["cat-1"]
    assert (stored.code, stored.name, stored.keywords, stored.active) == (
        "facturacion",
        "Cobros",
        ("cobro", "recibo"),
        False,
    )


@pytest.mark.parametrize("active", ["false", "true"])
def test_toggle_category_active(env, active):
    """R4: active true/false se guarda y responde 303."""
    _seed(env, active=active == "false")
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/cat-1/active",
        data={"csrf_token": csrf, "active": active},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert env.repo.categories["cat-1"].active is (active == "true")


# --- R5: validación ----------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        {"code": "1factura", "name": "Facturación", "keywords": "factura"},
        {"code": "Facturacion", "name": "Facturación", "keywords": "factura"},
        {"code": "facturacion", "name": "", "keywords": "factura"},
        {"code": "facturacion", "name": "a" * 61, "keywords": "factura"},
        {"code": "facturacion", "name": "Facturación", "keywords": ""},
    ],
    ids=["code", "uppercase_code", "empty_name", "long_name", "empty_keywords"],
)
def test_create_with_invalid_fields_returns_422_without_changes(env, data):
    """R5: un campo inválido en el alta -> 422 y ninguna categoría nueva."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories",
        data={"csrf_token": csrf, **data},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert env.repo.categories == {}


@pytest.mark.parametrize(
    "data",
    [
        {"name": "", "keywords": "factura"},
        {"name": "Facturación", "keywords": ""},
        {"name": "a" * 61, "keywords": "factura"},
    ],
    ids=["empty_name", "empty_keywords", "long_name"],
)
def test_update_with_invalid_fields_returns_422_without_changes(env, data):
    """R5: un campo inválido en la edición -> 422 sin modificar la categoría."""
    _seed(env)
    before = _snapshot(env)
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/cat-1",
        data={"csrf_token": csrf, **data},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert _snapshot(env) == before


@pytest.mark.parametrize("active", ["", "maybe", "1", "True", "false "])
def test_toggle_with_invalid_active_returns_422_without_changes(env, active):
    """R5: active distinto de true/false -> 422 sin modificar la categoría."""
    _seed(env, active=True)
    before = _snapshot(env)
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/cat-1/active",
        data={"csrf_token": csrf, "active": active},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert _snapshot(env) == before


# --- R6 y R7: conflictos y ausencias ------------------------------------------------


def test_duplicate_code_returns_409(env):
    """R6: un código repetido -> 409 category_code_taken sin cambios."""
    _seed(env)
    before = _snapshot(env)
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories",
        data={
            "csrf_token": csrf,
            "code": "facturacion",
            "name": "Otra",
            "keywords": "otra",
        },
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert "category_code_taken" in response.text
    assert _snapshot(env) == before


def test_update_unknown_category_returns_404(env):
    """R7: editar un id inexistente -> 404 category_not_found."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/no-existe",
        data={"csrf_token": csrf, "name": "Nombre", "keywords": "clave"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert "category_not_found" in response.text


def test_toggle_unknown_category_returns_404(env):
    """R7: cambiar el estado de un id inexistente -> 404 category_not_found."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/no-existe/active",
        data={"csrf_token": csrf, "active": "false"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert "category_not_found" in response.text


# --- R8 y R9: umbral ---------------------------------------------------------------


def test_threshold_is_saved_and_shown(env):
    """R8: un umbral válido se guarda y responde 303."""
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/threshold",
        data={"csrf_token": csrf, "threshold": "0.42"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert env.repo.classifier_threshold == 0.42
    assert "0.42" in env.client.get("/admin/categories").text


@pytest.mark.parametrize(
    "value", ["", "texto", "nan", "inf", "-0.1", "1.01"],
    ids=["empty", "text", "nan", "inf", "negative", "above"],
)
def test_invalid_threshold_returns_422_without_changes(env, value):
    """R9: umbral inválido -> 422 y el guardado no cambia."""
    env.repo.set_classifier_threshold(0.33)
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/categories/threshold",
        data={"csrf_token": csrf, "threshold": value},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert env.repo.classifier_threshold == 0.33


# --- R10 y R11: sesión y CSRF ------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("get", "/admin/categories", {}),
        ("post", "/admin/categories", {"code": "c", "name": "N", "keywords": "k"}),
        ("post", "/admin/categories/cat-1", {"name": "N", "keywords": "k"}),
        ("post", "/admin/categories/cat-1/active", {"active": "false"}),
        ("post", "/admin/categories/threshold", {"threshold": "0.5"}),
    ],
)
def test_categories_without_session_redirect_before_changes(env, method, path, data):
    """R10: sin sesión -> 303 a /admin/login sin leer ni modificar nada."""
    _seed(env)
    before = _snapshot(env)
    kwargs = {"follow_redirects": False}
    if method == "post":
        kwargs["data"] = data

    response = env.client.request(method, path, **kwargs)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert _snapshot(env) == before


@pytest.mark.parametrize("csrf_value", [None, "token-equivocado"])
@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("/admin/categories", {"code": "nueva", "name": "Nueva", "keywords": "k"}),
        ("/admin/categories/cat-1", {"name": "Nueva", "keywords": "k"}),
        ("/admin/categories/cat-1/active", {"active": "false"}),
        ("/admin/categories/threshold", {"threshold": "0.5"}),
    ],
)
def test_categories_posts_require_csrf(env, csrf_value, path, data):
    """R11: POST sin CSRF o con otro token -> 403 sin modificar nada."""
    _seed(env)
    before = _snapshot(env)
    _login_ok(env)
    body = dict(data)
    if csrf_value is not None:
        body["csrf_token"] = csrf_value

    response = env.client.post(path, data=body, follow_redirects=False)

    assert response.status_code == 403
    assert _snapshot(env) == before


# --- R12: escapado y cabeceras -----------------------------------------------------


def test_category_values_are_escaped_and_headers_are_secure(env):
    """R12: name y keywords se escapan y la página lleva cabeceras de seguridad."""
    _seed(
        env,
        name="<script>alert(1)</script>",
        keywords=("<b>factura</b>",),
    )
    _login_ok(env)
    response = env.client.get("/admin/categories")

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<b>factura</b>" not in response.text
    assert "&lt;b&gt;factura&lt;/b&gt;" in response.text
    _secure_html(response)


def test_error_pages_keep_security_headers(env):
    """R12: las respuestas de error del panel conservan las cabeceras de seguridad."""
    _seed(env)
    _login_ok(env)
    csrf = _csrf(env)
    responses = [
        env.client.post(
            "/admin/categories",
            data={"csrf_token": csrf, "code": "X", "name": "N", "keywords": "k"},
            follow_redirects=False,
        ),
        env.client.post(
            "/admin/categories",
            data={
                "csrf_token": csrf,
                "code": "facturacion",
                "name": "N",
                "keywords": "k",
            },
            follow_redirects=False,
        ),
        env.client.post(
            "/admin/categories/no-existe",
            data={"csrf_token": csrf, "name": "N", "keywords": "k"},
            follow_redirects=False,
        ),
    ]
    assert [response.status_code for response in responses] == [422, 409, 404]
    for response in responses:
        _secure_html(response)


# --- R27: persistencia -------------------------------------------------------------


def test_schema_creates_category_and_settings_tables():
    """R27: el esquema crea query_categories (code UNIQUE) y app_settings."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS query_categories" in schema
    assert "code TEXT UNIQUE NOT NULL" in schema
    assert "CREATE TABLE IF NOT EXISTS app_settings" in schema


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        sql = self.log[-1][0]
        if "FROM query_categories" in sql:
            return [("cat-1", "facturacion", "Facturación", "factura\npago", True)]
        if "FROM app_settings" in sql:
            return [("0.6",)]
        if "RETURNING id" in sql:
            return [("cat-1",)]
        return []


class _Conn:
    def __init__(self):
        self.log: list = []

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_category_queries_use_parameters_only():
    """R27: todas las consultas de categorías y umbral usan SQL parametrizado."""
    conn = _Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "nuevo")
    secret = "'; DROP TABLE query_categories; --"
    category = Category(
        id="cat-1",
        code="facturacion",
        name=secret,
        keywords=(secret,),
        active=True,
    )
    repo.list_categories()
    repo.create_category(category, FIXED_NOW)
    repo.update_category("cat-1", secret, (secret,))
    repo.set_category_active("cat-1", False)
    repo.get_classifier_threshold()
    repo.set_classifier_threshold(0.5)

    statements = [(sql, params) for sql, params in conn.log if not sql.startswith("CREATE")]
    assert len(statements) == 6
    for sql, params in statements:
        assert secret not in sql
        assert sql.count("%s") == len(params)
    assert any(secret in params for _, params in statements)
    assert any("classifier_threshold" in params for _, params in statements)
