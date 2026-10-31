"""Cliente de RAG (POST /search) con versión falsa."""
from __future__ import annotations

import logging
from typing import Protocol

import httpx
from lazaro_contracts import SERVICE_TOKEN_HEADER, SearchRequest, SearchResponse, SearchResult
from pydantic import ValidationError

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class RagClient(Protocol):
    def search(self, query: str, top_k: int) -> list[SearchResult]: ...


class HttpRagClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        body = SearchRequest(query=query, top_k=top_k)
        try:
            response = httpx.post(
                f"{self._base_url}/search",
                content=body.model_dump_json(exclude_none=True),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return SearchResponse.model_validate(response.json()).root
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            logger.error("rag_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("RAG no disponible.") from None


class FakeRagClient:
    def __init__(self, results: list[SearchResult] | None = None, fail: bool = False) -> None:
        self.results = results or []
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        self.calls.append((query, top_k))
        if self.fail:
            raise ServiceUnavailable("RAG caído")
        return list(self.results)
