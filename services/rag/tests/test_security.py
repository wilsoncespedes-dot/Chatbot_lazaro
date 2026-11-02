"""Tests del token de servicio en /manuals y /search."""
from __future__ import annotations

import re

from fastapi.routing import APIRoute

from rag_tests_fakes import make_pdf

_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _unauth(response):
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_all_non_health_routes_require_service_token(env):
    """R30: toda ruta distinta de /health responde 401 sin token válido."""
    routes = []
    for route in env.client.app.routes:
        if isinstance(route, APIRoute) and route.path != "/health":
            method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
            routes.append((method, _PATH_PARAM.sub("x", route.path)))
    assert routes
    for method, path in routes:
        response = env.client.request(method, path)
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["error"] == "unauthorized"


def test_manuals_without_token_returns_401(env):
    """R18: /manuals sin token -> 401 y no se ingiere nada."""
    _unauth(env.upload(make_pdf("hola mundo"), headers={}))
    assert env.repo.chunks == [] and env.embeddings.calls == []


def test_search_without_token_returns_401(env):
    """R18: /search sin token -> 401."""
    _unauth(env.search(headers={}))


def test_search_with_wrong_token_returns_401_and_no_embedding_call(env):
    """R18: token incorrecto -> 401 y no se llama a embeddings."""
    _unauth(env.search(headers={"X-Service-Token": "mal"}))
    assert env.embeddings.calls == []
