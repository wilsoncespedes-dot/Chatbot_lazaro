"""Consentimiento antes de cualquier dato salvo personal vinculado (#35)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.accounts import hash_token, new_link_token
from orchestrator.adapters.repository import FakeRepository
from orchestrator.privacy import PRIVACY_ACCEPT_BUTTON

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
USER_ID = 10
CHAT_ID = 100

ROUTES = (
    "free_text",
    "db_query",
    "db_query_malformed",
    "reply",
    "close",
    "reply_malformed",
    "start_client",
)

TEXTS = {
    "free_text": "¿Cómo instalo el módulo?",
    "db_query": "/consultar cuántos pedidos hay",
    "db_query_malformed": "/consultar",
    "reply": "/responder case-1 hola",
    "close": "/cerrar case-1",
    "reply_malformed": "/responder",
}

WRITE_METHODS = frozenset(
    {
        "get_or_create_contact",
        "add_message",
        "add_event",
        "link_case",
        "record_rag_outcome",
        "reset_rag_streak",
        "finish_auto_handover",
        "consume_link_token",
        "add_db_query_audit",
        "add_privacy_consent",
        "add_link_token",
    }
)


def _linked_rows(repo: FakeRepository, uid: int) -> dict[str, list]:
    """Filas del glosario ligadas al remitente; no incluye datos de setup sin vínculo."""
    contact_ids = {
        contact.id for contact in repo.contacts.values()
        if contact.telegram_user_id == uid
    }
    return {
        "contacts": [
            contact for contact in repo.contacts.values()
            if contact.telegram_user_id == uid
        ],
        "contact_created_at": [
            at for contact_id, at in repo.contact_created_at.items()
            if contact_id in contact_ids
        ],
        "messages": [
            message for message in repo.messages if message.contact_id in contact_ids
        ],
        "events": [
            event for event in repo.events if event.contact_id in contact_ids
        ],
        "case_links": [
            (case_id, contact_id)
            for case_id, contact_id in repo.case_links.items()
            if contact_id in contact_ids
        ],
        "case_link_created_at": [
            at for case_id, at in repo.case_link_created_at.items()
            if repo.case_links.get(case_id) in contact_ids
        ],
        "rag_streaks": [
            (contact_id, streak)
            for contact_id, streak in repo.rag_streaks.items()
            if contact_id in contact_ids
        ],
        "rag_outcomes": [
            key for key in repo.rag_outcomes if key[0] in contact_ids
        ],
        "rag_outcome_at": [
            (key, at) for key, at in repo.rag_outcome_at.items()
            if key[0] in contact_ids
        ],
        "db_query_audits": [
            audit for audit in repo.db_query_audits
            if audit.telegram_user_id == uid
        ],
        "profiles": [
            profile for profile in repo.profiles.values()
            if profile.telegram_user_id == uid
        ],
        "used_link_tokens": [
            token for token in repo.link_tokens.values()
            if token.used_at is not None
        ],
    }


def _assert_no_personal_data(env, uid: int) -> None:
    rows = _linked_rows(env.repo, uid)
    assert all(not value for value in rows.values()), rows
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.db_query_audits == []
    assert env.repo.privacy_consents == []


def _text_for(env, route: str) -> str:
    if route != "start_client":
        return TEXTS[route]
    profile = env.repo.create_profile("cliente1", "cliente", "hash", FIXED_NOW)
    token = new_link_token()
    env.repo.add_link_token(
        hash_token(token), profile.id, FIXED_NOW + timedelta(minutes=15)
    )
    return f"/start {token}"


def _link_staff(env, uid: int, role: str = "asesor"):
    profile = env.repo.create_profile(f"{role}{uid}", role, "hash", FIXED_NOW)
    env.repo.profiles[profile.id].telegram_user_id = uid
    return profile


@pytest.mark.parametrize("route", ROUTES)
def test_unconsented_sender_leaves_no_personal_data(env, route):
    """R10, R11, R15, R16, R18: toda ruta de no personal deja solo el aviso."""
    text = _text_for(env, route)
    response = env.post(
        text=text, update_id=1, user=USER_ID, chat=CHAT_ID, consent=False
    )

    assert response.status_code == 202
    assert len(env.gateway.sent) == 1
    assert env.gateway.sent[0][0] == CHAT_ID
    assert env.settings.privacy_notice_text in env.gateway.sent[0][1]
    _assert_no_personal_data(env, USER_ID)
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.handover.requests == []
    assert env.handover.authorized == []
    assert env.handover.closed == []
    assert env.db_query.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_unconsented_sender_only_stores_update_id(env, route):
    """R20: por HTTP solo queda el update_id en processed_updates."""
    text = _text_for(env, route)
    env.post(text=text, update_id=1, user=USER_ID, chat=CHAT_ID, consent=False)

    assert env.repo.processed == {1}
    assert env.repo.processed_messages == set()
    _assert_no_personal_data(env, USER_ID)


@pytest.mark.parametrize("route", ROUTES)
def test_acceptance_after_any_route_only_adds_privacy_consent(env, route):
    """R19: la aceptación posterior deja como única fila nueva el consentimiento."""
    text = _text_for(env, route)
    env.post(text=text, update_id=1, user=USER_ID, chat=CHAT_ID, consent=False)
    assert all(not value for value in _linked_rows(env.repo, USER_ID).values())

    response = env.post_button(
        PRIVACY_ACCEPT_BUTTON, user=USER_ID, chat=CHAT_ID, message_id="btn-1"
    )

    assert response.status_code == 202
    assert len(env.repo.privacy_consents) == 1
    consent = env.repo.privacy_consents[0]
    assert consent.telegram_user_id == USER_ID
    assert env.gateway.sent[-1] == (CHAT_ID, env.settings.privacy_accepted_reply)


class RecordingRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def get_profile_by_telegram_user_id(self, telegram_user_id):
        self.calls.append("get_profile_by_telegram_user_id")
        return super().get_profile_by_telegram_user_id(telegram_user_id)

    def get_link_token_role(self, token_hash, now):
        self.calls.append("get_link_token_role")
        return super().get_link_token_role(token_hash, now)

    def get_or_create_contact(self, telegram_user_id, chat_id, now):
        self.calls.append("get_or_create_contact")
        return super().get_or_create_contact(telegram_user_id, chat_id, now)

    def add_message(self, contact_id, role, text, at):
        self.calls.append("add_message")
        return super().add_message(contact_id, role, text, at)

    def add_event(self, contact_id, type, reason, at):
        self.calls.append("add_event")
        return super().add_event(contact_id, type, reason, at)

    def link_case(self, case_id, contact_id, at, profile_id=None):
        self.calls.append("link_case")
        return super().link_case(case_id, contact_id, at, profile_id=profile_id)

    def record_rag_outcome(self, contact_id, update_id, outcome, threshold, failure_reasons):
        self.calls.append("record_rag_outcome")
        return super().record_rag_outcome(
            contact_id, update_id, outcome, threshold, failure_reasons
        )

    def reset_rag_streak(self, contact_id):
        self.calls.append("reset_rag_streak")
        return super().reset_rag_streak(contact_id)

    def finish_auto_handover(self, contact_id, success):
        self.calls.append("finish_auto_handover")
        return super().finish_auto_handover(contact_id, success)

    def consume_link_token(self, token_hash, telegram_user_id, now):
        self.calls.append("consume_link_token")
        return super().consume_link_token(token_hash, telegram_user_id, now)

    def add_db_query_audit(
        self, profile_id, telegram_user_id, status, views, row_count, sql_sha256, at
    ):
        self.calls.append("add_db_query_audit")
        return super().add_db_query_audit(
            profile_id, telegram_user_id, status, views, row_count, sql_sha256, at
        )

    def add_privacy_consent(
        self, telegram_user_id, notice_version, notice_sha256, accepted_at
    ):
        self.calls.append("add_privacy_consent")
        return super().add_privacy_consent(
            telegram_user_id, notice_version, notice_sha256, accepted_at
        )

    def add_link_token(self, token_hash, profile_id, expires_at):
        self.calls.append("add_link_token")
        return super().add_link_token(token_hash, profile_id, expires_at)


def _first_write(calls: list[str]) -> int | None:
    for index, name in enumerate(calls):
        if name in WRITE_METHODS:
            return index
    return None


@pytest.mark.parametrize("route", ("consultar", "responder", "start"))
def test_staff_reads_happen_before_any_write(env_factory, route):
    """R1, R3: el perfil (y el rol del token) se leen antes de toda escritura."""
    env = env_factory()
    repo = RecordingRepository()
    env.repo = repo
    env.adapters.repository = repo

    if route == "start":
        profile = repo.create_profile("asesor1", "asesor", "hash", FIXED_NOW)
        token = new_link_token()
        repo.add_link_token(
            hash_token(token), profile.id, FIXED_NOW + timedelta(minutes=15)
        )
        text = f"/start {token}"
    else:
        _link_staff(env, 111, "asesor")
        text = (
            "/consultar cuántos pedidos hay"
            if route == "consultar"
            else "/responder case-1 hola"
        )
    repo.calls.clear()

    env.post(text=text, update_id=1, user=111, chat=111, consent=False)

    first_write = _first_write(repo.calls)
    assert first_write is not None, repo.calls
    assert repo.calls.index("get_profile_by_telegram_user_id") < first_write
    if route == "start":
        assert repo.calls.index("get_link_token_role") < first_write


def test_non_positive_sender_is_never_staff(env_factory):
    """R2: un remitente con id <= 0 recibe el aviso sin consultar perfiles."""
    env = env_factory()
    texts = env.repo.get_conversation_texts()
    repo = RecordingRepository()
    repo.save_conversation_texts(texts, "test-seed", FIXED_NOW)
    env.repo = repo
    env.adapters.repository = repo
    profile = repo.create_profile("asesor0", "asesor", "hash", FIXED_NOW)
    repo.profiles[profile.id].telegram_user_id = 0
    repo.calls.clear()

    response = env.post(
        text="/consultar cuántos pedidos hay",
        update_id=1,
        user=0,
        chat=0,
        consent=False,
    )

    assert response.status_code == 202
    assert "get_profile_by_telegram_user_id" not in repo.calls
    assert len(env.gateway.sent) == 1
    assert env.gateway.sent[0][0] == 0
    assert env.settings.privacy_notice_text in env.gateway.sent[0][1]
    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.db_query_audits == []


STAFF_COMMANDS = (
    ("db_query", "/consultar cuántos pedidos hay"),
    ("reply", "/responder case-1 hola"),
    ("close", "/cerrar case-1"),
    ("malformed", "/responder"),
)


def _empty_privacy() -> dict[str, str]:
    return {
        "privacy_notice_text": "",
        "privacy_notice_version": "",
        "privacy_accept_phrase": "",
        "privacy_accepted_reply": "",
        "privacy_retention_days": "",
    }


@pytest.mark.parametrize("role", ("asesor", "admin"))
@pytest.mark.parametrize(("name", "text"), STAFF_COMMANDS)
@pytest.mark.parametrize("without_privacy_config", (False, True))
def test_linked_staff_commands_skip_privacy_gate(
    env_factory, role, name, text, without_privacy_config
):
    """R6, R7: el personal vinculado opera como antes, sin aviso ni consentimiento."""
    overrides = _empty_privacy() if without_privacy_config else {}
    env = env_factory(**overrides)
    _link_staff(env, 111, role)

    response = env.post(text=text, update_id=1, user=111, chat=111, consent=False)

    assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert all(
        sent_text != env.settings.privacy_notice_text
        for _, sent_text in env.gateway.sent
    )
    if name == "db_query":
        assert len(env.repo.db_query_audits) == 1
    elif name in ("reply", "close"):
        assert len(env.handover.authorized) == 1
    else:
        assert env.gateway.sent[-1] == (111, env.settings.advisor_command_help)


@pytest.mark.parametrize("role", ("asesor", "admin"))
def test_start_with_staff_token_links_without_consent(env, role):
    """R8: un token de personal vincula sin consentimiento y sin aviso."""
    profile = env.repo.create_profile("staff1", role, "hash", FIXED_NOW)
    token = new_link_token()
    env.repo.add_link_token(
        hash_token(token), profile.id, FIXED_NOW + timedelta(minutes=15)
    )

    response = env.post(
        text=f"/start {token}",
        update_id=1,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )

    assert response.status_code == 202
    assert env.repo.profiles[profile.id].telegram_user_id == USER_ID
    assert env.repo.link_tokens[hash_token(token)].used_at == FIXED_NOW
    assert env.gateway.sent == [(CHAT_ID, env.settings.link_success_reply)]
    assert env.repo.privacy_consents == []


def test_linked_staff_start_skips_gate(env):
    """R9: el personal vinculado recibe link_failed_reply sin pasar por la puerta."""
    _link_staff(env, 111, "asesor")

    env.post(
        text="/start token-invalido", update_id=1, user=111, chat=111, consent=False
    )

    assert env.gateway.sent == [(111, env.settings.link_failed_reply)]
    assert env.repo.privacy_consents == []


def test_client_token_survives_until_acceptance(env):
    """R15, R16, R17: sin consentimiento no se consume; tras aceptar sí vincula."""
    profile = env.repo.create_profile("cliente1", "cliente", "hash", FIXED_NOW)
    token = new_link_token()
    token_hash = hash_token(token)
    env.repo.add_link_token(
        token_hash, profile.id, FIXED_NOW + timedelta(minutes=15)
    )

    env.post(
        text=f"/start {token}",
        update_id=1,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )
    assert len(env.gateway.sent) == 1
    assert env.settings.privacy_notice_text in env.gateway.sent[0][1]
    assert env.repo.link_tokens[token_hash].used_at is None
    assert env.repo.profiles[profile.id].telegram_user_id is None

    env.post_button(
        PRIVACY_ACCEPT_BUTTON, user=USER_ID, chat=CHAT_ID, message_id="btn-1"
    )
    env.post(
        text=f"/start {token}",
        update_id=3,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )

    assert env.repo.link_tokens[token_hash].used_at == FIXED_NOW
    assert env.repo.profiles[profile.id].telegram_user_id == USER_ID
    assert env.gateway.sent[-1] == (CHAT_ID, env.settings.link_success_reply)


def test_consented_non_staff_keeps_existing_authorization(env):
    """R12, R13, R14: con consentimiento, la autorización no gana permisos."""
    env.repo.add_privacy_consent(
        USER_ID, env.settings.privacy_notice_version, "sha", FIXED_NOW
    )

    env.post(
        text="/consultar cuántos pedidos hay",
        update_id=1,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )
    [audit] = env.repo.db_query_audits
    assert audit.status == "forbidden"
    assert env.gateway.sent[-1] == (CHAT_ID, env.settings.db_query_forbidden_reply)

    env.handover.authorized_advisors = set()
    env.post(
        text="/responder case-1 hola",
        update_id=2,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )
    assert env.gateway.sent[-1] == (
        CHAT_ID,
        env.settings.advisor_command_forbidden_reply,
    )
    assert any(event.type == "advisor_forbidden" for event in env.repo.events)

    env.post(
        text="/responder",
        update_id=3,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )
    assert env.gateway.sent[-1] == (CHAT_ID, env.settings.advisor_command_help)


def test_consented_client_free_text_unchanged(env):
    """R21: con consentimiento la ruta de texto libre sigue igual."""
    response = env.post()

    assert response.status_code == 202
    assert env.repo.contacts[USER_ID].telegram_user_id == USER_ID
    assert [message.role for message in env.repo.messages] == ["user", "bot"]
    assert env.rag.calls == [("¿Cómo instalo el módulo?", 7)]
    assert env.gateway.sent == [(CHAT_ID, "Respuesta final")]


def test_notice_version_change_blocks_new_data(env):
    """R22: un consentimiento de otra versión no desbloquea datos nuevos."""
    env.repo.add_privacy_consent(USER_ID, "v0", "sha-v0", FIXED_NOW)

    env.post(text="hola", update_id=1, user=USER_ID, chat=CHAT_ID, consent=False)
    env.post(
        text="/consultar cuántos pedidos hay",
        update_id=2,
        user=USER_ID,
        chat=CHAT_ID,
        consent=False,
    )

    assert len(env.gateway.sent) == 2
    assert all(chat_id == CHAT_ID for chat_id, _ in env.gateway.sent)
    assert all(
        env.settings.privacy_notice_text in text
        for _, text in env.gateway.sent
    )
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.db_query_audits == []
    assert [consent.notice_version for consent in env.repo.privacy_consents] == ["v0"]
