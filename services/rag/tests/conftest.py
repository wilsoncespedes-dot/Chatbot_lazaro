"""Fixtures del servicio rag: solo adaptadores falsos (sin red ni Postgres)."""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag.config import Settings
from rag.main import create_app

# `fakes.py` existe también en otros servicios: se carga con un nombre único.
_spec = importlib.util.spec_from_file_location(
    "rag_tests_fakes", Path(__file__).with_name("fakes.py")
)
rag_tests_fakes = importlib.util.module_from_spec(_spec)
sys.modules["rag_tests_fakes"] = rag_tests_fakes
_spec.loader.exec_module(rag_tests_fakes)

FakeChunkRepository = rag_tests_fakes.FakeChunkRepository
FakeEmbeddings = rag_tests_fakes.FakeEmbeddings

TOKEN = "svc-token"
HEADERS = {"X-Service-Token": TOKEN}


@dataclass
class Env:
    client: TestClient
    embeddings: FakeEmbeddings
    repo: FakeChunkRepository
    settings: Settings

    def upload(self, data: bytes, name: str = "Manual A", filename: str = "m.pdf",
               ctype: str = "application/pdf", headers: dict | None = None):
        return self.client.post(
            "/manuals",
            files={"file": (filename, data, ctype)},
            data={"name": name},
            headers=HEADERS if headers is None else headers,
        )

    def search(self, query: str = "hola", top_k: int = 5, headers: dict | None = None, **extra):
        return self.client.post(
            "/search",
            json={"query": query, "top_k": top_k, **extra},
            headers=HEADERS if headers is None else headers,
        )


def build_env(**overrides) -> Env:
    values = {
        "service_token": TOKEN, "chunk_size": 100, "chunk_overlap": 20,
        "rag_similarity_threshold": 0.5,
    }
    values.update(overrides)
    settings = Settings(**values)
    embeddings = FakeEmbeddings()
    repo = FakeChunkRepository()
    return Env(TestClient(create_app(settings, embeddings, repo)), embeddings, repo, settings)


@pytest.fixture()
def env() -> Env:
    return build_env()


@pytest.fixture()
def make_env():
    """Fábrica de entornos con ajustes distintos (umbral, tamaño de fragmento...)."""
    return build_env
