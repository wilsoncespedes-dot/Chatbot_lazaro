"""Cliente de RAG (búsqueda y administración de manuales) con versión falsa."""
from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import quote

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChunkActiveRequest,
    ChunkItem,
    ChunkListResponse,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
    ErrorResponse,
    ManualListResponse,
    ManualSummary,
    ManualUploadRequest,
    ManualUploadResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from pydantic import BaseModel, ValidationError

from ..domain import RagRejected, ServiceUnavailable

logger = logging.getLogger(__name__)

_REJECT_STATUSES = {404, 415, 422}
_REJECT_CODES = {"not_found", "unsupported_format", "validation_error", "empty_document"}


class RagClient(Protocol):
    def search(self, query: str, top_k: int) -> list[SearchResult]: ...

    def list_manuals(self) -> list[ManualSummary]: ...

    def list_chunks(self, manual_id: str) -> list[ChunkItem]: ...

    def upload_manual(
        self, name: str, filename: str, content: bytes, content_type: str
    ) -> ManualUploadResponse: ...

    def update_chunk(self, chunk_id: str, text: str) -> ChunkUpdateResponse: ...

    def set_chunk_active(self, chunk_id: str, active: bool) -> ChunkItem: ...


class HttpRagClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        model: type[BaseModel],
        *,
        ok_status: int = 200,
        **kwargs,
    ) -> BaseModel:
        headers = {SERVICE_TOKEN_HEADER: self._service_token}
        if "content" in kwargs:
            headers["Content-Type"] = "application/json"
        try:
            response = getattr(httpx, method)(
                f"{self._base_url}{path}",
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            logger.error("rag_admin_error operation=%s code=%s", method, type(exc).__name__)
            raise ServiceUnavailable("RAG no disponible.") from None

        if response.status_code in _REJECT_STATUSES:
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("rag_admin_error operation=%s code=invalid_response", method)
                raise ServiceUnavailable("RAG no disponible.") from None
            if error.error not in _REJECT_CODES:
                logger.error("rag_admin_error operation=%s code=invalid_code", method)
                raise ServiceUnavailable("RAG no disponible.") from None
            raise RagRejected(error.error, response.status_code)

        if response.status_code != ok_status:
            logger.error("rag_admin_error operation=%s code=%s", method, response.status_code)
            raise ServiceUnavailable("RAG no disponible.")

        try:
            return model.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            logger.error(
                "rag_admin_error operation=%s code=%s", method, type(exc).__name__
            )
            raise ServiceUnavailable("RAG no disponible.") from None

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

    def list_manuals(self) -> list[ManualSummary]:
        response = self._request("get", "/manuals", ManualListResponse)
        return response.root  # type: ignore[attr-defined]

    def list_chunks(self, manual_id: str) -> list[ChunkItem]:
        path = f"/manuals/{quote(manual_id, safe='')}/chunks"
        response = self._request("get", path, ChunkListResponse)
        return response.root  # type: ignore[attr-defined]

    def upload_manual(
        self, name: str, filename: str, content: bytes, content_type: str
    ) -> ManualUploadResponse:
        ManualUploadRequest(name=name)
        return self._request(
            "post",
            "/manuals",
            ManualUploadResponse,
            ok_status=201,
            files={"file": (filename, content, content_type)},
            data={"name": name},
        )  # type: ignore[return-value]

    def update_chunk(self, chunk_id: str, text: str) -> ChunkUpdateResponse:
        body = ChunkUpdateRequest(text=text)
        return self._request(
            "patch",
            f"/chunks/{quote(chunk_id, safe='')}",
            ChunkUpdateResponse,
            content=body.model_dump_json(),
        )  # type: ignore[return-value]

    def set_chunk_active(self, chunk_id: str, active: bool) -> ChunkItem:
        body = ChunkActiveRequest(active=active)
        return self._request(
            "patch",
            f"/chunks/{quote(chunk_id, safe='')}/active",
            ChunkItem,
            content=body.model_dump_json(),
        )  # type: ignore[return-value]


class FakeRagClient:
    def __init__(
        self,
        results: list[SearchResult] | None = None,
        fail: bool = False,
        manuals: list[ManualSummary] | None = None,
        chunks: dict[str, list[ChunkItem]] | None = None,
        upload_response: ManualUploadResponse | None = None,
        update_response: ChunkUpdateResponse | None = None,
        active_response: ChunkItem | None = None,
    ) -> None:
        self.results = results or []
        self.fail = fail
        self.calls: list[tuple[str, int]] = []
        self.admin_calls: list[tuple] = []
        self.manuals = manuals or []
        self.chunks = chunks or {}
        self.upload_response = upload_response
        self.update_response = update_response
        self.active_response = active_response
        self.errors: dict[str, BaseException] = {}

    def _raise_if_configured(self, operation: str) -> None:
        error = self.errors.get(operation)
        if error is not None:
            raise error

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        self.calls.append((query, top_k))
        if self.fail:
            raise ServiceUnavailable("RAG caído")
        return list(self.results)

    def list_manuals(self) -> list[ManualSummary]:
        self.admin_calls.append(("list_manuals",))
        self._raise_if_configured("list_manuals")
        return list(self.manuals)

    def list_chunks(self, manual_id: str) -> list[ChunkItem]:
        self.admin_calls.append(("list_chunks", manual_id))
        self._raise_if_configured("list_chunks")
        return list(self.chunks.get(manual_id, []))

    def upload_manual(
        self, name: str, filename: str, content: bytes, content_type: str
    ) -> ManualUploadResponse:
        self.admin_calls.append(("upload_manual", name, filename, content, content_type))
        self._raise_if_configured("upload_manual")
        if self.upload_response is not None:
            return self.upload_response
        return ManualUploadResponse(manual_id="manual-nuevo", chunks=1)

    def update_chunk(self, chunk_id: str, text: str) -> ChunkUpdateResponse:
        self.admin_calls.append(("update_chunk", chunk_id, text))
        self._raise_if_configured("update_chunk")
        if self.update_response is not None:
            return self.update_response
        return ChunkUpdateResponse(
            chunk_id=chunk_id,
            manual_id="manual-1",
            manual="Manual A",
            order=1,
            text=text,
            active=True,
        )

    def set_chunk_active(self, chunk_id: str, active: bool) -> ChunkItem:
        self.admin_calls.append(("set_chunk_active", chunk_id, active))
        self._raise_if_configured("set_chunk_active")
        if self.active_response is not None:
            return self.active_response
        return ChunkItem(
            chunk_id=chunk_id,
            manual_id="manual-1",
            manual="Manual A",
            order=1,
            text="texto",
            active=active,
        )
