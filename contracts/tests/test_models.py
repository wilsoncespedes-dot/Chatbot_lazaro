"""Rechazos y límites de los modelos de lazaro_contracts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from lazaro_contracts import (
    MAX_IDENTIFIER_LENGTH,
    MAX_LAST_MESSAGES,
    MAX_MANUAL_NAME_LENGTH,
    MAX_TEXT_LENGTH,
    MAX_TOP_K,
    CaseAssignRequest,
    CaseAssignResponse,
    CaseAuthorizeAction,
    CaseAuthorizeRequest,
    CaseAuthorizeResponse,
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    CaseCloseRequest,
    CaseCloseResponse,
    CaseReplyRequest,
    CaseReplyResponse,
    CheckTimeoutsRequest,
    CheckTimeoutsResponse,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
    ContractModel,
    ErrorResponse,
    HandoverRequest,
    HandoverResponse,
    HealthResponse,
    LastMessage,
    ManualUploadRequest,
    ManualUploadResponse,
    MessageRequest,
    MessageResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SendRequest,
    SendResponse,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# Ejemplo base de cada modelo de R16. SearchResult y LastMessage se toman anidados.
BASE_EXAMPLES: dict[type[BaseModel], tuple[str, str | None]] = {
    MessageRequest: ("message_request.json", None),
    MessageResponse: ("message_response.json", None),
    SendRequest: ("send_request.json", None),
    SendResponse: ("send_response.json", None),
    SearchRequest: ("search_request.json", None),
    SearchResult: ("search_response.json", "first"),
    SearchResponse: ("search_response.json", None),
    HandoverRequest: ("handover_request.json", None),
    LastMessage: ("handover_request.json", "last_messages"),
    HandoverResponse: ("handover_response.json", None),
    CaseReplyRequest: ("case_reply_request.json", None),
    CaseReplyResponse: ("case_reply_response.json", None),
    ManualUploadRequest: ("manual_upload_request.json", None),
    ManualUploadResponse: ("manual_upload_response.json", None),
    CaseCloseRequest: ("case_close_request.json", None),
    CaseCloseResponse: ("case_close_response.json", None),
    CaseAssignRequest: ("case_assign_request.json", None),
    CaseAssignResponse: ("case_assign_response.json", None),
    CaseAuthorizeRequest: ("case_authorize_request.json", None),
    CaseAuthorizeResponse: ("case_authorize_response.json", None),
    CaseClientMessageRequest: ("case_client_message_request.json", None),
    CaseClientMessageResponse: ("case_client_message_response.json", None),
    CheckTimeoutsRequest: ("check_timeouts_request.json", None),
    CheckTimeoutsResponse: ("check_timeouts_response.json", None),
    ChunkUpdateRequest: ("chunk_update_request.json", None),
    ChunkUpdateResponse: ("chunk_update_response.json", None),
    ErrorResponse: ("error_response.json", None),
    HealthResponse: ("health_response.json", None),
}

OBJECT_MODELS = [model for model in BASE_EXAMPLES if model is not SearchResponse]


def _example(model: type[BaseModel]) -> Any:
    filename, nested = BASE_EXAMPLES[model]
    data = json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))
    if nested == "first":
        return copy.deepcopy(data[0])
    if nested is not None:
        return copy.deepcopy(data[nested][0])
    return data


def _validate(model: type[BaseModel], data: Any) -> BaseModel:
    return model.model_validate_json(json.dumps(data))


def _with(model: type[BaseModel], **changes: Any) -> Any:
    data = _example(model)
    data.update(changes)
    return data


def _required_cases() -> list[tuple[type[BaseModel], str]]:
    cases = []
    for model in BASE_EXAMPLES:
        fields_model = SearchResult if model is SearchResponse else model
        for name, field in fields_model.model_fields.items():
            if field.is_required():
                cases.append((model, name))
    return cases


# ── Parte 1: genérica, derivada de los ejemplos ──────────────────────────────


@pytest.mark.parametrize(
    ("model", "field"),
    _required_cases(),
    ids=[f"{m.__name__}.{f}" for m, f in _required_cases()],
)
def test_missing_required_field_is_rejected(model: type[BaseModel], field: str) -> None:
    """R19: quitar un campo obligatorio de un ejemplo válido lanza ValidationError."""
    data = _example(model)
    _validate(model, data)
    if model is SearchResponse:
        del data[0][field]
    else:
        del data[field]
    with pytest.raises(ValidationError):
        _validate(model, data)


@pytest.mark.parametrize("model", OBJECT_MODELS, ids=lambda m: m.__name__)
def test_unexpected_field_is_rejected(model: type[BaseModel]) -> None:
    """R18: un campo no declarado lanza ValidationError."""
    data = _with(model, unexpected="x")
    with pytest.raises(ValidationError):
        _validate(model, data)


def test_unexpected_field_inside_search_response_element_is_rejected() -> None:
    """R18: un campo no declarado en un SearchResult dentro del arreglo lanza ValidationError."""
    data = _example(SearchResponse)
    data[0]["unexpected"] = "x"
    with pytest.raises(ValidationError):
        _validate(SearchResponse, data)


def test_every_model_has_a_required_field_case_except_check_timeouts_request() -> None:
    """R19: cada modelo con campos obligatorios aparece en los casos de rechazo."""
    with_cases = {model for model, _ in _required_cases()}
    assert set(BASE_EXAMPLES) - with_cases == {CheckTimeoutsRequest}


# ── Parte 2: tipos y límites comunes ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("model", "field"),
    [(MessageRequest, "received_at"), (LastMessage, "at")],
    ids=["MessageRequest.received_at", "LastMessage.at"],
)
def test_datetime_without_timezone_is_rejected(model: type[BaseModel], field: str) -> None:
    """R20: una fecha sin zona horaria lanza ValidationError."""
    _validate(model, _with(model, **{field: "2026-10-30T19:05:00+00:00"}))
    with pytest.raises(ValidationError):
        _validate(model, _with(model, **{field: "2026-10-30T19:05:00"}))


TEXT_MODELS = [MessageRequest, SendRequest, CaseReplyRequest, LastMessage]


@pytest.mark.parametrize("model", TEXT_MODELS, ids=lambda m: m.__name__)
@pytest.mark.parametrize("text", ["", "a" * (MAX_TEXT_LENGTH + 1)], ids=["empty", "too_long"])
def test_invalid_text_is_rejected(model: type[BaseModel], text: str) -> None:
    """R21: text vacío o de más de MAX_TEXT_LENGTH caracteres lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(model, _with(model, text=text))


@pytest.mark.parametrize("model", TEXT_MODELS, ids=lambda m: m.__name__)
def test_text_at_max_length_is_accepted(model: type[BaseModel]) -> None:
    """R21: text de exactamente MAX_TEXT_LENGTH caracteres es válido."""
    _validate(model, _with(model, text="a" * MAX_TEXT_LENGTH))


IDENTIFIER_FIELDS = [
    (HandoverRequest, "case_id"),
    (HandoverResponse, "case_id"),
    (CaseCloseResponse, "case_id"),
    (HandoverRequest, "contact_id"),
    (CaseReplyRequest, "advisor_id"),
    (CaseCloseRequest, "advisor_id"),
    (SearchResult, "chunk_id"),
    (ManualUploadResponse, "manual_id"),
    (CaseAssignRequest, "advisor_id"),
    (CaseAssignResponse, "case_id"),
    (CaseAuthorizeRequest, "advisor_id"),
    (CaseAuthorizeResponse, "case_id"),
    (CaseClientMessageResponse, "case_id"),
    (ChunkUpdateResponse, "chunk_id"),
    (ChunkUpdateResponse, "manual_id"),
]


@pytest.mark.parametrize(
    ("model", "field"),
    IDENTIFIER_FIELDS,
    ids=[f"{m.__name__}.{f}" for m, f in IDENTIFIER_FIELDS],
)
@pytest.mark.parametrize(
    "value", ["", "a" * (MAX_IDENTIFIER_LENGTH + 1)], ids=["empty", "too_long"]
)
def test_invalid_identifier_is_rejected(model: type[BaseModel], field: str, value: str) -> None:
    """R22: un identificador vacío o de más de MAX_IDENTIFIER_LENGTH lanza ValidationError."""
    _validate(model, _with(model, **{field: "a" * MAX_IDENTIFIER_LENGTH}))
    with pytest.raises(ValidationError):
        _validate(model, _with(model, **{field: value}))


@pytest.mark.parametrize(
    "value", ["", "a" * (MAX_IDENTIFIER_LENGTH + 1)], ids=["empty", "too_long"]
)
def test_invalid_timed_out_case_identifier_is_rejected(value: str) -> None:
    """R22: un elemento de timed_out_cases vacío o demasiado largo lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(CheckTimeoutsResponse, {"timed_out_cases": ["case-1", value]})


@pytest.mark.parametrize(
    "value", ["", "a" * (MAX_IDENTIFIER_LENGTH + 1)], ids=["empty", "too_long"]
)
def test_invalid_search_category_identifier_is_rejected(value: str) -> None:
    """R22: category de SearchRequest sigue las reglas de identificador (S7)."""
    with pytest.raises(ValidationError):
        _validate(SearchRequest, _with(SearchRequest, category=value))


# ── Parte 3: por modelo ──────────────────────────────────────────────────────


def test_message_request_requires_its_fields() -> None:
    """R23: MessageRequest exige update_id, telegram_user_id, chat_id, text y received_at."""
    assert {
        name for name, f in MessageRequest.model_fields.items() if f.is_required()
    } == {"update_id", "telegram_user_id", "chat_id", "text", "received_at"}
    message = _validate(MessageRequest, _example(MessageRequest))
    assert message.received_at.tzinfo is not None


def test_message_request_rejects_negative_update_id() -> None:
    """R23: update_id debe ser un entero >= 0."""
    _validate(MessageRequest, _with(MessageRequest, update_id=0))
    with pytest.raises(ValidationError):
        _validate(MessageRequest, _with(MessageRequest, update_id=-1))


@pytest.mark.parametrize("field", ["update_id", "telegram_user_id", "chat_id"])
def test_message_request_rejects_non_integer_ids(field: str) -> None:
    """R23: update_id, telegram_user_id y chat_id son enteros."""
    with pytest.raises(ValidationError):
        _validate(MessageRequest, _with(MessageRequest, **{field: "abc"}))


@pytest.mark.parametrize("status", ["accepted", "duplicate"])
def test_message_response_accepts_valid_status(status: str) -> None:
    """R24: status accepted y duplicate son válidos."""
    _validate(MessageResponse, {"status": status})


@pytest.mark.parametrize("status", ["ok", "ACCEPTED", ""])
def test_message_response_rejects_invalid_status(status: str) -> None:
    """R24: un status distinto de accepted o duplicate lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(MessageResponse, {"status": status})


def test_send_request_requires_chat_id_and_text() -> None:
    """R25: SendRequest exige chat_id (entero) y text."""
    assert {
        name for name, f in SendRequest.model_fields.items() if f.is_required()
    } == {"chat_id", "text"}
    with pytest.raises(ValidationError):
        _validate(SendRequest, _with(SendRequest, chat_id="abc"))


@pytest.mark.parametrize("model", [SendResponse, CaseReplyResponse], ids=lambda m: m.__name__)
def test_sent_must_be_true(model: type[BaseModel]) -> None:
    """R26: sent distinto de true lanza ValidationError."""
    _validate(model, {"sent": True})
    with pytest.raises(ValidationError):
        _validate(model, {"sent": False})


def test_search_request_requires_query_and_top_k() -> None:
    """R27: SearchRequest exige query (no vacío) y top_k (entero)."""
    assert {
        name for name, f in SearchRequest.model_fields.items() if f.is_required()
    } == {"query", "top_k"}
    with pytest.raises(ValidationError):
        _validate(SearchRequest, _with(SearchRequest, query=""))
    with pytest.raises(ValidationError):
        _validate(SearchRequest, _with(SearchRequest, top_k="muchos"))


@pytest.mark.parametrize("top_k", [0, MAX_TOP_K + 1])
def test_search_request_rejects_top_k_out_of_range(top_k: int) -> None:
    """R28: top_k menor que 1 o mayor que MAX_TOP_K lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(SearchRequest, _with(SearchRequest, top_k=top_k))


@pytest.mark.parametrize("top_k", [1, MAX_TOP_K])
def test_search_request_accepts_top_k_limits(top_k: int) -> None:
    """R28: top_k en los extremos 1 y MAX_TOP_K es válido."""
    _validate(SearchRequest, _with(SearchRequest, top_k=top_k))


def test_search_request_category_defaults_to_none() -> None:
    """R52: sin category, el modelo deja category = None."""
    data = _example(SearchRequest)
    assert "category" not in data
    assert _validate(SearchRequest, data).category is None


def test_search_response_accepts_empty_list() -> None:
    """R29: SearchResponse valida el arreglo vacío []."""
    assert SearchResponse.model_validate_json("[]").root == []


def test_search_response_accepts_results() -> None:
    """R29: SearchResponse valida un arreglo de SearchResult."""
    response = _validate(SearchResponse, _example(SearchResponse))
    assert all(isinstance(item, SearchResult) for item in response.root)
    assert set(SearchResult.model_fields) == {"chunk_id", "manual", "text", "score"}


def test_search_response_rejects_object_body() -> None:
    """R29: SearchResponse es un arreglo de nivel superior, no un objeto."""
    with pytest.raises(ValidationError):
        _validate(SearchResponse, {"results": _example(SearchResponse)})


@pytest.mark.parametrize("score", [-1.01, 1.01])
def test_search_result_rejects_score_out_of_range(score: float) -> None:
    """R30: score menor que -1 o mayor que 1 lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(SearchResult, _with(SearchResult, score=score))


@pytest.mark.parametrize("score", [-1.0, 1.0])
def test_search_result_accepts_score_limits(score: float) -> None:
    """R30: score en los extremos -1 y 1 es válido."""
    _validate(SearchResult, _with(SearchResult, score=score))


def test_handover_request_requires_its_fields() -> None:
    """R31: HandoverRequest exige case_id, contact_id, chat_id, reason y last_messages."""
    assert {
        name for name, f in HandoverRequest.model_fields.items() if f.is_required()
    } == {"case_id", "contact_id", "chat_id", "reason", "last_messages"}
    request = _validate(HandoverRequest, _example(HandoverRequest))
    assert all(isinstance(m, LastMessage) for m in request.last_messages)
    with pytest.raises(ValidationError):
        _validate(HandoverRequest, _with(HandoverRequest, chat_id="abc"))


@pytest.mark.parametrize("reason", ["no_relevant_chunks", "user_request", "invalid_answer"])
def test_handover_request_accepts_valid_reason(reason: str) -> None:
    """R32: los tres motivos documentados son válidos."""
    _validate(HandoverRequest, _with(HandoverRequest, reason=reason))


@pytest.mark.parametrize("reason", ["angry_user", ""])
def test_handover_request_rejects_invalid_reason(reason: str) -> None:
    """R32: un reason no documentado lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(HandoverRequest, _with(HandoverRequest, reason=reason))


def test_handover_request_rejects_too_many_last_messages() -> None:
    """R33: más de MAX_LAST_MESSAGES elementos lanza ValidationError; MAX_LAST_MESSAGES vale."""
    message = _example(LastMessage)
    _validate(HandoverRequest, _with(HandoverRequest, last_messages=[message] * MAX_LAST_MESSAGES))
    with pytest.raises(ValidationError):
        _validate(
            HandoverRequest,
            _with(HandoverRequest, last_messages=[message] * (MAX_LAST_MESSAGES + 1)),
        )


@pytest.mark.parametrize("role", ["user", "bot", "advisor"])
def test_last_message_accepts_valid_role(role: str) -> None:
    """R34: los roles user, bot y advisor son válidos."""
    _validate(LastMessage, _with(LastMessage, role=role))


@pytest.mark.parametrize("role", ["system", "assistant", ""])
def test_last_message_rejects_invalid_role(role: str) -> None:
    """R34: un role distinto de user, bot o advisor lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(LastMessage, _with(LastMessage, role=role))


@pytest.mark.parametrize("status", ["notified", "no_advisors"])
def test_handover_response_accepts_valid_status(status: str) -> None:
    """R35: HandoverResponse acepta status notified y no_advisors."""
    _validate(HandoverResponse, _with(HandoverResponse, status=status))


def test_handover_response_requires_status_and_case_id() -> None:
    """R35: HandoverResponse exige status (notified o no_advisors) y case_id."""
    assert {
        name for name, f in HandoverResponse.model_fields.items() if f.is_required()
    } == {"status", "case_id"}
    with pytest.raises(ValidationError):
        _validate(HandoverResponse, _with(HandoverResponse, status="pending"))


def test_case_reply_request_requires_advisor_id_and_text() -> None:
    """R36: CaseReplyRequest exige advisor_id y text."""
    assert {
        name for name, f in CaseReplyRequest.model_fields.items() if f.is_required()
    } == {"advisor_id", "text"}


@pytest.mark.parametrize(
    "name", ["", "a" * (MAX_MANUAL_NAME_LENGTH + 1)], ids=["empty", "too_long"]
)
def test_manual_upload_request_rejects_invalid_name(name: str) -> None:
    """R37: name vacío o de más de MAX_MANUAL_NAME_LENGTH lanza ValidationError."""
    _validate(ManualUploadRequest, {"name": "a" * MAX_MANUAL_NAME_LENGTH})
    with pytest.raises(ValidationError):
        _validate(ManualUploadRequest, {"name": name})


def test_manual_upload_response_rejects_zero_chunks() -> None:
    """R38: chunks menor que 1 lanza ValidationError."""
    _validate(ManualUploadResponse, _with(ManualUploadResponse, chunks=1))
    with pytest.raises(ValidationError):
        _validate(ManualUploadResponse, _with(ManualUploadResponse, chunks=0))


def test_case_close_request_requires_advisor_id() -> None:
    """R39: CaseCloseRequest exige advisor_id."""
    assert {
        name for name, f in CaseCloseRequest.model_fields.items() if f.is_required()
    } == {"advisor_id"}
    with pytest.raises(ValidationError):
        _validate(CaseCloseRequest, {})


@pytest.mark.parametrize("status", ["open", "timed_out", ""])
def test_case_close_response_rejects_invalid_status(status: str) -> None:
    """R40: un status distinto de closed lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(CaseCloseResponse, _with(CaseCloseResponse, status=status))


def test_case_assign_request_requires_advisor_id() -> None:
    """contrato_asignar_caso R15, R16: CaseAssignRequest exige solo advisor_id."""
    assert issubclass(CaseAssignRequest, ContractModel)
    assert {
        name for name, f in CaseAssignRequest.model_fields.items() if f.is_required()
    } == {"advisor_id"}
    with pytest.raises(ValidationError):
        _validate(CaseAssignRequest, {})


def test_case_assign_response_requires_status_and_case_id() -> None:
    """contrato_asignar_caso R18: CaseAssignResponse exige status (assigned) y case_id."""
    assert issubclass(CaseAssignResponse, ContractModel)
    assert {
        name for name, f in CaseAssignResponse.model_fields.items() if f.is_required()
    } == {"status", "case_id"}
    response = _validate(CaseAssignResponse, _example(CaseAssignResponse))
    assert response.status == "assigned"


@pytest.mark.parametrize("status", ["open", "timed_out", "closed", "ASSIGNED", ""])
def test_case_assign_response_rejects_invalid_status(status: str) -> None:
    """contrato_asignar_caso R19: un status distinto de assigned lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(CaseAssignResponse, _with(CaseAssignResponse, status=status))


def test_check_timeouts_request_accepts_empty_object() -> None:
    """R41: CheckTimeoutsRequest valida {}."""
    CheckTimeoutsRequest.model_validate_json("{}")


def test_check_timeouts_response_accepts_empty_list() -> None:
    """R42: timed_out_cases puede ser la lista vacía."""
    response = CheckTimeoutsResponse.model_validate_json('{"timed_out_cases": []}')
    assert response.timed_out_cases == []
    with pytest.raises(ValidationError):
        CheckTimeoutsResponse.model_validate_json("{}")


@pytest.mark.parametrize(
    "data",
    [
        {"error": "Not Found", "message": "No existe."},
        {"error": "not_found", "message": ""},
        {"error": "1error", "message": "x"},
    ],
    ids=["error_not_snake_case", "empty_message", "error_starts_with_digit"],
)
def test_error_response_rejects_invalid_values(data: dict[str, str]) -> None:
    """R43: error fuera de ^[a-z][a-z0-9_]*$ o message vacío lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(ErrorResponse, data)


@pytest.mark.parametrize(
    "data",
    [{"status": "down", "service": "rag"}, {"status": "ok", "service": ""}],
    ids=["status_down", "empty_service"],
)
def test_health_response_rejects_invalid_values(data: dict[str, str]) -> None:
    """R44: status distinto de ok o service vacío lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(HealthResponse, data)


# ── contrato_autorizacion_asesores (feature #13) ─────────────────────────────


def test_case_authorize_action_is_reply_or_close() -> None:
    """contrato_autorizacion_asesores R27: CaseAuthorizeAction es reply o close."""
    assert get_args(CaseAuthorizeAction) == ("reply", "close")


def test_case_authorize_request_requires_advisor_id_and_action() -> None:
    """contrato_autorizacion_asesores R28: CaseAuthorizeRequest exige advisor_id y action."""
    assert issubclass(CaseAuthorizeRequest, ContractModel)
    assert {
        name for name, f in CaseAuthorizeRequest.model_fields.items() if f.is_required()
    } == {"advisor_id", "action"}
    _validate(CaseAuthorizeRequest, _example(CaseAuthorizeRequest))


def test_case_authorize_request_without_advisor_id_is_rejected() -> None:
    """contrato_autorizacion_asesores R29: sin advisor_id lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(CaseAuthorizeRequest, {"action": "reply"})


def test_case_authorize_request_without_action_is_rejected() -> None:
    """contrato_autorizacion_asesores R30: sin action lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(CaseAuthorizeRequest, {"advisor_id": "222222222"})


@pytest.mark.parametrize("action", ["reply", "close"])
def test_case_authorize_request_accepts_valid_action(action: str) -> None:
    """contrato_autorizacion_asesores R28, R31: reply y close son válidas."""
    _validate(CaseAuthorizeRequest, _with(CaseAuthorizeRequest, action=action))


@pytest.mark.parametrize("action", ["assign", "REPLY", "read", ""])
def test_case_authorize_request_rejects_invalid_action(action: str) -> None:
    """contrato_autorizacion_asesores R31: una action fuera de la lista es rechazada."""
    with pytest.raises(ValidationError):
        _validate(CaseAuthorizeRequest, _with(CaseAuthorizeRequest, action=action))


def test_case_authorize_response_requires_allowed_and_case_id() -> None:
    """contrato_autorizacion_asesores R33: CaseAuthorizeResponse exige allowed y case_id."""
    assert issubclass(CaseAuthorizeResponse, ContractModel)
    assert {
        name for name, f in CaseAuthorizeResponse.model_fields.items() if f.is_required()
    } == {"allowed", "case_id"}
    response = _validate(CaseAuthorizeResponse, _example(CaseAuthorizeResponse))
    assert response.allowed is True


@pytest.mark.parametrize("allowed", [False, None, "false", 0])
def test_case_authorize_response_rejects_allowed_not_true(allowed: Any) -> None:
    """contrato_autorizacion_asesores R34: allowed distinto de true es rechazado."""
    with pytest.raises(ValidationError):
        _validate(CaseAuthorizeResponse, _with(CaseAuthorizeResponse, allowed=allowed))


# ── contrato_conversacion_caso (feature #15) ─────────────────────────────────


def test_case_client_message_request_requires_text_and_at() -> None:
    """contrato_conversacion_caso R19, R20: exige text y at; sin text lanza ValidationError."""
    assert issubclass(CaseClientMessageRequest, ContractModel)
    assert {
        name
        for name, field in CaseClientMessageRequest.model_fields.items()
        if field.is_required()
    } == {"text", "at"}
    with pytest.raises(ValidationError):
        _validate(CaseClientMessageRequest, {"at": "2026-10-30T19:20:00Z"})


def test_case_client_message_request_rejects_naive_at() -> None:
    """contrato_conversacion_caso R22: at sin zona horaria lanza ValidationError."""
    _validate(
        CaseClientMessageRequest,
        {"text": "hola", "at": "2026-10-30T19:20:00+00:00"},
    )
    with pytest.raises(ValidationError):
        _validate(CaseClientMessageRequest, {"text": "hola", "at": "2026-10-30T19:20:00"})


@pytest.mark.parametrize(
    "text", ["", "a" * (MAX_TEXT_LENGTH + 1)], ids=["empty", "too_long"]
)
def test_case_client_message_request_rejects_invalid_text(text: str) -> None:
    """contrato_conversacion_caso R23: text vacío o demasiado largo lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(
            CaseClientMessageRequest,
            {"text": text, "at": "2026-10-30T19:20:00Z"},
        )


def test_case_client_message_request_accepts_text_at_max_length() -> None:
    """contrato_conversacion_caso R23: text de MAX_TEXT_LENGTH caracteres es válido."""
    _validate(
        CaseClientMessageRequest,
        {"text": "a" * MAX_TEXT_LENGTH, "at": "2026-10-30T19:20:00Z"},
    )


def test_case_client_message_response_requires_status_and_case_id() -> None:
    """contrato_conversacion_caso R24: exige exactamente status y case_id."""
    assert issubclass(CaseClientMessageResponse, ContractModel)
    assert {
        name
        for name, field in CaseClientMessageResponse.model_fields.items()
        if field.is_required()
    } == {"status", "case_id"}


@pytest.mark.parametrize("status", ["forwarded", "not_assigned"])
def test_case_client_message_response_accepts_valid_status(status: str) -> None:
    """contrato_conversacion_caso R24: forwarded y not_assigned son válidos."""
    _validate(
        CaseClientMessageResponse,
        {"status": status, "case_id": "case-1"},
    )


@pytest.mark.parametrize(
    "status", ["assigned", "open", "closed", "FORWARDED", "sent", ""]
)
def test_case_client_message_response_rejects_invalid_status(status: str) -> None:
    """contrato_conversacion_caso R25: un status fuera de la lista lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(
            CaseClientMessageResponse,
            {"status": status, "case_id": "case-1"},
        )


# ── edicion_fragmentos (feature #19) ─────────────────────────────────────────


def test_chunk_update_request_requires_only_text() -> None:
    """edicion_fragmentos R1: ChunkUpdateRequest exige únicamente text."""
    assert issubclass(ChunkUpdateRequest, ContractModel)
    assert {
        name for name, field in ChunkUpdateRequest.model_fields.items() if field.is_required()
    } == {"text"}
    _validate(ChunkUpdateRequest, {"text": "texto nuevo"})


@pytest.mark.parametrize("text", ["", "   ", "\n\t "], ids=["empty", "spaces", "whitespace"])
def test_chunk_update_request_rejects_blank_text(text: str) -> None:
    """edicion_fragmentos R2: texto vacío o solo espacios lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(ChunkUpdateRequest, {"text": text})


def test_chunk_update_request_preserves_text_exactly() -> None:
    """edicion_fragmentos R3: el texto no vacío se conserva sin normalizar."""
    text = "  Texto con espacios  "
    request = _validate(ChunkUpdateRequest, {"text": text})
    assert request.text == text


def test_chunk_update_response_has_fragment_metadata_fields() -> None:
    """edicion_fragmentos R8: la respuesta devuelve los datos actualizados del fragmento."""
    assert issubclass(ChunkUpdateResponse, ContractModel)
    assert set(ChunkUpdateResponse.model_fields) == {
        "chunk_id",
        "manual_id",
        "manual",
        "order",
        "text",
        "active",
    }
    response = _validate(ChunkUpdateResponse, _example(ChunkUpdateResponse))
    assert response.active is True
    assert response.order == 1


def test_chunk_update_response_rejects_invalid_order() -> None:
    """edicion_fragmentos R8: order menor que 1 lanza ValidationError."""
    with pytest.raises(ValidationError):
        _validate(ChunkUpdateResponse, _with(ChunkUpdateResponse, order=0))

