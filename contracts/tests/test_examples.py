"""Valida los ejemplos de contracts/examples/ contra sus modelos."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

import lazaro_contracts
from lazaro_contracts import (
    CaseAssignRequest,
    CaseAssignResponse,
    CaseAuthorizeRequest,
    CaseAuthorizeResponse,
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    CaseCloseRequest,
    CaseCloseResponse,
    CaseListQuery,
    CaseListResponse,
    CaseReplyRequest,
    CaseReplyResponse,
    CaseTransferRequest,
    CaseTransferResponse,
    ChannelCapabilities,
    ChannelSendRequest,
    CheckTimeoutsRequest,
    CheckTimeoutsResponse,
    ChunkActiveRequest,
    ChunkItem,
    ChunkListResponse,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
    ErrorResponse,
    ExpiryNoticeRunRequest,
    ExpiryNoticeRunResponse,
    HandoverRequest,
    HandoverResponse,
    HealthResponse,
    LinkBlock,
    ListBlock,
    ManualListResponse,
    ManualUploadRequest,
    ManualUploadResponse,
    MessageRequest,
    MessageResponse,
    NormalizedMessage,
    OptionsBlock,
    PrivacyPurgeRequest,
    PrivacyPurgeResponse,
    ResponseBlocks,
    SearchRequest,
    SearchResponse,
    SendRequest,
    SendResponse,
    TemplateBlock,
    TextBlock,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

EXAMPLES: dict[str, type[BaseModel]] = {
    "message_request.json": MessageRequest,
    "message_response.json": MessageResponse,
    "message_response_duplicate.json": MessageResponse,
    "normalized_message.json": NormalizedMessage,
    "normalized_button_message.json": NormalizedMessage,
    "channel_capabilities.json": ChannelCapabilities,
    "channel_send_request.json": ChannelSendRequest,
    "text_block.json": TextBlock,
    "options_block.json": OptionsBlock,
    "list_block.json": ListBlock,
    "link_block.json": LinkBlock,
    "template_block.json": TemplateBlock,
    "response_blocks.json": ResponseBlocks,
    "send_request.json": SendRequest,
    "send_response.json": SendResponse,
    "search_request.json": SearchRequest,
    "search_response.json": SearchResponse,
    "search_response_empty.json": SearchResponse,
    "handover_request.json": HandoverRequest,
    "handover_response.json": HandoverResponse,
    "handover_response_no_advisors.json": HandoverResponse,
    "case_reply_request.json": CaseReplyRequest,
    "case_reply_response.json": CaseReplyResponse,
    "manual_upload_request.json": ManualUploadRequest,
    "manual_upload_response.json": ManualUploadResponse,
    "case_close_request.json": CaseCloseRequest,
    "case_close_response.json": CaseCloseResponse,
    "case_assign_request.json": CaseAssignRequest,
    "case_assign_response.json": CaseAssignResponse,
    "case_authorize_request.json": CaseAuthorizeRequest,
    "case_authorize_response.json": CaseAuthorizeResponse,
    "case_transfer_request.json": CaseTransferRequest,
    "case_transfer_response.json": CaseTransferResponse,
    "case_client_message_request.json": CaseClientMessageRequest,
    "case_client_message_response.json": CaseClientMessageResponse,
    "case_client_message_response_not_assigned.json": CaseClientMessageResponse,
    "case_list_query.json": CaseListQuery,
    "case_list_response.json": CaseListResponse,
    "case_list_response_empty.json": CaseListResponse,
    "check_timeouts_request.json": CheckTimeoutsRequest,
    "check_timeouts_response.json": CheckTimeoutsResponse,
    "privacy_purge_request.json": PrivacyPurgeRequest,
    "privacy_purge_response.json": PrivacyPurgeResponse,
    "expiry_notice_run_request.json": ExpiryNoticeRunRequest,
    "expiry_notice_run_response.json": ExpiryNoticeRunResponse,
    "chunk_update_request.json": ChunkUpdateRequest,
    "chunk_update_response.json": ChunkUpdateResponse,
    "manual_list_response.json": ManualListResponse,
    "chunk_list_response.json": ChunkListResponse,
    "chunk_active_request.json": ChunkActiveRequest,
    "chunk_active_response.json": ChunkItem,
    "error_response.json": ErrorResponse,
    "health_response.json": HealthResponse,
}

MODEL_NAMES = [
    "MessageRequest",
    "MessageResponse",
    "NormalizedMessage",
    "ChannelCapabilities",
    "ChannelSendRequest",
    "TextBlock",
    "OptionsBlock",
    "ListBlock",
    "LinkBlock",
    "TemplateBlock",
    "ResponseBlocks",
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
    "CaseAssignRequest",
    "CaseAssignResponse",
    "CaseAuthorizeRequest",
    "CaseAuthorizeResponse",
    "CaseTransferRequest",
    "CaseTransferResponse",
    "CaseClientMessageRequest",
    "CaseClientMessageResponse",
    "CheckTimeoutsRequest",
    "CheckTimeoutsResponse",
    "PrivacyPurgeRequest",
    "PrivacyPurgeResponse",
    "ExpiryNoticeRunRequest",
    "ExpiryNoticeRunResponse",
    "ChunkUpdateRequest",
    "ChunkUpdateResponse",
    "ChunkItem",
    "ChunkListResponse",
    "ChunkActiveRequest",
    "ManualSummary",
    "ManualListResponse",
    "ErrorResponse",
    "HealthResponse",
]
NESTED_ONLY = {"SearchResult", "LastMessage", "ManualSummary"}


@pytest.mark.parametrize("filename", sorted(EXAMPLES))
def test_every_example_validates_against_its_model(filename: str) -> None:
    """R48: cada ejemplo valida con model_validate_json de su modelo."""
    text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
    EXAMPLES[filename].model_validate_json(text)


def test_every_example_file_is_mapped() -> None:
    """R49: todo .json de contracts/examples/ figura en EXAMPLES."""
    files = {path.name for path in EXAMPLES_DIR.glob("*.json")}
    assert files - set(EXAMPLES) == set()
    assert set(EXAMPLES) - files == set()


def test_every_model_has_an_example() -> None:
    """R47: cada modelo de R16 salvo SearchResult y LastMessage tiene un ejemplo."""
    mapped = {model.__name__ for model in EXAMPLES.values()}
    expected = set(MODEL_NAMES) - NESTED_ONLY
    assert expected - mapped == set()
    for name in expected:
        assert getattr(lazaro_contracts, name) in EXAMPLES.values()


def test_nested_models_are_covered_by_examples() -> None:
    """R47: SearchResult y LastMessage aparecen anidados en sus ejemplos."""
    results = SearchResponse.model_validate_json(
        (EXAMPLES_DIR / "search_response.json").read_text(encoding="utf-8")
    )
    handover = HandoverRequest.model_validate_json(
        (EXAMPLES_DIR / "handover_request.json").read_text(encoding="utf-8")
    )
    assert len(results.root) >= 1
    assert len(handover.last_messages) >= 1
