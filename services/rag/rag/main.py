"""Aplicación FastAPI del servicio rag: token de servicio, errores y /health."""
from __future__ import annotations

import hmac
import logging

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChunkActiveRequest,
    ChunkItem,
    ChunkListResponse,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
    ErrorResponse,
    HealthResponse,
    ManualListResponse,
    ManualUploadRequest,
    ManualUploadResponse,
    SearchRequest,
    SearchResponse,
)
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings
from .adapters.embeddings import EmbeddingsClient, HttpEmbeddingsClient
from .adapters.repository import ChunkRepository, PgVectorChunkRepository
from .domain import (
    DomainError,
    ingest_manual,
    list_manual_chunks,
    list_manuals,
    search_chunks,
    set_chunk_active,
    update_chunk_text,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "rag"
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def create_app(
    settings: Settings | None = None,
    embeddings: EmbeddingsClient | None = None,
    repository: ChunkRepository | None = None,
) -> FastAPI:
    settings = settings or Settings()
    # Adaptadores reales perezosos: no conectan ni llaman a la red al construirse.
    if embeddings is None:
        embeddings = HttpEmbeddingsClient(
            settings.embeddings_base_url,
            settings.embeddings_api_key,
            settings.embeddings_model,
            settings.embeddings_dim,
            settings.http_timeout_seconds,
        )
    if repository is None:
        repository = PgVectorChunkRepository(settings.database_url, settings.embeddings_dim)
    app = FastAPI(title=SERVICE_NAME)

    @app.middleware("http")
    async def verify_service_token(request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        token = request.headers.get(SERVICE_TOKEN_HEADER)
        expected = settings.service_token
        if (
            expected == ""
            or token is None
            or not hmac.compare_digest(token.encode(), expected.encode())
        ):
            return _error(401, "unauthorized", "Falta X-Service-Token o no es válido.")
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError):
        return _error(exc.status_code, exc.code, str(exc) or exc.code)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 405:
            code = "method_not_allowed"
        else:
            code = "http_error"
        return _error(exc.status_code, code, str(exc.detail) or code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return _error(422, "validation_error", "El cuerpo de la petición no es válido.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception("Excepción no controlada")
        return _error(500, "internal_error", "Error interno.")

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=SERVICE_NAME)

    @app.post("/manuals", status_code=201, response_model=ManualUploadResponse)
    def upload_manual(
        file: UploadFile = File(...), name: str = Form(...)
    ) -> ManualUploadResponse | JSONResponse:
        try:
            ManualUploadRequest(name=name)
        except ValidationError:
            return _error(422, "validation_error", "El nombre del manual no es válido.")
        data = file.file.read()
        return ingest_manual(data, name, settings, embeddings, repository)

    @app.get("/manuals", response_model=ManualListResponse)
    def read_manuals() -> ManualListResponse:
        return ManualListResponse(list_manuals(repository))

    @app.get("/manuals/{id}/chunks", response_model=ChunkListResponse)
    def read_manual_chunks(id: str) -> ChunkListResponse:
        return ChunkListResponse(list_manual_chunks(id, repository))

    @app.post("/search", response_model=SearchResponse)
    def search(body: SearchRequest) -> SearchResponse:
        results = search_chunks(body, settings, embeddings, repository)
        return SearchResponse(results)

    @app.patch("/chunks/{id}", response_model=ChunkUpdateResponse)
    def edit_chunk(id: str, body: ChunkUpdateRequest) -> ChunkUpdateResponse:
        return update_chunk_text(id, body, embeddings, repository)

    @app.patch("/chunks/{id}/active", response_model=ChunkItem)
    def change_chunk_active(id: str, body: ChunkActiveRequest) -> ChunkItem:
        return set_chunk_active(id, body, repository)

    return app


app = create_app()
