"""Contratos HTTP/JSON entre los servicios del chatbot (ver contracts/CONTRATOS.md)."""
from __future__ import annotations

from .cases import (
    CaseCloseRequest,
    CaseCloseResponse,
    CaseReplyRequest,
    CaseReplyResponse,
    CheckTimeoutsRequest,
    CheckTimeoutsResponse,
    HandoverReason,
    HandoverRequest,
    HandoverResponse,
    LastMessage,
)
from .common import (
    MAX_IDENTIFIER_LENGTH,
    MAX_LAST_MESSAGES,
    MAX_MANUAL_NAME_LENGTH,
    MAX_TEXT_LENGTH,
    MAX_TOP_K,
    SERVICE_TOKEN_HEADER,
    ContractModel,
    ErrorResponse,
    HealthResponse,
    Identifier,
    MessageText,
)
from .manuals import ManualUploadRequest, ManualUploadResponse
from .messages import MessageRequest, MessageResponse, SendRequest, SendResponse
from .search import SearchRequest, SearchResponse, SearchResult

__all__ = [
    "MessageRequest",
    "MessageResponse",
    "SendRequest",
    "SendResponse",
    "SearchRequest",
    "SearchResult",
    "SearchResponse",
    "HandoverRequest",
    "LastMessage",
    "HandoverResponse",
    "CaseReplyRequest",
    "CaseReplyResponse",
    "ManualUploadRequest",
    "ManualUploadResponse",
    "CaseCloseRequest",
    "CaseCloseResponse",
    "CheckTimeoutsRequest",
    "CheckTimeoutsResponse",
    "ErrorResponse",
    "HealthResponse",
    "SERVICE_TOKEN_HEADER",
    "MAX_TEXT_LENGTH",
    "MAX_LAST_MESSAGES",
    "MAX_TOP_K",
    "MAX_IDENTIFIER_LENGTH",
    "MAX_MANUAL_NAME_LENGTH",
    "ContractModel",
    "Identifier",
    "MessageText",
    "HandoverReason",
]
