"""Tests del traspaso automático tras fallos consecutivos (#32)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from lazaro_contracts import HandoverRequest, HandoverResponse, MessageRequest, SearchResult
from pydantic import ValidationError

from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.repository import FakeRepository, PostgresRepository
from orchestrator.config import Settings
from orchestrator.domain import ServiceUnavailable, process_message

ACK = "Avisé a un asesor; te responderá por aquí en cuanto pueda."
ROOT = Path(__file__).resolve().parents[3]
REASONS = {"no_relevant_chunks", "invalid_answer"}


def _chunks() -> list[SearchResult]:
    return [SearchResult(chunk_id="c1", manual="M", text="dato 42", score=0.9)]


def _valid_reply() -> str:
    return json.dumps(
        {"answer": "dato 42", "citations": [{"chunk_id": "c1", "quote": "dato 42"}]}
    )


def _fail(env, update_id: int, user: int = 10, chat: int = 100):
    env.rag.results = []
    return env.post(update_id=update_id, user=user, chat=chat)


def _contact(env, telegram_user_id: int = 10):
    return env.repo.contacts[telegram_user_id]


def _sent_texts(env) -> list[str]:
    return [text for _, text in env.gateway.sent]


# --- R3, R13: configuración ---------------------------------------------------------------


def test_threshold_and_reasons_defaults(monkeypatch):
    """R3: umbral 3 y allowlist completa por defecto."""
    monkeypatch.delenv("AUTO_HANDOVER_FAILURE_THRESHOLD", raising=False)
    monkeypatch.delenv("AUTO_HANDOVER_FAILURE_REASONS", raising=False)
    settings = Settings()
    assert settings.auto_handover_failure_threshold == 3
    assert settings.auto_handover_failure_reason_set == REASONS
    assert settings.effective_auto_handover_failure_reasons == REASONS


def test_env_example_documents_auto_handover_defaults():
    """R3: las variables nuevas quedan en .env.example con sus defaults."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "AUTO_HANDOVER_FAILURE_THRESHOLD=3" in text
    assert "AUTO_HANDOVER_FAILURE_REASONS=no_relevant_chunks,invalid_answer" in text


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_threshold_prevents_start(value):
    """R13: un umbral menor que 1 impide iniciar y señala la variable."""
    with pytest.raises(ValidationError) as exc:
        Settings(auto_handover_failure_threshold=value)
    assert "auto_handover_failure_threshold" in str(exc.value)


@pytest.mark.parametrize("value", ["no_relevant_chunks,otro", "desconocido"])
def test_invalid_reasons_prevent_start_and_name_the_variable(value):
    """R13: un motivo fuera de la allowlist impide iniciar y señala la variable."""
    with pytest.raises(ValidationError) as exc:
        Settings(auto_handover_failure_reasons=value)
    assert "AUTO_HANDOVER_FAILURE_REASONS" in str(exc.value)


def test_invalid_answer_is_excluded_when_its_handover_is_disabled():
    """R3: INVALID_ANSWER_HANDOVER=false excluye invalid_answer del conteo."""
    settings = Settings(
        invalid_answer_handover=False,
        auto_handover_failure_reasons="no_relevant_chunks,invalid_answer",
    )
    assert settings.auto_handover_failure_reason_set == REASONS
    assert settings.effective_auto_handover_failure_reasons == {"no_relevant_chunks"}


# --- R1, R7, R9: umbral y aviso ------------------------------------------------------------


def test_failures_below_threshold_do_not_hand_over(env):
    """R1, R7, R9: la racha suma, pero solo el fallo que cruza el umbral deriva y avisa."""
    env.settings.auto_handover_failure_threshold = 3
    _fail(env, 1)
    _fail(env, 2)
    assert env.handover.requests == []
    assert all(event_type != "handover" for event_type, _ in env.events())
    assert ACK not in _sent_texts(env)

    _fail(env, 3)
    assert [request.reason for request in env.handover.requests] == [
        "no_relevant_chunks"
    ]
    assert ("handover", "no_relevant_chunks") in env.events()
    assert _sent_texts(env).count(ACK) == 1
    assert env.repo.rag_streaks[_contact(env).id].state == "handed_over"


def test_extra_failures_after_notified_do_not_derive_again(env):
    """R8, R9: una derivación completada no se repite ni reenvía el ACK."""
    env.settings.auto_handover_failure_threshold = 1
    _fail(env, 1)
    _fail(env, 2)
    _fail(env, 3)
    assert len(env.handover.requests) == 1
    assert _sent_texts(env).count(ACK) == 1


def test_no_advisors_sends_fixed_reply_and_closes_streak(env):
    """R10, R8: sin asesores se envía NO_ADVISORS_REPLY y no se reintenta."""
    env.settings.auto_handover_failure_threshold = 1
    env.handover.status = "no_advisors"
    _fail(env, 1)
    reply = env.settings.no_advisors_reply
    assert len(env.handover.requests) == 1
    assert reply in _sent_texts(env)
    assert ("handover_failed", "no_advisors") in env.events()
    assert ACK not in _sent_texts(env)

    _fail(env, 2)
    assert len(env.handover.requests) == 1
    assert _sent_texts(env).count(reply) == 1


# --- R6, R4: respuesta válida y aislamiento ------------------------------------------------


def test_valid_answer_resets_the_streak(env):
    """R6: una respuesta válida pone el contador a cero."""
    env.settings.auto_handover_failure_threshold = 2
    _fail(env, 1)
    env.rag.results = _chunks()
    env.llm.reply = _valid_reply()
    env.post(update_id=2)
    assert env.handover.requests == []
    assert env.repo.rag_streaks[_contact(env).id].failure_count == 0

    _fail(env, 3)
    assert env.handover.requests == []
    _fail(env, 4)
    assert len(env.handover.requests) == 1


def test_valid_answer_after_handover_opens_a_new_streak(env):
    """R6, R8; #37 R13: el asesor devuelve el caso y una respuesta válida abre racha."""
    from orchestrator.domain import ConversationEvent, apply_conversation_event

    env.settings.auto_handover_failure_threshold = 1
    _fail(env, 1)
    assert len(env.handover.requests) == 1
    apply_conversation_event(
        _contact(env).id, ConversationEvent.ADVISOR_RESOLVED, env.adapters
    )
    env.rag.results = _chunks()
    env.llm.reply = _valid_reply()
    env.post(update_id=2)
    _fail(env, 3)
    assert len(env.handover.requests) == 2


def test_streak_is_isolated_by_contact(env):
    """R4: cada conversación mantiene su propia racha."""
    env.settings.auto_handover_failure_threshold = 2
    _fail(env, 1, user=10, chat=100)
    _fail(env, 2, user=10, chat=100)
    _fail(env, 3, user=20, chat=200)
    assert len(env.handover.requests) == 1

    _fail(env, 4, user=20, chat=200)
    assert len(env.handover.requests) == 2
    assert env.handover.requests[0].contact_id == env.repo.contacts[10].id
    assert env.handover.requests[1].contact_id == env.repo.contacts[20].id


# --- R5, R11, R14: idempotencia, reintento y caso reutilizado ------------------------------


def test_repeated_update_id_does_not_increment_the_streak():
    """R5: el mismo update_id solo se registra una vez."""
    repo = FakeRepository()
    assert (
        repo.record_rag_outcome("c1", 7, "no_relevant_chunks", 2, {"no_relevant_chunks"})
        is False
    )
    assert (
        repo.record_rag_outcome("c1", 7, "no_relevant_chunks", 2, {"no_relevant_chunks"})
        is False
    )
    assert repo.rag_streaks["c1"].failure_count == 1


def test_pending_retry_uses_the_next_eligible_outcome_even_if_not_counted():
    """R11: una derivación pendiente se reintenta sin sumar un motivo excluido."""
    repo = FakeRepository()
    reasons = {"no_relevant_chunks"}
    assert repo.record_rag_outcome("c1", 1, "no_relevant_chunks", 1, reasons) is True
    repo.finish_auto_handover("c1", False)
    assert repo.rag_streaks["c1"].state == "retry"
    assert repo.record_rag_outcome("c1", 2, "invalid_answer", 1, reasons) is True
    assert repo.rag_streaks["c1"].failure_count == 1


def test_transient_handover_failure_is_retried_on_the_next_failure(env):
    """R11, R8, R9: si handover cae, se reintenta y no se duplica el aviso."""
    env.settings.auto_handover_failure_threshold = 2
    env.handover.fail = True
    _fail(env, 1)
    _fail(env, 2)
    assert len(env.handover.requests) == 1
    assert env.repo.rag_streaks[_contact(env).id].state == "retry"

    env.handover.fail = False
    _fail(env, 3)
    assert len(env.handover.requests) == 2
    assert env.repo.rag_streaks[_contact(env).id].state == "handed_over"
    assert _sent_texts(env).count(ACK) == 1

    _fail(env, 4)
    assert len(env.handover.requests) == 2


class _ReusingHandover(FakeHandoverClient):
    """Simula la reutilización de un caso activo que hace handover."""

    def request(self, req: HandoverRequest) -> HandoverResponse:  # type: ignore[override]
        self.requests.append(req)
        if self.fail:
            raise ServiceUnavailable("Handover caído")
        return HandoverResponse(status=self.status, case_id="case-reused")


def test_retry_reuses_the_active_case(env):
    """R14: el reintento vuelve a pedir el traspaso y enlaza el caso reutilizado."""
    env.settings.auto_handover_failure_threshold = 2
    reusing = _ReusingHandover()
    env.adapters.handover = reusing
    reusing.fail = True
    _fail(env, 1)
    _fail(env, 2)
    assert len(reusing.requests) == 1

    reusing.fail = False
    _fail(env, 3)
    assert len(reusing.requests) == 2
    assert reusing.requests[0].contact_id == reusing.requests[1].contact_id
    assert env.repo.get_case_contact("case-reused") == _contact(env)
    assert list(env.repo.case_links) == ["case-reused"]


# --- R1, R2, R3: motivos excluidos y errores ------------------------------------------------


def test_no_relevant_chunks_is_not_counted_when_outside_the_policy(env):
    """R1: solo se cuentan los motivos habilitados en la allowlist."""
    env.settings.auto_handover_failure_threshold = 1
    env.settings.auto_handover_failure_reasons = "invalid_answer"
    _fail(env, 1)
    assert env.handover.requests == []
    assert env.repo.rag_streaks == {}


def test_invalid_answer_is_not_counted_when_handover_is_disabled(env):
    """R2, R3: con INVALID_ANSWER_HANDOVER=false no cuenta ni deriva."""
    env.settings.auto_handover_failure_threshold = 1
    env.settings.invalid_answer_handover = False
    env.llm.reply = "no json"
    env.post(update_id=1)
    assert env.handover.requests == []
    assert env.repo.rag_streaks == {}


def test_invalid_answer_counts_when_enabled(env):
    """R1, R3, R7: invalid_answer cuenta cuando la opción existente está activa."""
    env.settings.auto_handover_failure_threshold = 1
    env.llm.reply = "no json"
    env.post(update_id=1)
    assert [request.reason for request in env.handover.requests] == ["invalid_answer"]
    assert ("invalid_answer", "invalid_json") in env.events()
    assert _sent_texts(env).count(ACK) == 1


def test_rag_and_llm_errors_do_not_count_or_break_the_streak(env):
    """R2: los errores de infraestructura no son fallos de respuesta."""
    env.settings.auto_handover_failure_threshold = 2
    _fail(env, 1)
    env.rag.fail = True
    env.post(update_id=2)
    env.rag.fail = False
    env.rag.results = _chunks()
    env.llm.fail = True
    env.post(update_id=3)
    assert env.handover.requests == []
    assert env.repo.rag_streaks[_contact(env).id].failure_count == 1

    env.llm.fail = False
    _fail(env, 4)
    assert len(env.handover.requests) == 1


def test_commands_privacy_and_user_request_are_not_counted(env):
    """R2: comandos, aviso de privacidad y petición explícita no crean racha."""
    env.settings.auto_handover_failure_threshold = 3
    env.post(text="/responder case-1 hola", update_id=1)
    assert env.repo.rag_streaks == {}
    env.post(text="hola", update_id=2, user=30, chat=300, consent=False)
    assert env.repo.rag_streaks == {}

    _fail(env, 3)
    contact = _contact(env)
    assert env.repo.rag_streaks[contact.id].failure_count == 1
    env.post(text="quiero un asesor", update_id=4)
    assert env.repo.rag_streaks[contact.id].failure_count == 0


def test_forwarded_assigned_conversation_is_not_counted(env):
    """R2: el reenvío al asesor no pasa por RAG ni crea una racha de fallos."""
    env.settings.auto_handover_failure_threshold = 1
    contact = env.repo.get_or_create_contact(10, 100, env.adapters.clock())
    env.repo.link_case("case-1", contact.id, env.adapters.clock())
    env.handover.client_message_status = "forwarded"
    env.post(text="hola asesor", update_id=1)
    assert env.rag.calls == []
    assert env.repo.rag_streaks == {}


# --- R4, R5, R11: persistencia Postgres -----------------------------------------------------


class _LoggingCursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self._rows: list = []

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))
        self._rows = [(1,)] if "RETURNING update_id" in sql else []

    def fetchall(self):
        return self._rows


class _LoggingConn:
    def __init__(self) -> None:
        self.log: list = []

    def cursor(self):
        return _LoggingCursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_rag_outcomes_use_parameterized_sql():
    """R4, R5: la persistencia nueva usa tablas propias y SQL parametrizado."""
    conn = _LoggingConn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    contact_id = "'; DROP TABLE auto_handover_streaks; --"
    repo.record_rag_outcome(
        contact_id, 7, "no_relevant_chunks", 3, {"no_relevant_chunks"}
    )
    repo.finish_auto_handover(contact_id, False)
    repo.reset_rag_streak(contact_id)

    assert any(
        "CREATE TABLE IF NOT EXISTS auto_handover_outcomes" in sql
        for sql, _ in conn.log
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS auto_handover_streaks" in sql
        for sql, _ in conn.log
    )
    for sql, params in conn.log:
        if sql.startswith("CREATE"):
            continue
        assert contact_id not in sql and "'" not in sql
        assert sql.count("%s") == len(params)


class _MemoryCursor:
    def __init__(self, state: dict) -> None:
        self.state = state
        self._rows: list = []

    def execute(self, sql, params=()):
        if sql.startswith("CREATE"):
            self._rows = []
            return
        if "INSERT INTO auto_handover_outcomes" in sql:
            contact_id, update_id, outcome = params
            key = (contact_id, update_id)
            if key in self.state["outcomes"]:
                self._rows = []
            else:
                self.state["outcomes"].add(key)
                self._rows = [(update_id,)]
            return
        if "SELECT failure_count, state FROM auto_handover_streaks" in sql:
            contact_id = params[0]
            row = self.state["streaks"].get(contact_id)
            self._rows = [row] if row is not None else []
            return
        if "INSERT INTO auto_handover_streaks" in sql:
            contact_id, failure_count, state = params
            self.state["streaks"][contact_id] = (failure_count, state)
            self._rows = []
            return
        if "UPDATE auto_handover_streaks SET state" in sql:
            state, contact_id = params
            current = self.state["streaks"].get(contact_id)
            if current is not None:
                self.state["streaks"][contact_id] = (current[0], state)
            self._rows = []
            return
        self._rows = []

    def fetchall(self):
        return self._rows


class _MemoryConn:
    def __init__(self) -> None:
        self.state = {"outcomes": set(), "streaks": {}}

    def cursor(self):
        return _MemoryCursor(self.state)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_streak_survives_a_restart_and_retry_is_persisted():
    """R4, R5, R11: una instancia nueva del repositorio conserva racha y reintento."""
    conn = _MemoryConn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    reasons = {"no_relevant_chunks"}
    assert repo.record_rag_outcome("c1", 1, "no_relevant_chunks", 2, reasons) is False
    assert repo.record_rag_outcome("c1", 2, "no_relevant_chunks", 2, reasons) is True

    restarted = PostgresRepository("postgresql://x", connect=lambda: conn)
    assert (
        restarted.record_rag_outcome("c1", 3, "no_relevant_chunks", 2, reasons)
        is False
    )
    restarted.finish_auto_handover("c1", False)
    assert (
        restarted.record_rag_outcome("c1", 4, "no_relevant_chunks", 2, reasons)
        is True
    )


# --- #34: recuperación ante una excepción de _handover --------------------------------------


class _ExplodingHandover(FakeHandoverClient):
    """Handover que falla con una excepción no prevista por `_handover`."""

    def request(self, req: HandoverRequest) -> HandoverResponse:  # type: ignore[override]
        self.requests.append(req)
        raise RuntimeError("fallo inesperado de handover")


def test_unexpected_handover_exception_leaves_the_streak_in_retry(env):
    """R4: una excepción de `_handover` deja la racha reintentable y se propaga."""
    env.settings.auto_handover_failure_threshold = 1
    env.rag.results = []
    env.adapters.handover = _ExplodingHandover()
    env.repo.add_privacy_consent(
        10,
        env.settings.privacy_notice_version,
        "sha",
        env.adapters.clock(),
    )
    request = MessageRequest(
        update_id=1,
        telegram_user_id=10,
        chat_id=100,
        text="¿Cómo instalo el módulo?",
        received_at=env.adapters.clock(),
    )

    with pytest.raises(RuntimeError):
        process_message(request, env.settings, env.adapters)

    contact = _contact(env)
    assert env.repo.rag_streaks[contact.id].state == "retry"
