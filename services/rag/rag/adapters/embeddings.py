"""Cliente de embeddings (compatible con /embeddings de OpenAI) y su versión falsa."""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Protocol

import httpx

from ..domain import EmbeddingsUnavailable

logger = logging.getLogger(__name__)


class EmbeddingsClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HttpEmbeddingsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout: float = 10,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._timeout = timeout
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {"model": self._model, "input": texts}
        try:
            if self._client is not None:
                response = self._client.post(
                    self._url, json=payload, headers=headers, timeout=self._timeout
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(self._url, json=payload, headers=headers)
            if response.status_code // 100 != 2:
                logger.error("embeddings: respuesta %s", response.status_code)
                raise EmbeddingsUnavailable("El proveedor de embeddings respondió con error.")
            data = response.json()["data"]
            items = sorted(data, key=lambda d: d.get("index", 0))
            vectors = [[float(x) for x in item["embedding"]] for item in items]
        except EmbeddingsUnavailable:
            raise
        except Exception as exc:
            logger.error("embeddings: fallo (%s)", type(exc).__name__)
            raise EmbeddingsUnavailable("No se pudo contactar con embeddings.") from exc
        if len(vectors) != len(texts) or any(len(v) != self._dim for v in vectors):
            logger.error("embeddings: forma o dimensión inesperada")
            raise EmbeddingsUnavailable("Respuesta de embeddings inesperada.")
        return vectors


class FakeEmbeddings:
    """Determinista y sin red: hash por palabra a un vector normalizado."""

    def __init__(self, dim: int = 64, fail: bool = False) -> None:
        self.dim = dim
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            raise EmbeddingsUnavailable("fake embeddings failure")
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            vec[0] = 1.0
            return vec
        return [x / norm for x in vec]
