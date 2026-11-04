"""Persistencia (contactos, historial, eventos, update_id, casos) detrás de un Repository."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import unquote, urlparse

from lazaro_contracts import LastMessage

from ..classifier import Category
from ..domain import (
    ClientCredential,
    ClientSession,
    ClientStatus,
    Contact,
    ConversationState,
    Profile,
    SummaryView,
    TemplateExists,
    UsernameTaken,
)
from ..memory import in_window, session_window
from ..privacy import (
    ConversationTexts,
    conversation_text_settings,
    parse_conversation_texts,
)


class Repository(Protocol):
    def mark_message_if_new(
        self, channel: str, external_message_id: str
    ) -> bool: ...

    def mark_update_if_new(self, update_id: int) -> bool: ...

    def get_or_create_contact(
        self, telegram_user_id: int, chat_id: int, now: datetime
    ) -> Contact: ...

    def get_or_create_channel_contact(
        self, channel: str, external_user_id: str, external_chat_id: str, now: datetime
    ) -> Contact: ...

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None: ...

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]: ...

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None: ...

    def link_case(
        self,
        case_id: str,
        contact_id: str,
        at: datetime,
        profile_id: str | None = None,
    ) -> None: ...

    def get_case_contact(self, case_id: str) -> Contact | None: ...

    def get_case_link(self, case_id: str) -> "CaseLink | None": ...

    def case_activity(
        self, contact_id: str, since: datetime
    ) -> tuple[datetime | None, datetime | None]: ...

    def last_user_message_at(self, contact_id: str) -> datetime | None: ...

    def case_messages(
        self, contact_id: str, since: datetime, limit: int
    ) -> list[tuple[str, str, datetime]]: ...

    def foreign_session_windows(
        self, contact_id: str, profile_id: str | None, idle_minutes: int, now: datetime
    ) -> list[tuple[datetime, datetime, datetime]]: ...

    def last_privacy_decision(
        self, channel: str, external_user_id: str
    ) -> tuple[str, str, datetime | None] | None: ...

    def set_advisor_presence(
        self, profile_id: str, status: str, now: datetime
    ) -> None: ...

    def touch_advisor_presence(self, profile_id: str, now: datetime) -> None: ...

    def get_advisor_presence(
        self, profile_ids: Sequence[str]
    ) -> dict[str, tuple[str, datetime]]: ...

    def add_panel_audit(
        self,
        actor_profile_id: str,
        actor_role: str,
        action: str,
        case_id: str | None,
        request_id: str | None,
        target: str | None,
        result: str,
        at: datetime,
    ) -> None: ...

    def list_panel_audit(self, limit: int) -> list["PanelAudit"]: ...

    def list_suppression_requests(
        self, executed_limit: int
    ) -> list["StoredSuppressionRequest"]: ...

    def set_suppression_outcome(
        self, request_id: str, note: str | None, notification_result: str
    ) -> None: ...

    def get_case_profile(self, case_id: str) -> str | None: ...

    def get_contact(self, contact_id: str) -> Contact | None: ...

    def get_contact_last_case(self, contact_id: str) -> str | None: ...

    def record_rag_outcome(
        self,
        contact_id: str,
        update_id: int,
        outcome: str,
        threshold: int,
        failure_reasons: set[str],
    ) -> bool: ...

    def reset_rag_streak(self, contact_id: str) -> None: ...

    def finish_auto_handover(self, contact_id: str, success: bool) -> None: ...

    def create_profile(
        self, username: str, role: str, password_hash: str, now: datetime
    ) -> Profile: ...

    def get_profile(self, profile_id: str) -> Profile | None: ...

    def get_profile_by_telegram_user_id(
        self, telegram_user_id: int
    ) -> Profile | None: ...

    def add_db_query_audit(
        self,
        profile_id: str | None,
        telegram_user_id: int,
        status: str,
        views: str,
        row_count: int,
        sql_sha256: str,
        at: datetime,
    ) -> None: ...

    def add_tool_call(
        self,
        contact_id: str,
        profile_id: str | None,
        state: str,
        tool: str,
        origin: str,
        decision: str,
        result: str,
        args_sha256: str,
        detail: str,
        at: datetime,
    ) -> None: ...

    def create_or_get_pending_suppression(
        self,
        request_id: str,
        profile_id: str,
        contact_id: str,
        channel: str,
        at: datetime,
    ) -> tuple[str, bool]: ...

    def set_suppression_case(self, request_id: str, case_id: str) -> None: ...

    def get_profile_credentials(self, username: str) -> tuple[Profile, str] | None: ...

    def list_profiles(self) -> list[Profile]: ...

    def set_role(self, profile_id: str, role: str) -> bool: ...

    def create_session(
        self, token_hash: str, profile_id: str, csrf_token: str, expires_at: datetime
    ) -> None: ...

    def get_session(self, token_hash: str, now: datetime) -> "AdminSession | None": ...

    def get_session_for_role(
        self, token_hash: str, now: datetime, role: str
    ) -> "AdminSession | None": ...

    def delete_session(self, token_hash: str) -> None: ...

    def recent_events(self, limit: int) -> list["StoredEvent"]: ...

    def count_login_failures(
        self, username: str, ip: str, since: datetime
    ) -> tuple[int, int]: ...

    def record_login_failure(
        self, username: str, ip: str, at: datetime, purge_before: datetime
    ) -> None: ...

    def clear_login_failures(self, username: str) -> None: ...

    def add_link_token(self, token_hash: str, profile_id: str, expires_at: datetime) -> None: ...

    def consume_link_token(
        self, token_hash: str, telegram_user_id: int, now: datetime
    ) -> bool: ...

    def get_link_token_role(self, token_hash: str, now: datetime) -> str | None: ...

    def list_categories(self) -> list[Category]: ...

    def create_category(self, category: Category, now: datetime) -> bool: ...

    def update_category(
        self, category_id: str, name: str, keywords: tuple[str, ...]
    ) -> bool: ...

    def set_category_active(self, category_id: str, active: bool) -> bool: ...

    def get_classifier_threshold(self) -> float | None: ...

    def set_classifier_threshold(self, value: float) -> None: ...

    def has_privacy_consent(self, telegram_user_id: int, notice_version: str) -> bool: ...

    def has_channel_privacy_consent(
        self, channel: str, external_user_id: str, notice_version: str
    ) -> bool: ...

    def add_privacy_consent(
        self,
        telegram_user_id: int,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None: ...

    def add_channel_privacy_consent(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None: ...

    def add_privacy_decision(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        result: str,
        external_message_id: str,
        button_id: str,
        at: datetime,
        evidence_type: str = "button",
    ) -> None: ...

    def last_privacy_result(
        self, channel: str, external_user_id: str
    ) -> str | None: ...

    def find_channel_contact(
        self, channel: str, external_user_id: str
    ) -> Contact | None: ...

    def delete_contact_content(
        self, channel: str, external_user_id: str
    ) -> None: ...

    def get_conversation_state(self, contact_id: str) -> "ConversationState | None": ...

    def set_conversation_state(
        self, contact_id: str, state: "ConversationState", at: datetime
    ) -> None: ...

    def get_conversation_texts(self) -> ConversationTexts: ...

    def save_conversation_texts(
        self, texts: ConversationTexts, admin_profile_id: str, at: datetime
    ) -> None: ...

    def purge_personal_data(self, cutoff: datetime, ran_at: datetime) -> dict[str, int]: ...

    def create_client_credential(
        self,
        username: str,
        password_hash: str,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
    ) -> Profile: ...

    def get_client_credential(self, profile_id: str) -> ClientCredential | None: ...

    def get_client_credentials_by_username(
        self, username: str
    ) -> tuple[Profile, str, ClientCredential | None] | None: ...

    def renew_client_credential(
        self, profile_id: str, valid_until: datetime, now: datetime
    ) -> bool: ...

    def revoke_client_credential(self, profile_id: str, now: datetime) -> bool: ...

    def add_login_link(
        self,
        token_hash: str,
        contact_id: str,
        channel: str,
        external_chat_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> None: ...

    def get_login_link(self, token_hash: str, now: datetime) -> "LoginLink | None": ...

    def start_client_session(
        self, token_hash: str, profile_id: str, session_id: str, now: datetime
    ) -> str: ...

    def get_active_session_by_contact(self, contact_id: str) -> ClientSession | None: ...

    def get_active_session_by_profile(self, profile_id: str) -> ClientSession | None: ...

    def touch_client_session(self, session_id: str, now: datetime) -> None: ...

    def end_client_session(
        self, session_id: str, reason: str, now: datetime
    ) -> bool: ...

    def count_identity_login_failures(
        self, username: str, ip: str, since: datetime
    ) -> tuple[int, int]: ...

    def record_identity_login_failure(
        self, username: str, ip: str, now: datetime, prune_before: datetime
    ) -> None: ...

    def clear_identity_login_failures(self, username: str) -> None: ...

    def add_identity_audit(
        self,
        profile_id: str | None,
        contact_id: str | None,
        action: str,
        reason: str,
        at: datetime,
    ) -> None: ...

    def get_identity_overrides(self) -> dict[str, str]: ...

    def session_messages(
        self,
        contact_id: str,
        since: datetime,
        until: datetime,
        idle_limit: datetime,
        limit: int,
    ) -> list[tuple[str, str, datetime]]: ...

    def get_client_memory(
        self, profile_id: str
    ) -> tuple[tuple[str, ...], datetime | None]: ...

    def set_client_memory(
        self,
        profile_id: str,
        items: Sequence[str],
        source_session_id: str,
        now: datetime,
    ) -> None: ...

    def upsert_conversation_summary(
        self,
        session_id: str,
        profile_id: str,
        contact_id: str,
        channel: str,
        summary: str,
        trigger: str,
        now: datetime,
    ) -> None: ...

    def list_conversation_summaries(
        self, profile_id: str, limit: int
    ) -> list[SummaryView]: ...

    def get_suppression_request(
        self, request_id: str
    ) -> "StoredSuppressionRequest | None": ...

    def execute_suppression(
        self, request_id: str, executed_by: str, idle_minutes: int, now: datetime
    ) -> dict[str, int] | None: ...

    # administración y avisos (#42)
    def get_app_settings(self, prefixes: Sequence[str]) -> dict[str, str]: ...

    def save_app_settings(
        self, upserts: dict[str, str], deletes: Sequence[str]
    ) -> None: ...

    def current_text_versions(self) -> dict[str, int]: ...

    def text_history(self, field: str, limit: int) -> list["TextVersion"]: ...

    def list_client_credentials(self) -> list["ClientCredentialRow"]: ...

    def current_expiry_notice_status(
        self, profile_id: str, valid_until: datetime
    ) -> str | None: ...

    def list_whatsapp_templates(self) -> list["WhatsAppTemplate"]: ...

    def create_whatsapp_template(self, template: "WhatsAppTemplate") -> None: ...

    def update_whatsapp_template(
        self,
        name: str,
        language: str,
        variables: int,
        body: str,
        actor: str,
        at: datetime,
    ) -> bool: ...

    def set_whatsapp_template_status(
        self,
        name: str,
        from_status: str,
        to_status: str,
        actor: str,
        at: datetime,
    ) -> bool: ...

    def list_expiring_credentials(
        self, now: datetime, horizon: datetime
    ) -> list["ExpiringCredential"]: ...

    def last_client_contact(self, profile_id: str) -> Contact | None: ...

    def claim_expiry_notice(
        self,
        profile_id: str,
        valid_until: datetime,
        now: datetime,
        max_attempts: int,
    ) -> bool: ...

    def finish_expiry_notice(
        self,
        profile_id: str,
        valid_until: datetime,
        status: str,
        method: str,
        now: datetime,
    ) -> None: ...

    def case_first_responses(
        self, since: datetime, until: datetime
    ) -> list[tuple[datetime, datetime | None]]: ...

    def advisor_reply_contacts(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, int]]: ...

    def event_reason_counts(
        self, event_type: str, since: datetime, until: datetime
    ) -> list[tuple[str, int]]: ...

    def count_events(
        self, types: tuple[str, ...], since: datetime, until: datetime
    ) -> int: ...

    def unanswered_samples(
        self, since: datetime, until: datetime, limit: int
    ) -> list[tuple[datetime, str]]: ...


RAG_OUTCOMES = frozenset({"no_relevant_chunks", "invalid_answer", "rag_answer"})


@dataclass
class RagStreak:
    failure_count: int
    state: str


@dataclass
class StoredMessage:
    contact_id: str
    role: str
    text: str
    at: datetime


@dataclass
class StoredEvent:
    contact_id: str
    type: str
    reason: str
    at: datetime


@dataclass
class StoredProfile:
    id: str
    username: str
    role: str
    password_hash: str
    telegram_user_id: int | None = None


@dataclass
class StoredLinkToken:
    token_hash: str
    profile_id: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class LoginLink:
    token_hash: str
    contact_id: str
    channel: str
    external_chat_id: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class IdentityAudit:
    profile_id: str | None
    contact_id: str | None
    action: str
    reason: str
    at: datetime


@dataclass
class AdminSession:
    token_hash: str
    profile_id: str
    csrf_token: str
    expires_at: datetime


@dataclass
class StoredLoginFailure:
    username: str
    ip: str
    at: datetime


@dataclass
class DbQueryAudit:
    profile_id: str | None
    telegram_user_id: int
    status: str
    views: str
    row_count: int
    sql_sha256: str
    at: datetime


@dataclass
class StoredToolCall:
    contact_id: str
    profile_id: str | None
    state: str
    tool: str
    origin: str
    decision: str
    result: str
    args_sha256: str
    detail: str
    at: datetime


@dataclass
class StoredSuppressionRequest:
    id: str
    profile_id: str
    contact_id: str
    channel: str
    status: str
    case_id: str | None
    created_at: datetime
    executed_at: datetime | None = None
    executed_by: str | None = None
    removed_counts: dict[str, int] | None = None
    result_note: str | None = None
    notification_result: str | None = None


@dataclass(frozen=True)
class CaseLink:
    case_id: str
    contact: Contact
    profile_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class TextVersion:
    field: str
    version: int
    value: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class ClientCredentialRow:
    profile: Profile
    credential: ClientCredential
    has_active_session: bool


@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str
    purpose: str
    language: str
    variables: int
    body: str
    status: str
    approved_by: str | None
    approved_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class ExpiringCredential:
    profile_id: str
    valid_until: datetime


@dataclass(frozen=True)
class PanelAudit:
    actor_profile_id: str
    actor_role: str
    action: str
    case_id: str | None
    request_id: str | None
    target: str | None
    result: str
    at: datetime


@dataclass
class StoredClientMemory:
    profile_id: str
    items: tuple[str, ...]
    source_session_id: str | None
    updated_at: datetime


@dataclass
class StoredConversationSummary:
    session_id: str
    profile_id: str
    contact_id: str
    channel: str
    summary: str
    trigger: str
    created_at: datetime
    updated_at: datetime


@dataclass
class PrivacyConsent:
    notice_version: str
    notice_sha256: str
    accepted_at: datetime | None
    channel: str = "telegram"
    external_user_id: str = ""
    telegram_user_id: int | None = None
    result: str = "accepted"
    evidence_type: str = "button"
    external_message_id: str = ""
    button_id: str = ""
    occurred_at: datetime | None = None


def _telegram_value(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.contacts: dict[object, Contact] = {}
        self.messages: list[StoredMessage] = []
        self.events: list[StoredEvent] = []
        self.processed: set[int] = set()
        self.processed_messages: set[tuple[str, str]] = set()
        self.case_links: dict[str, str] = {}
        self.profiles: dict[str, StoredProfile] = {}
        self.link_tokens: dict[str, StoredLinkToken] = {}
        self.sessions: dict[str, AdminSession] = {}
        self.login_failures: list[StoredLoginFailure] = []
        self.categories: dict[str, Category] = {}
        self.classifier_threshold: float | None = None
        self.rag_streaks: dict[str, RagStreak] = {}
        self.rag_outcomes: set[tuple[str, int]] = set()
        self.rag_outcome_at: dict[tuple[str, int], datetime] = {}
        self.db_query_audits: list[DbQueryAudit] = []
        self.tool_calls: list[StoredToolCall] = []
        self.suppression_requests: dict[str, StoredSuppressionRequest] = {}
        self.fail_db_query_audit = False
        self.contact_created_at: dict[str, datetime] = {}
        self.case_link_created_at: dict[str, datetime] = {}
        self.privacy_consents: list[PrivacyConsent] = []
        self.privacy_purge_runs: list[dict[str, Any]] = []
        self.fail_privacy_consent = False
        self.conversation_states: dict[str, tuple[ConversationState, datetime]] = {}
        self.conversation_texts = ConversationTexts()
        self.client_credentials: dict[str, ClientCredential] = {}
        self.login_links: dict[str, LoginLink] = {}
        self.client_sessions: dict[str, ClientSession] = {}
        self.identity_login_attempts: list[StoredLoginFailure] = []
        self.identity_audits: list[IdentityAudit] = []
        self.identity_overrides: dict[str, str] = {}
        self.client_memory: dict[str, StoredClientMemory] = {}
        self.conversation_summaries: dict[str, StoredConversationSummary] = {}
        self.case_profiles: dict[str, str | None] = {}
        self.advisor_presence: dict[str, tuple[str, datetime]] = {}
        self.panel_audit: list[PanelAudit] = []
        self.text_versions: list[TextVersion] = []
        self.whatsapp_templates: dict[str, WhatsAppTemplate] = {}
        self.expiry_notices: dict[tuple[str, datetime], dict[str, Any]] = {}
        self._expiry_lock = threading.Lock()
        self._app_settings: dict[str, str] = {}
        self._profiles_lock = threading.Lock()
        self._rag_lock = threading.Lock()
        self._processed_lock = threading.Lock()
        self._identity_lock = threading.Lock()

    def mark_message_if_new(
        self, channel: str, external_message_id: str
    ) -> bool:
        """R5, R6: la clave es (canal, mensaje externo), no el id aislado."""
        with self._processed_lock:
            legacy_id: int | None = None
            if channel == "telegram":
                try:
                    legacy_id = int(external_message_id)
                except ValueError:
                    legacy_id = None
            if (channel, external_message_id) in self.processed_messages:
                return False
            if legacy_id is not None and legacy_id in self.processed:
                return False
            self.processed_messages.add((channel, external_message_id))
            return True

    def mark_update_if_new(self, update_id: int) -> bool:
        """R22: el endpoint legacy solo conserva `update_id`, sin identidad."""
        with self._processed_lock:
            if update_id in self.processed:
                return False
            if ("telegram", str(update_id)) in self.processed_messages:
                return False
            self.processed.add(update_id)
            return True

    def _contact_key(self, channel: str, external_user_id: str) -> object:
        """Clave interna de `contacts`; Telegram conserva la clave entera histórica."""
        if channel == "telegram":
            legacy = _telegram_value(external_user_id)
            if legacy is not None:
                return legacy
        return (channel, external_user_id)

    def get_or_create_contact(self, telegram_user_id: int, chat_id: int, now: datetime) -> Contact:
        return self.get_or_create_channel_contact(
            "telegram", str(telegram_user_id), str(chat_id), now
        )

    def get_or_create_channel_contact(
        self, channel: str, external_user_id: str, external_chat_id: str, now: datetime
    ) -> Contact:
        key = self._contact_key(channel, external_user_id)
        contact = self.contacts.get(key)
        if contact is None:
            telegram_user_id = (
                _telegram_value(external_user_id) if channel == "telegram" else None
            )
            chat_id = (
                _telegram_value(external_chat_id) if channel == "telegram" else None
            )
            contact = Contact(
                id=f"c{len(self.contacts) + 1}",
                channel=channel,
                external_user_id=external_user_id,
                external_chat_id=external_chat_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
            )
            self.contacts[key] = contact
            self.contact_created_at[contact.id] = now
        return contact

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None:
        self.messages.append(StoredMessage(contact_id, role, text, at))

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]:
        own = [m for m in self.messages if m.contact_id == contact_id]
        return [LastMessage(role=m.role, text=m.text, at=m.at) for m in own[-limit:]]  # type: ignore[arg-type]

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None:
        self.events.append(StoredEvent(contact_id, type, reason, at))

    def link_case(
        self,
        case_id: str,
        contact_id: str,
        at: datetime,
        profile_id: str | None = None,
    ) -> None:
        self.case_links.setdefault(case_id, contact_id)
        self.case_link_created_at.setdefault(case_id, at)
        self.case_profiles.setdefault(case_id, profile_id)

    def get_case_contact(self, case_id: str) -> Contact | None:
        contact_id = self.case_links.get(case_id)
        for contact in self.contacts.values():
            if contact.id == contact_id:
                return contact
        return None

    def get_case_link(self, case_id: str) -> CaseLink | None:
        contact_id = self.case_links.get(case_id)
        if contact_id is None:
            return None
        contact = self.get_contact(contact_id)
        if contact is None:
            return None
        created_at = self.case_link_created_at.get(case_id)
        if created_at is None:
            return None
        return CaseLink(
            case_id=case_id,
            contact=contact,
            profile_id=self.case_profiles.get(case_id),
            created_at=created_at,
        )

    def case_activity(
        self, contact_id: str, since: datetime
    ) -> tuple[datetime | None, datetime | None]:
        last_user: datetime | None = None
        last_advisor: datetime | None = None
        for message in self.messages:
            if message.contact_id != contact_id or message.at < since:
                continue
            if message.role == "user" and (
                last_user is None or message.at > last_user
            ):
                last_user = message.at
            if message.role == "advisor" and (
                last_advisor is None or message.at > last_advisor
            ):
                last_advisor = message.at
        return last_user, last_advisor

    def last_user_message_at(self, contact_id: str) -> datetime | None:
        values = [
            message.at
            for message in self.messages
            if message.contact_id == contact_id and message.role == "user"
        ]
        return max(values) if values else None

    def case_messages(
        self, contact_id: str, since: datetime, limit: int
    ) -> list[tuple[str, str, datetime]]:
        selected = [
            message
            for message in self.messages
            if message.contact_id == contact_id and message.at >= since
        ]
        selected.sort(key=lambda message: message.at)
        return [
            (message.role, message.text, message.at) for message in selected[-limit:]
        ]

    def foreign_session_windows(
        self, contact_id: str, profile_id: str | None, idle_minutes: int, now: datetime
    ) -> list[tuple[datetime, datetime, datetime]]:
        return [
            session_window(
                session.started_at,
                session.last_activity_at,
                session.ended_at,
                now,
                idle_minutes,
            )
            for session in self.client_sessions.values()
            if session.contact_id == contact_id
            and (profile_id is None or session.profile_id != profile_id)
        ]

    def last_privacy_decision(
        self, channel: str, external_user_id: str
    ) -> tuple[str, str, datetime | None] | None:
        for consent in reversed(self.privacy_consents):
            if (
                consent.channel == channel
                and consent.external_user_id == external_user_id
            ):
                return (
                    consent.result,
                    consent.notice_version,
                    consent.occurred_at or consent.accepted_at,
                )
        return None

    def set_advisor_presence(
        self, profile_id: str, status: str, now: datetime
    ) -> None:
        self.advisor_presence[profile_id] = (status, now)

    def touch_advisor_presence(self, profile_id: str, now: datetime) -> None:
        current = self.advisor_presence.get(profile_id)
        status = current[0] if current is not None else "away"
        self.advisor_presence[profile_id] = (status, now)

    def get_advisor_presence(
        self, profile_ids: Sequence[str]
    ) -> dict[str, tuple[str, datetime]]:
        return {
            profile_id: self.advisor_presence[profile_id]
            for profile_id in profile_ids
            if profile_id in self.advisor_presence
        }

    def add_panel_audit(
        self,
        actor_profile_id: str,
        actor_role: str,
        action: str,
        case_id: str | None,
        request_id: str | None,
        target: str | None,
        result: str,
        at: datetime,
    ) -> None:
        self.panel_audit.append(
            PanelAudit(
                actor_profile_id=actor_profile_id,
                actor_role=actor_role,
                action=action,
                case_id=case_id,
                request_id=request_id,
                target=target,
                result=result,
                at=at,
            )
        )

    def list_panel_audit(self, limit: int) -> list[PanelAudit]:
        indexed = list(enumerate(self.panel_audit))
        indexed.sort(key=lambda pair: (pair[1].at, pair[0]), reverse=True)
        return [row for _, row in indexed[:limit]]

    def list_suppression_requests(
        self, executed_limit: int
    ) -> list[StoredSuppressionRequest]:
        pending = [
            request
            for request in self.suppression_requests.values()
            if request.status == "pending"
        ]
        pending.sort(key=lambda request: (request.created_at, request.id))
        executed = [
            request
            for request in self.suppression_requests.values()
            if request.status == "executed"
        ]
        executed.sort(
            key=lambda request: (
                request.executed_at or request.created_at,
                request.id,
            ),
            reverse=True,
        )
        return [request for request in pending] + executed[:executed_limit]

    def set_suppression_outcome(
        self, request_id: str, note: str | None, notification_result: str
    ) -> None:
        stored = self.suppression_requests.get(request_id)
        if stored is not None:
            stored.result_note = note
            stored.notification_result = notification_result

    def get_case_profile(self, case_id: str) -> str | None:
        return self.case_profiles.get(case_id)

    def get_contact(self, contact_id: str) -> Contact | None:
        for contact in self.contacts.values():
            if contact.id == contact_id:
                return contact
        return None

    def get_contact_last_case(self, contact_id: str) -> str | None:
        last: str | None = None
        for case_id, linked_contact_id in self.case_links.items():
            if linked_contact_id == contact_id:
                last = case_id
        return last

    def record_rag_outcome(
        self,
        contact_id: str,
        update_id: int,
        outcome: str,
        threshold: int,
        failure_reasons: set[str],
    ) -> bool:
        if outcome not in RAG_OUTCOMES:
            raise ValueError("outcome de RAG no permitido")
        with self._rag_lock:
            key = (contact_id, update_id)
            if key in self.rag_outcomes:
                return False
            self.rag_outcomes.add(key)
            self.rag_outcome_at[key] = datetime.now(timezone.utc)

            if outcome == "rag_answer":
                self.rag_streaks[contact_id] = RagStreak(0, "open")
                return False

            streak = self.rag_streaks.get(contact_id)
            if streak is not None and streak.state == "retry":
                if outcome in failure_reasons:
                    streak.failure_count += 1
                streak.state = "pending"
                return True
            if outcome not in failure_reasons:
                return False

            streak = self.rag_streaks.setdefault(contact_id, RagStreak(0, "open"))
            streak.failure_count += 1
            if streak.state in ("pending", "handed_over"):
                return False
            if streak.failure_count >= threshold:
                streak.state = "pending"
                return True
            return False

    def reset_rag_streak(self, contact_id: str) -> None:
        with self._rag_lock:
            self.rag_streaks[contact_id] = RagStreak(0, "open")

    def finish_auto_handover(self, contact_id: str, success: bool) -> None:
        with self._rag_lock:
            streak = self.rag_streaks.get(contact_id)
            if streak is None:
                return
            streak.state = "handed_over" if success else "retry"

    def create_profile(
        self, username: str, role: str, password_hash: str, now: datetime
    ) -> Profile:
        normalized = username.lower()
        with self._profiles_lock:
            if any(p.username == normalized for p in self.profiles.values()):
                raise UsernameTaken("El nombre de usuario ya existe.")
            profile_id = f"p{len(self.profiles) + 1}"
            self.profiles[profile_id] = StoredProfile(
                id=profile_id,
                username=normalized,
                role=role,
                password_hash=password_hash,
            )
        return Profile(id=profile_id, username=normalized, role=role)

    def get_profile(self, profile_id: str) -> Profile | None:
        stored = self.profiles.get(profile_id)
        if stored is None:
            return None
        return Profile(
            id=stored.id,
            username=stored.username,
            role=stored.role,
            telegram_user_id=stored.telegram_user_id,
        )

    def get_profile_by_telegram_user_id(
        self, telegram_user_id: int
    ) -> Profile | None:
        for stored in self.profiles.values():
            if stored.telegram_user_id == telegram_user_id:
                return Profile(
                    id=stored.id,
                    username=stored.username,
                    role=stored.role,
                    telegram_user_id=stored.telegram_user_id,
                )
        return None

    def add_db_query_audit(
        self,
        profile_id: str | None,
        telegram_user_id: int,
        status: str,
        views: str,
        row_count: int,
        sql_sha256: str,
        at: datetime,
    ) -> None:
        if self.fail_db_query_audit:
            raise RuntimeError("audit no disponible")
        self.db_query_audits.append(
            DbQueryAudit(
                profile_id=profile_id,
                telegram_user_id=telegram_user_id,
                status=status,
                views=views,
                row_count=row_count,
                sql_sha256=sql_sha256,
                at=at,
            )
        )

    def add_tool_call(
        self,
        contact_id: str,
        profile_id: str | None,
        state: str,
        tool: str,
        origin: str,
        decision: str,
        result: str,
        args_sha256: str,
        detail: str,
        at: datetime,
    ) -> None:
        self.tool_calls.append(
            StoredToolCall(
                contact_id=contact_id,
                profile_id=profile_id,
                state=state,
                tool=tool,
                origin=origin,
                decision=decision,
                result=result,
                args_sha256=args_sha256,
                detail=detail,
                at=at,
            )
        )

    def create_or_get_pending_suppression(
        self,
        request_id: str,
        profile_id: str,
        contact_id: str,
        channel: str,
        at: datetime,
    ) -> tuple[str, bool]:
        for stored in self.suppression_requests.values():
            if stored.profile_id == profile_id and stored.status == "pending":
                return stored.id, False
        self.suppression_requests[request_id] = StoredSuppressionRequest(
            id=request_id,
            profile_id=profile_id,
            contact_id=contact_id,
            channel=channel,
            status="pending",
            case_id=None,
            created_at=at,
        )
        return request_id, True

    def set_suppression_case(self, request_id: str, case_id: str) -> None:
        stored = self.suppression_requests.get(request_id)
        if stored is not None:
            stored.case_id = case_id

    def add_link_token(self, token_hash: str, profile_id: str, expires_at: datetime) -> None:
        self.link_tokens[token_hash] = StoredLinkToken(
            token_hash=token_hash, profile_id=profile_id, expires_at=expires_at
        )

    def get_profile_credentials(self, username: str) -> tuple[Profile, str] | None:
        normalized = username.lower()
        for stored in self.profiles.values():
            if stored.username == normalized:
                profile = Profile(
                    id=stored.id,
                    username=stored.username,
                    role=stored.role,
                    telegram_user_id=stored.telegram_user_id,
                )
                return profile, stored.password_hash
        return None

    def list_profiles(self) -> list[Profile]:
        return [
            Profile(
                id=stored.id,
                username=stored.username,
                role=stored.role,
                telegram_user_id=stored.telegram_user_id,
            )
            for stored in self.profiles.values()
        ]

    def set_role(self, profile_id: str, role: str) -> bool:
        with self._profiles_lock:
            stored = self.profiles.get(profile_id)
            if stored is None:
                return False
            if role != "admin" and stored.role == "admin":
                admins = sum(1 for p in self.profiles.values() if p.role == "admin")
                if admins <= 1:
                    return False
            stored.role = role
            return True

    def create_session(
        self, token_hash: str, profile_id: str, csrf_token: str, expires_at: datetime
    ) -> None:
        self.sessions[token_hash] = AdminSession(
            token_hash=token_hash,
            profile_id=profile_id,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    def get_session(self, token_hash: str, now: datetime) -> AdminSession | None:
        return self.get_session_for_role(token_hash, now, "admin")

    def get_session_for_role(
        self, token_hash: str, now: datetime, role: str
    ) -> AdminSession | None:
        session = self.sessions.get(token_hash)
        if session is None or session.expires_at <= now:
            return None
        profile = self.profiles.get(session.profile_id)
        if profile is None or profile.role != role:
            return None
        return session

    def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    def recent_events(self, limit: int) -> list[StoredEvent]:
        indexed = list(enumerate(self.events))
        indexed.sort(key=lambda pair: (pair[1].at, pair[0]), reverse=True)
        return [event for _, event in indexed[:limit]]

    def count_login_failures(self, username: str, ip: str, since: datetime) -> tuple[int, int]:
        by_username = sum(
            1 for failure in self.login_failures
            if failure.username == username and failure.at > since
        )
        by_ip = sum(
            1 for failure in self.login_failures if failure.ip == ip and failure.at > since
        )
        return by_username, by_ip

    def record_login_failure(
        self, username: str, ip: str, at: datetime, purge_before: datetime
    ) -> None:
        self.login_failures.append(StoredLoginFailure(username=username, ip=ip, at=at))
        self.login_failures = [
            failure for failure in self.login_failures if failure.at >= purge_before
        ]

    def clear_login_failures(self, username: str) -> None:
        self.login_failures = [
            failure for failure in self.login_failures if failure.username != username
        ]

    def consume_link_token(
        self, token_hash: str, telegram_user_id: int, now: datetime
    ) -> bool:
        with self._profiles_lock:
            token = self.link_tokens.get(token_hash)
            if token is None or token.used_at is not None or token.expires_at <= now:
                return False
            profile = self.profiles.get(token.profile_id)
            if profile is None:
                return False
            linked_elsewhere = any(
                other.telegram_user_id == telegram_user_id and other.id != profile.id
                for other in self.profiles.values()
            )
            if linked_elsewhere:
                return False
            token.used_at = now
            profile.telegram_user_id = telegram_user_id
            return True

    def get_link_token_role(self, token_hash: str, now: datetime) -> str | None:
        with self._profiles_lock:
            token = self.link_tokens.get(token_hash)
            if token is None or token.used_at is not None or token.expires_at <= now:
                return None
            profile = self.profiles.get(token.profile_id)
            return profile.role if profile is not None else None

    def list_categories(self) -> list[Category]:
        return sorted(self.categories.values(), key=lambda category: category.code)

    def create_category(self, category: Category, now: datetime) -> bool:
        if any(
            stored.code == category.code for stored in self.categories.values()
        ):
            return False
        self.categories[category.id] = category
        return True

    def update_category(
        self, category_id: str, name: str, keywords: tuple[str, ...]
    ) -> bool:
        stored = self.categories.get(category_id)
        if stored is None:
            return False
        self.categories[category_id] = Category(
            id=stored.id,
            code=stored.code,
            name=name,
            keywords=keywords,
            active=stored.active,
        )
        return True

    def set_category_active(self, category_id: str, active: bool) -> bool:
        stored = self.categories.get(category_id)
        if stored is None:
            return False
        self.categories[category_id] = Category(
            id=stored.id,
            code=stored.code,
            name=stored.name,
            keywords=stored.keywords,
            active=active,
        )
        return True

    def get_classifier_threshold(self) -> float | None:
        return self.classifier_threshold

    def set_classifier_threshold(self, value: float) -> None:
        self.classifier_threshold = value

    def has_privacy_consent(self, telegram_user_id: int, notice_version: str) -> bool:
        return self.has_channel_privacy_consent(
            "telegram", str(telegram_user_id), notice_version
        )

    def has_channel_privacy_consent(
        self, channel: str, external_user_id: str, notice_version: str
    ) -> bool:
        """R4, R34: solo una aceptación de botón de la versión vigente habilita."""
        return any(
            consent.channel == channel
            and consent.external_user_id == external_user_id
            and consent.notice_version == notice_version
            and consent.result == "accepted"
            and consent.evidence_type == "button"
            for consent in self.privacy_consents
        )

    def add_privacy_consent(
        self,
        telegram_user_id: int,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        self.add_channel_privacy_consent(
            "telegram",
            str(telegram_user_id),
            notice_version,
            notice_sha256,
            accepted_at,
        )

    def add_channel_privacy_consent(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        if self.fail_privacy_consent:
            raise RuntimeError("consentimiento no disponible")
        telegram_user_id = (
            _telegram_value(external_user_id) if channel == "telegram" else None
        )
        self.privacy_consents.append(
            PrivacyConsent(
                channel=channel,
                external_user_id=external_user_id,
                telegram_user_id=telegram_user_id,
                notice_version=notice_version,
                notice_sha256=notice_sha256,
                accepted_at=accepted_at,
                result="accepted",
                evidence_type="button",
                occurred_at=accepted_at,
            )
        )

    def add_privacy_decision(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        result: str,
        external_message_id: str,
        button_id: str,
        at: datetime,
        evidence_type: str = "button",
    ) -> None:
        if self.fail_privacy_consent:
            raise RuntimeError("consentimiento no disponible")
        telegram_user_id = (
            _telegram_value(external_user_id) if channel == "telegram" else None
        )
        self.privacy_consents.append(
            PrivacyConsent(
                channel=channel,
                external_user_id=external_user_id,
                telegram_user_id=telegram_user_id,
                notice_version=notice_version,
                notice_sha256=notice_sha256,
                accepted_at=at if result == "accepted" else None,
                result=result,
                evidence_type=evidence_type,
                external_message_id=external_message_id,
                button_id=button_id,
                occurred_at=at,
            )
        )

    def last_privacy_result(
        self, channel: str, external_user_id: str
    ) -> str | None:
        for consent in reversed(self.privacy_consents):
            if (
                consent.channel == channel
                and consent.external_user_id == external_user_id
            ):
                return consent.result
        return None

    def find_channel_contact(
        self, channel: str, external_user_id: str
    ) -> Contact | None:
        return self.contacts.get(self._contact_key(channel, external_user_id))

    def delete_contact_content(
        self, channel: str, external_user_id: str
    ) -> None:
        """R29: borra el contenido personal del hilo rechazado y conserva la evidencia."""
        contact = self.find_channel_contact(channel, external_user_id)
        if contact is None:
            return
        contact_id = contact.id
        self.messages = [
            message for message in self.messages if message.contact_id != contact_id
        ]
        self.events = [
            event for event in self.events if event.contact_id != contact_id
        ]
        self.case_links = {
            case_id: linked
            for case_id, linked in self.case_links.items()
            if linked != contact_id
        }
        self.case_link_created_at = {
            case_id: at
            for case_id, at in self.case_link_created_at.items()
            if case_id in self.case_links
        }
        self.case_profiles = {
            case_id: profile_id
            for case_id, profile_id in self.case_profiles.items()
            if case_id in self.case_links
        }
        self.rag_streaks.pop(contact_id, None)
        self.rag_outcomes = {
            key for key in self.rag_outcomes if key[0] != contact_id
        }
        self.rag_outcome_at = {
            key: at
            for key, at in self.rag_outcome_at.items()
            if key[0] != contact_id
        }
        self.conversation_states.pop(contact_id, None)
        self.contacts = {
            key: stored for key, stored in self.contacts.items() if stored.id != contact_id
        }
        self.contact_created_at.pop(contact_id, None)

    def get_conversation_state(
        self, contact_id: str
    ) -> ConversationState | None:
        stored = self.conversation_states.get(contact_id)
        return stored[0] if stored is not None else None

    def set_conversation_state(
        self, contact_id: str, state: ConversationState, at: datetime
    ) -> None:
        self.conversation_states[contact_id] = (ConversationState(state), at)

    def get_conversation_texts(self) -> ConversationTexts:
        return self.conversation_texts

    def save_conversation_texts(
        self, texts: ConversationTexts, admin_profile_id: str, at: datetime
    ) -> None:
        """R16, R17: versión nueva solo para el campo que cambió."""
        current = self.conversation_texts
        for field in ConversationTexts.__dataclass_fields__:
            value = getattr(texts, field)
            if value == getattr(current, field):
                continue
            version = 1 + max(
                (row.version for row in self.text_versions if row.field == field),
                default=0,
            )
            self.text_versions.append(
                TextVersion(field, version, value, admin_profile_id, at)
            )
        self.conversation_texts = texts

    def purge_personal_data(self, cutoff: datetime, ran_at: datetime) -> dict[str, int]:
        def recent_link(contact_id: str) -> bool:
            return any(
                linked_contact_id == contact_id
                and self.case_link_created_at.get(case_id, cutoff) >= cutoff
                for case_id, linked_contact_id in self.case_links.items()
            )

        def recent_message(contact_id: str) -> bool:
            return any(
                message.contact_id == contact_id and message.at >= cutoff
                for message in self.messages
            )

        inactive_ids = {
            contact.id
            for contact in self.contacts.values()
            if self.contact_created_at.get(contact.id, ran_at) < cutoff
            and not recent_message(contact.id)
            and not recent_link(contact.id)
        }

        deleted_links = [
            case_id
            for case_id, contact_id in self.case_links.items()
            if contact_id in inactive_ids
        ]
        for case_id in deleted_links:
            self.case_links.pop(case_id, None)
            self.case_link_created_at.pop(case_id, None)
            self.case_profiles.pop(case_id, None)

        deleted_contacts = [
            telegram_user_id
            for telegram_user_id, contact in self.contacts.items()
            if contact.id in inactive_ids
        ]
        for telegram_user_id in deleted_contacts:
            self.contacts.pop(telegram_user_id, None)
        for contact_id in inactive_ids:
            self.contact_created_at.pop(contact_id, None)

        kept_messages = [message for message in self.messages if message.at >= cutoff]
        deleted_messages = len(self.messages) - len(kept_messages)
        self.messages = kept_messages

        kept_events = [event for event in self.events if event.at >= cutoff]
        deleted_events = len(self.events) - len(kept_events)
        self.events = kept_events

        kept_tool_calls = [
            call
            for call in self.tool_calls
            if call.at >= cutoff and call.contact_id not in inactive_ids
        ]
        deleted_tool_calls = len(self.tool_calls) - len(kept_tool_calls)
        self.tool_calls = kept_tool_calls

        expired_outcomes = [
            key
            for key in self.rag_outcomes
            if key[0] in inactive_ids
            or self.rag_outcome_at.get(key, ran_at) < cutoff
        ]
        for key in expired_outcomes:
            self.rag_outcomes.discard(key)
            self.rag_outcome_at.pop(key, None)

        expired_streaks = [
            contact_id for contact_id in self.rag_streaks if contact_id in inactive_ids
        ]
        for contact_id in expired_streaks:
            self.rag_streaks.pop(contact_id, None)

        expired_states = [
            contact_id
            for contact_id in self.conversation_states
            if contact_id in inactive_ids
        ]
        for contact_id in expired_states:
            self.conversation_states.pop(contact_id, None)

        expired_summaries = [
            key
            for key, row in self.conversation_summaries.items()
            if row.updated_at < cutoff
        ]
        for key in expired_summaries:
            self.conversation_summaries.pop(key, None)

        counts = {
            "messages": deleted_messages,
            "events": deleted_events,
            "contacts": len(deleted_contacts),
            "case_links": len(deleted_links),
            "auto_handover_outcomes": len(expired_outcomes),
            "auto_handover_streaks": len(expired_streaks),
            "tool_calls": deleted_tool_calls,
            "conversation_summaries": len(expired_summaries),
        }
        self.privacy_purge_runs.append(
            {"ran_at": ran_at, "cutoff": cutoff, "counts": dict(counts)}
        )
        return counts

    def create_client_credential(
        self,
        username: str,
        password_hash: str,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
    ) -> Profile:
        normalized = username.lower()
        with self._identity_lock:
            if any(
                profile.username == normalized
                for profile in self.profiles.values()
            ):
                raise UsernameTaken("El nombre de usuario ya existe.")
            profile_id = f"p{len(self.profiles) + 1}"
            self.profiles[profile_id] = StoredProfile(
                id=profile_id,
                username=normalized,
                role="cliente",
                password_hash=password_hash,
            )
            self.client_credentials[profile_id] = ClientCredential(
                profile_id=profile_id,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        return Profile(id=profile_id, username=normalized, role="cliente")

    def get_client_credential(self, profile_id: str) -> ClientCredential | None:
        return self.client_credentials.get(profile_id)

    def get_client_credentials_by_username(
        self, username: str
    ) -> tuple[Profile, str, ClientCredential | None] | None:
        normalized = username.lower()
        for stored in self.profiles.values():
            if stored.username == normalized:
                return (
                    Profile(
                        id=stored.id,
                        username=stored.username,
                        role=stored.role,
                        telegram_user_id=stored.telegram_user_id,
                    ),
                    stored.password_hash,
                    self.client_credentials.get(stored.id),
                )
        return None

    def renew_client_credential(
        self, profile_id: str, valid_until: datetime, now: datetime
    ) -> bool:
        with self._identity_lock:
            credential = self.client_credentials.get(profile_id)
            if credential is None or credential.revoked_at is not None:
                return False
            credential.valid_until = valid_until
            return True

    def revoke_client_credential(self, profile_id: str, now: datetime) -> bool:
        with self._identity_lock:
            credential = self.client_credentials.get(profile_id)
            if credential is None:
                return False
            if credential.revoked_at is None:
                credential.revoked_at = now
            return True

    def add_login_link(
        self,
        token_hash: str,
        contact_id: str,
        channel: str,
        external_chat_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        with self._identity_lock:
            for key, link in list(self.login_links.items()):
                if link.contact_id != contact_id:
                    continue
                if link.used_at is not None or link.expires_at <= now:
                    del self.login_links[key]
            for link in self.login_links.values():
                if link.contact_id == contact_id and link.used_at is None:
                    link.used_at = now
            self.login_links[token_hash] = LoginLink(
                token_hash=token_hash,
                contact_id=contact_id,
                channel=channel,
                external_chat_id=external_chat_id,
                expires_at=expires_at,
            )

    def get_login_link(self, token_hash: str, now: datetime) -> LoginLink | None:
        link = self.login_links.get(token_hash)
        if link is None or link.used_at is not None or link.expires_at <= now:
            return None
        return link

    def start_client_session(
        self, token_hash: str, profile_id: str, session_id: str, now: datetime
    ) -> str:
        with self._identity_lock:
            link = self.login_links.get(token_hash)
            if link is None or link.used_at is not None or link.expires_at <= now:
                return "invalid_link"
            if (
                self.get_active_session_by_profile(profile_id) is not None
                or self.get_active_session_by_contact(link.contact_id) is not None
            ):
                return "conflict"
            link.used_at = now
            self.client_sessions[session_id] = ClientSession(
                id=session_id,
                profile_id=profile_id,
                contact_id=link.contact_id,
                started_at=now,
                last_activity_at=now,
            )
            return "ok"

    def get_active_session_by_contact(self, contact_id: str) -> ClientSession | None:
        for session in self.client_sessions.values():
            if session.contact_id == contact_id and session.ended_at is None:
                return session
        return None

    def get_active_session_by_profile(self, profile_id: str) -> ClientSession | None:
        for session in self.client_sessions.values():
            if session.profile_id == profile_id and session.ended_at is None:
                return session
        return None

    def touch_client_session(self, session_id: str, now: datetime) -> None:
        session = self.client_sessions.get(session_id)
        if session is not None and session.ended_at is None:
            session.last_activity_at = now

    def end_client_session(
        self, session_id: str, reason: str, now: datetime
    ) -> bool:
        with self._identity_lock:
            session = self.client_sessions.get(session_id)
            if session is None or session.ended_at is not None:
                return False
            session.ended_at = now
            session.end_reason = reason
            return True

    def count_identity_login_failures(
        self, username: str, ip: str, since: datetime
    ) -> tuple[int, int]:
        by_username = sum(
            1
            for failure in self.identity_login_attempts
            if failure.username == username and failure.at > since
        )
        by_ip = sum(
            1
            for failure in self.identity_login_attempts
            if failure.ip == ip and failure.at > since
        )
        return by_username, by_ip

    def record_identity_login_failure(
        self, username: str, ip: str, now: datetime, prune_before: datetime
    ) -> None:
        self.identity_login_attempts.append(
            StoredLoginFailure(username=username, ip=ip, at=now)
        )
        self.identity_login_attempts = [
            failure
            for failure in self.identity_login_attempts
            if failure.at >= prune_before
        ]

    def clear_identity_login_failures(self, username: str) -> None:
        self.identity_login_attempts = [
            failure
            for failure in self.identity_login_attempts
            if failure.username != username
        ]

    def add_identity_audit(
        self,
        profile_id: str | None,
        contact_id: str | None,
        action: str,
        reason: str,
        at: datetime,
    ) -> None:
        self.identity_audits.append(
            IdentityAudit(
                profile_id=profile_id,
                contact_id=contact_id,
                action=action,
                reason=reason,
                at=at,
            )
        )

    def get_identity_overrides(self) -> dict[str, str]:
        return dict(self.identity_overrides)

    def session_messages(
        self,
        contact_id: str,
        since: datetime,
        until: datetime,
        idle_limit: datetime,
        limit: int,
    ) -> list[tuple[str, str, datetime]]:
        selected = [
            message
            for message in self.messages
            if message.contact_id == contact_id
            and since <= message.at <= until
            and message.at < idle_limit
        ]
        selected.sort(key=lambda message: message.at)
        return [
            (message.role, message.text, message.at) for message in selected[-limit:]
        ]

    def get_client_memory(
        self, profile_id: str
    ) -> tuple[tuple[str, ...], datetime | None]:
        stored = self.client_memory.get(profile_id)
        if stored is None:
            return (), None
        return stored.items, stored.updated_at

    def set_client_memory(
        self,
        profile_id: str,
        items: Sequence[str],
        source_session_id: str,
        now: datetime,
    ) -> None:
        self.client_memory[profile_id] = StoredClientMemory(
            profile_id=profile_id,
            items=tuple(items),
            source_session_id=source_session_id,
            updated_at=now,
        )

    def upsert_conversation_summary(
        self,
        session_id: str,
        profile_id: str,
        contact_id: str,
        channel: str,
        summary: str,
        trigger: str,
        now: datetime,
    ) -> None:
        existing = self.conversation_summaries.get(session_id)
        created_at = existing.created_at if existing is not None else now
        self.conversation_summaries[session_id] = StoredConversationSummary(
            session_id=session_id,
            profile_id=profile_id,
            contact_id=contact_id,
            channel=channel,
            summary=summary,
            trigger=trigger,
            created_at=created_at,
            updated_at=now,
        )

    def list_conversation_summaries(
        self, profile_id: str, limit: int
    ) -> list[SummaryView]:
        rows = [
            row
            for row in self.conversation_summaries.values()
            if row.profile_id == profile_id
        ]
        rows.sort(key=lambda row: (row.updated_at, row.session_id), reverse=True)
        return [
            SummaryView(
                session_id=row.session_id,
                channel=row.channel,
                summary=row.summary,
                trigger=row.trigger,
                updated_at=row.updated_at,
            )
            for row in rows[:limit]
        ]

    def get_suppression_request(
        self, request_id: str
    ) -> "StoredSuppressionRequest | None":
        return self.suppression_requests.get(request_id)

    def execute_suppression(
        self, request_id: str, executed_by: str, idle_minutes: int, now: datetime
    ) -> dict[str, int] | None:
        with self._identity_lock:
            request = self.suppression_requests.get(request_id)
            if request is None or request.status != "pending":
                return None
            sessions = [
                session
                for session in self.client_sessions.values()
                if session.profile_id == request.profile_id
            ]
            windows = [
                (
                    session.contact_id,
                    session_window(
                        session.started_at,
                        session.last_activity_at,
                        session.ended_at,
                        now,
                        idle_minutes,
                    ),
                )
                for session in sessions
            ]
            keep: list[StoredMessage] = []
            deleted_messages = 0
            for message in self.messages:
                if any(
                    message.contact_id == contact_id
                    and in_window(message.at, window)
                    for contact_id, window in windows
                ):
                    deleted_messages += 1
                else:
                    keep.append(message)
            self.messages = keep

            deleted_summaries = sum(
                1
                for row in self.conversation_summaries.values()
                if row.profile_id == request.profile_id
            )
            self.conversation_summaries = {
                key: row
                for key, row in self.conversation_summaries.items()
                if row.profile_id != request.profile_id
            }

            deleted_memory = 1 if self.client_memory.pop(request.profile_id, None) else 0

            counts = {
                "messages": deleted_messages,
                "conversation_summaries": deleted_summaries,
                "client_memory": deleted_memory,
            }
            request.status = "executed"
            request.executed_at = now
            request.executed_by = executed_by
            request.removed_counts = dict(counts)
            return counts

    def get_app_settings(self, prefixes: Sequence[str]) -> dict[str, str]:
        merged = dict(self.identity_overrides)
        merged.update(self._app_settings)
        return {
            key: value
            for key, value in merged.items()
            if any(key.startswith(prefix) for prefix in prefixes)
        }

    def save_app_settings(
        self, upserts: dict[str, str], deletes: Sequence[str]
    ) -> None:
        for key in deletes:
            self._app_settings.pop(key, None)
            if key.startswith("identity."):
                self.identity_overrides.pop(key, None)
        self._app_settings.update(upserts)
        for key, value in upserts.items():
            if key.startswith("identity."):
                self.identity_overrides[key] = value

    def current_text_versions(self) -> dict[str, int]:
        return {
            field: max(
                (row.version for row in self.text_versions if row.field == field),
                default=0,
            )
            for field in ConversationTexts.__dataclass_fields__
            if any(row.field == field for row in self.text_versions)
        }

    def text_history(self, field: str, limit: int) -> list[TextVersion]:
        rows = [row for row in self.text_versions if row.field == field]
        rows.sort(key=lambda row: row.version, reverse=True)
        return rows[:limit]

    def list_client_credentials(self) -> list[ClientCredentialRow]:
        rows: list[ClientCredentialRow] = []
        for stored in self.profiles.values():
            credential = self.client_credentials.get(stored.id)
            if stored.role != "cliente" or credential is None:
                continue
            rows.append(
                ClientCredentialRow(
                    profile=Profile(
                        id=stored.id,
                        username=stored.username,
                        role=stored.role,
                        telegram_user_id=stored.telegram_user_id,
                    ),
                    credential=credential,
                    has_active_session=self.get_active_session_by_profile(stored.id)
                    is not None,
                )
            )
        rows.sort(key=lambda row: row.profile.username)
        return rows

    def current_expiry_notice_status(
        self, profile_id: str, valid_until: datetime
    ) -> str | None:
        row = self.expiry_notices.get((profile_id, valid_until))
        return row["status"] if row is not None else None

    def list_whatsapp_templates(self) -> list[WhatsAppTemplate]:
        return sorted(self.whatsapp_templates.values(), key=lambda item: item.name)

    def create_whatsapp_template(self, template: WhatsAppTemplate) -> None:
        if template.name in self.whatsapp_templates:
            raise TemplateExists("La plantilla ya existe.")
        self.whatsapp_templates[template.name] = template

    def update_whatsapp_template(
        self,
        name: str,
        language: str,
        variables: int,
        body: str,
        actor: str,
        at: datetime,
    ) -> bool:
        current = self.whatsapp_templates.get(name)
        if current is None:
            return False
        self.whatsapp_templates[name] = WhatsAppTemplate(
            name=current.name,
            purpose=current.purpose,
            language=language,
            variables=variables,
            body=body,
            status="draft",
            approved_by=None,
            approved_at=None,
            updated_at=at,
        )
        return True

    def set_whatsapp_template_status(
        self,
        name: str,
        from_status: str,
        to_status: str,
        actor: str,
        at: datetime,
    ) -> bool:
        current = self.whatsapp_templates.get(name)
        if current is None or current.status != from_status:
            return False
        approved_by = current.approved_by
        approved_at = current.approved_at
        if to_status == "approved":
            approved_by = actor
            approved_at = at
        self.whatsapp_templates[name] = WhatsAppTemplate(
            name=current.name,
            purpose=current.purpose,
            language=current.language,
            variables=current.variables,
            body=current.body,
            status=to_status,
            approved_by=approved_by,
            approved_at=approved_at,
            updated_at=at,
        )
        return True

    def list_expiring_credentials(
        self, now: datetime, horizon: datetime
    ) -> list[ExpiringCredential]:
        rows = [
            ExpiringCredential(credential.profile_id, credential.valid_until)
            for credential in self.client_credentials.values()
            if credential.revoked_at is None
            and credential.valid_from <= now < credential.valid_until <= horizon
        ]
        rows.sort(key=lambda row: (row.valid_until, row.profile_id))
        return rows

    def last_client_contact(self, profile_id: str) -> Contact | None:
        sessions = [
            session
            for session in self.client_sessions.values()
            if session.profile_id == profile_id
        ]
        sessions.sort(
            key=lambda session: (session.last_activity_at, session.id), reverse=True
        )
        for session in sessions:
            contact = self.get_contact(session.contact_id)
            if contact is not None:
                return contact
        return None

    def claim_expiry_notice(
        self,
        profile_id: str,
        valid_until: datetime,
        now: datetime,
        max_attempts: int,
    ) -> bool:
        with self._expiry_lock:
            key = (profile_id, valid_until)
            row = self.expiry_notices.get(key)
            if row is None:
                self.expiry_notices[key] = {
                    "status": "sending",
                    "method": None,
                    "attempts": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                return True
            if row["status"] == "failed" and row["attempts"] < max_attempts:
                row["status"] = "sending"
                row["attempts"] += 1
                row["updated_at"] = now
                return True
            return False

    def finish_expiry_notice(
        self,
        profile_id: str,
        valid_until: datetime,
        status: str,
        method: str,
        now: datetime,
    ) -> None:
        with self._expiry_lock:
            row = self.expiry_notices.setdefault(
                (profile_id, valid_until),
                {
                    "status": "sending",
                    "method": None,
                    "attempts": 1,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            row["status"] = status
            row["method"] = method
            row["updated_at"] = now

    def case_first_responses(
        self, since: datetime, until: datetime
    ) -> list[tuple[datetime, datetime | None]]:
        rows: list[tuple[datetime, datetime | None]] = []
        for case_id, contact_id in self.case_links.items():
            created_at = self.case_link_created_at.get(case_id)
            if created_at is None or created_at < since or created_at >= until:
                continue
            replies = [
                message.at
                for message in self.messages
                if message.contact_id == contact_id
                and message.role == "advisor"
                and message.at >= created_at
            ]
            rows.append((created_at, min(replies) if replies else None))
        rows.sort(key=lambda row: row[0])
        return rows

    def advisor_reply_contacts(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, int]]:
        contacts_by_ref: dict[str, set[str]] = {}
        for event in self.events:
            if event.type != "advisor_reply" or event.at < since or event.at >= until:
                continue
            if not event.reason.startswith("advisor:"):
                continue
            ref = event.reason.split(":", 1)[1]
            contacts_by_ref.setdefault(ref, set()).add(event.contact_id)
        rows = [(ref, len(contacts)) for ref, contacts in contacts_by_ref.items()]
        rows.sort(key=lambda row: (-row[1], row[0]))
        return rows

    def event_reason_counts(
        self, event_type: str, since: datetime, until: datetime
    ) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for event in self.events:
            if event.type != event_type or event.at < since or event.at >= until:
                continue
            counts[event.reason] = counts.get(event.reason, 0) + 1
        rows = list(counts.items())
        rows.sort(key=lambda row: (-row[1], row[0]))
        return rows

    def count_events(
        self, types: tuple[str, ...], since: datetime, until: datetime
    ) -> int:
        return sum(
            1
            for event in self.events
            if event.type in types and since <= event.at < until
        )

    def unanswered_samples(
        self, since: datetime, until: datetime, limit: int
    ) -> list[tuple[datetime, str]]:
        selected = [
            event
            for event in self.events
            if event.type in ("no_results", "invalid_answer")
            and since <= event.at < until
        ]
        selected.sort(key=lambda event: event.at, reverse=True)
        samples: list[tuple[datetime, str]] = []
        for event in selected[:limit]:
            candidates = [
                message
                for message in self.messages
                if message.contact_id == event.contact_id
                and message.role == "user"
                and message.at <= event.at
            ]
            if not candidates:
                continue
            last = max(candidates, key=lambda message: message.at)
            samples.append((event.at, last.text))
        return samples


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS contacts ("
    "id TEXT PRIMARY KEY, channel TEXT NOT NULL, "
    "external_user_id TEXT, external_chat_id TEXT, "
    "telegram_user_id BIGINT UNIQUE, "
    "chat_id BIGINT, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS messages ("
    "id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, role TEXT NOT NULL, "
    "text TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS events ("
    "id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, type TEXT NOT NULL, "
    "reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS tool_calls ("
    "id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, profile_id TEXT, "
    "state TEXT NOT NULL, tool TEXT NOT NULL, origin TEXT NOT NULL, "
    "decision TEXT NOT NULL, result TEXT NOT NULL, args_sha256 TEXT NOT NULL, "
    "detail TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS suppression_requests ("
    "id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, contact_id TEXT NOT NULL, "
    "channel TEXT NOT NULL, status TEXT NOT NULL, "
    "case_id TEXT, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS processed_messages ("
    "channel TEXT NOT NULL, external_message_id TEXT NOT NULL, "
    "PRIMARY KEY (channel, external_message_id))",
    "CREATE TABLE IF NOT EXISTS processed_updates ("
    "update_id BIGINT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS case_links ("
    "case_id TEXT PRIMARY KEY, contact_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS auto_handover_outcomes ("
    "contact_id TEXT NOT NULL, update_id BIGINT NOT NULL, outcome TEXT NOT NULL, "
    "at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "PRIMARY KEY (contact_id, update_id))",
    "CREATE TABLE IF NOT EXISTS auto_handover_streaks ("
    "contact_id TEXT PRIMARY KEY, failure_count INTEGER NOT NULL, "
    "state TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS profiles ("
    "id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, role TEXT NOT NULL, "
    "password_hash TEXT NOT NULL, "
    "telegram_user_id BIGINT UNIQUE, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS link_tokens ("
    "token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), "
    "expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ)",
    "CREATE TABLE IF NOT EXISTS admin_sessions ("
    "token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), "
    "csrf_token TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS admin_login_attempts ("
    "id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL, "
    "at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS query_categories ("
    "id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, "
    "keywords TEXT NOT NULL, active BOOLEAN NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS app_settings ("
    "key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS db_query_audit ("
    "id BIGSERIAL PRIMARY KEY, profile_id TEXT, telegram_user_id BIGINT NOT NULL, "
    "status TEXT NOT NULL, views TEXT NOT NULL, row_count INTEGER NOT NULL, "
    "sql_sha256 TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS privacy_consents ("
    "id BIGSERIAL PRIMARY KEY, channel TEXT NOT NULL, "
    "external_user_id TEXT, telegram_user_id BIGINT, "
    "notice_version TEXT NOT NULL, notice_sha256 TEXT NOT NULL, "
    "accepted_at TIMESTAMPTZ, result TEXT, evidence_type TEXT, "
    "external_message_id TEXT, button_id TEXT, occurred_at TIMESTAMPTZ)",
    "CREATE TABLE IF NOT EXISTS conversation_states ("
    "contact_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS privacy_purge_runs ("
    "id BIGSERIAL PRIMARY KEY, ran_at TIMESTAMPTZ NOT NULL, "
    "cutoff TIMESTAMPTZ NOT NULL, counts JSONB NOT NULL)",
    "CREATE TABLE IF NOT EXISTS client_credentials ("
    "profile_id TEXT PRIMARY KEY REFERENCES profiles(id), "
    "valid_from TIMESTAMPTZ NOT NULL, valid_until TIMESTAMPTZ NOT NULL, "
    "revoked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS login_links ("
    "token_hash TEXT PRIMARY KEY, contact_id TEXT NOT NULL, "
    "channel TEXT NOT NULL, external_chat_id TEXT NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL, "
    "used_at TIMESTAMPTZ)",
    "CREATE TABLE IF NOT EXISTS client_sessions ("
    "id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), "
    "contact_id TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL, "
    "last_activity_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ, "
    "end_reason TEXT)",
    "CREATE TABLE IF NOT EXISTS identity_login_attempts ("
    "id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL, "
    "at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS identity_audit ("
    "id BIGSERIAL PRIMARY KEY, profile_id TEXT, contact_id TEXT, "
    "action TEXT NOT NULL, reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS client_memory ("
    "profile_id TEXT PRIMARY KEY, items JSONB NOT NULL, source_session_id TEXT, "
    "updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS conversation_summaries ("
    "session_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, contact_id TEXT NOT NULL, "
    "channel TEXT NOT NULL, summary TEXT NOT NULL, trigger TEXT NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS advisor_presence ("
    "profile_id TEXT PRIMARY KEY, status TEXT NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS panel_audit ("
    "id BIGSERIAL PRIMARY KEY, actor_profile_id TEXT NOT NULL, "
    "actor_role TEXT NOT NULL, action TEXT NOT NULL, case_id TEXT, request_id TEXT, "
    "target TEXT, result TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS text_versions ("
    "id BIGSERIAL PRIMARY KEY, field TEXT NOT NULL, version INTEGER NOT NULL, "
    "value TEXT NOT NULL, created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "UNIQUE (field, version))",
    "CREATE TABLE IF NOT EXISTS whatsapp_templates ("
    "name TEXT PRIMARY KEY, purpose TEXT NOT NULL, language TEXT NOT NULL, "
    "variables INTEGER NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, "
    "approved_by TEXT, approved_at TIMESTAMPTZ, "
    "updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS credential_expiry_notices ("
    "profile_id TEXT NOT NULL, valid_until TIMESTAMPTZ NOT NULL, "
    "status TEXT NOT NULL, method TEXT, attempts INTEGER NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, "
    "PRIMARY KEY (profile_id, valid_until))",
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS admin_login_attempts_user_at "
    "ON admin_login_attempts (username, at)",
    "CREATE INDEX IF NOT EXISTS admin_login_attempts_ip_at "
    "ON admin_login_attempts (ip, at)",
    "CREATE INDEX IF NOT EXISTS privacy_consents_user_version "
    "ON privacy_consents (telegram_user_id, notice_version)",
    "CREATE UNIQUE INDEX IF NOT EXISTS client_sessions_one_active_profile "
    "ON client_sessions (profile_id) WHERE ended_at IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS client_sessions_one_active_contact "
    "ON client_sessions (contact_id) WHERE ended_at IS NULL",
    "CREATE INDEX IF NOT EXISTS login_links_contact "
    "ON login_links (contact_id)",
    "CREATE INDEX IF NOT EXISTS identity_login_attempts_user_at "
    "ON identity_login_attempts (username, at)",
    "CREATE INDEX IF NOT EXISTS identity_login_attempts_ip_at "
    "ON identity_login_attempts (ip, at)",
    "CREATE INDEX IF NOT EXISTS tool_calls_at_idx ON tool_calls (at)",
    "CREATE INDEX IF NOT EXISTS tool_calls_contact_idx ON tool_calls (contact_id)",
    "CREATE INDEX IF NOT EXISTS conversation_summaries_profile "
    "ON conversation_summaries (profile_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS conversation_summaries_updated "
    "ON conversation_summaries (updated_at)",
    "CREATE INDEX IF NOT EXISTS client_sessions_profile "
    "ON client_sessions (profile_id)",
    "CREATE INDEX IF NOT EXISTS panel_audit_at ON panel_audit (at)",
    "CREATE INDEX IF NOT EXISTS suppression_requests_status_created "
    "ON suppression_requests (status, created_at)",
    "CREATE INDEX IF NOT EXISTS whatsapp_templates_purpose "
    "ON whatsapp_templates (purpose, status)",
    "CREATE INDEX IF NOT EXISTS events_type_at ON events (type, at)",
    "CREATE INDEX IF NOT EXISTS case_links_created ON case_links (created_at)",
)

# Migración aditiva e idempotente para instalaciones anteriores a #36. Se ejecuta
# después de `_SCHEMA`/`_INDEXES` y nunca cambia ids, mensajes, casos ni fechas.
_MIGRATIONS = (
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS channel TEXT",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS external_user_id TEXT",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS external_chat_id TEXT",
    "ALTER TABLE contacts ALTER COLUMN telegram_user_id DROP NOT NULL",
    "ALTER TABLE contacts ALTER COLUMN chat_id DROP NOT NULL",
    "UPDATE contacts SET channel = 'telegram' WHERE channel IS NULL",
    "UPDATE contacts SET external_user_id = CAST(telegram_user_id AS TEXT) "
    "WHERE external_user_id IS NULL AND telegram_user_id IS NOT NULL",
    "UPDATE contacts SET external_chat_id = CAST(chat_id AS TEXT) "
    "WHERE external_chat_id IS NULL AND chat_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS contacts_channel_external_user "
    "ON contacts (channel, external_user_id)",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS channel TEXT",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS external_user_id TEXT",
    "ALTER TABLE privacy_consents ALTER COLUMN telegram_user_id DROP NOT NULL",
    "UPDATE privacy_consents SET channel = 'telegram' WHERE channel IS NULL",
    "UPDATE privacy_consents SET external_user_id = CAST(telegram_user_id AS TEXT) "
    "WHERE external_user_id IS NULL AND telegram_user_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS privacy_consents_channel_user_version "
    "ON privacy_consents (channel, external_user_id, notice_version)",
    "ALTER TABLE privacy_consents ALTER COLUMN accepted_at DROP NOT NULL",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS result TEXT",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS evidence_type TEXT",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS external_message_id TEXT",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS button_id TEXT",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ",
    "UPDATE privacy_consents SET result = 'accepted' WHERE result IS NULL",
    "UPDATE privacy_consents SET evidence_type = 'legacy' WHERE evidence_type IS NULL",
    "UPDATE privacy_consents SET occurred_at = accepted_at "
    "WHERE occurred_at IS NULL AND accepted_at IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS suppression_requests_one_pending "
    "ON suppression_requests (profile_id) WHERE status = 'pending'",
    "ALTER TABLE case_links ADD COLUMN IF NOT EXISTS profile_id TEXT",
    "ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ",
    "ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS executed_by TEXT",
    "ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS removed_counts JSONB",
    "ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS result_note TEXT",
    "ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS notification_result TEXT",
)


_UNIQUE_VIOLATION_SQLSTATE = "23505"


def _is_unique_violation(error: BaseException) -> bool:
    """Detecta un 23505 de pg8000 (`args[0]` es dict) o de psycopg (`sqlstate`)."""
    sqlstate = getattr(error, "sqlstate", None) or getattr(error, "pgcode", None)
    if sqlstate == _UNIQUE_VIOLATION_SQLSTATE:
        return True
    if error.args and isinstance(error.args[0], dict):
        return error.args[0].get("C") == _UNIQUE_VIOLATION_SQLSTATE
    return False


def _pg_connect(database_url: str) -> Any:
    import pg8000.dbapi

    parsed = urlparse(database_url)
    return pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/").lstrip("/"),
    )


def _row_to_suppression(row: tuple) -> StoredSuppressionRequest:
    counts = row[9]
    if isinstance(counts, str):
        counts = json.loads(counts)
    return StoredSuppressionRequest(
        id=row[0],
        profile_id=row[1],
        contact_id=row[2],
        channel=row[3],
        status=row[4],
        case_id=row[5],
        created_at=row[6],
        executed_at=row[7],
        executed_by=row[8],
        removed_counts=counts,
        result_note=row[10],
        notification_result=row[11],
    )


class PostgresRepository:
    """SQL siempre parametrizado (%s); la conexión se abre en el primer uso.

    Un threading.Lock serializa todo el uso de la conexión compartida (#18).
    """

    def __init__(
        self,
        database_url: str,
        connect: Callable[[], Any] | None = None,
        new_id: Callable[[], str] | None = None,
        run_migrations: bool | None = None,
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        # En producción (conexión real) se aplica el esquema y la migración; las
        # conexiones falsas de los tests pueden activarla para probar el DDL.
        self._run_migrations = (
            connect is None if run_migrations is None else run_migrations
        )
        self._conn: Any = None
        self._lock = threading.Lock()

    def _connection(self) -> Any:
        if self._conn is None:
            conn = self._connect()
            cur = conn.cursor()
            for statement in _SCHEMA:
                cur.execute(statement)
            for statement in _INDEXES:
                cur.execute(statement)
            if self._run_migrations:
                for statement in _MIGRATIONS:
                    cur.execute(statement)
            conn.commit()
            self._conn = conn
        return self._conn

    def ensure_schema(self) -> None:
        """Crea el esquema y aplica la migración idempotente de #36."""
        self._connection()

    def _run(self, sql: str, params: tuple, fetch: bool = False) -> list:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                rows = list(cur.fetchall()) if fetch else []
                conn.commit()
                return rows
            except Exception:
                conn.rollback()
                raise

    def mark_message_if_new(
        self, channel: str, external_message_id: str
    ) -> bool:
        """R5, R6: la clave compuesta; una sola sentencia por mensaje.

        Las filas históricas de `processed_updates` se consultan dentro de la
        misma sentencia, así que no hace falta migrarlas al inicializar ni
        añaden consultas a operaciones no relacionadas.
        """
        legacy_update_id: int | None = None
        if channel == "telegram":
            try:
                legacy_update_id = int(external_message_id)
            except ValueError:
                legacy_update_id = None
        if legacy_update_id is None:
            sql = (
                "INSERT INTO processed_messages (channel, external_message_id) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING "
                "RETURNING external_message_id"
            )
            params = (channel, external_message_id)
        else:
            sql = (
                "INSERT INTO processed_messages (channel, external_message_id) "
                "SELECT %s, %s WHERE NOT EXISTS ("
                "SELECT 1 FROM processed_updates WHERE update_id = %s"
                ") ON CONFLICT DO NOTHING RETURNING external_message_id"
            )
            params = (channel, external_message_id, legacy_update_id)
        rows = self._run(sql, params, fetch=True)
        return bool(rows)

    def mark_update_if_new(self, update_id: int) -> bool:
        """R22: el endpoint legacy guarda solo `update_id` en `processed_updates`."""
        sql = (
            "INSERT INTO processed_updates (update_id) "
            "SELECT %s WHERE NOT EXISTS ("
            "SELECT 1 FROM processed_messages "
            "WHERE channel = %s AND external_message_id = %s"
            ") ON CONFLICT DO NOTHING RETURNING update_id"
        )
        params = (update_id, "telegram", str(update_id))
        rows = self._run(sql, params, fetch=True)
        return bool(rows)

    def get_or_create_contact(
        self, telegram_user_id: int, chat_id: int, now: datetime
    ) -> Contact:
        self._run(
            "INSERT INTO contacts "
            "(id, channel, external_user_id, external_chat_id, telegram_user_id, "
            "chat_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (telegram_user_id) DO NOTHING",
            (
                self._new_id(),
                "telegram",
                str(telegram_user_id),
                str(chat_id),
                telegram_user_id,
                chat_id,
                now,
            ),
        )
        rows = self._run(
            "SELECT id, telegram_user_id, chat_id FROM contacts "
            "WHERE telegram_user_id = %s",
            (telegram_user_id,),
            fetch=True,
        )
        row = rows[0]
        return Contact(
            id=row[0],
            channel="telegram",
            external_user_id=str(row[1]),
            external_chat_id=str(row[2]),
            telegram_user_id=row[1],
            chat_id=row[2],
        )

    def get_or_create_channel_contact(
        self,
        channel: str,
        external_user_id: str,
        external_chat_id: str,
        now: datetime,
    ) -> Contact:
        telegram_user_id = (
            _telegram_value(external_user_id) if channel == "telegram" else None
        )
        chat_id = (
            _telegram_value(external_chat_id) if channel == "telegram" else None
        )
        self._run(
            "INSERT INTO contacts "
            "(id, channel, external_user_id, external_chat_id, telegram_user_id, "
            "chat_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (channel, external_user_id) DO NOTHING",
            (
                self._new_id(),
                channel,
                external_user_id,
                external_chat_id,
                telegram_user_id,
                chat_id,
                now,
            ),
        )
        rows = self._run(
            "SELECT id, channel, external_user_id, external_chat_id, "
            "telegram_user_id, chat_id FROM contacts "
            "WHERE channel = %s AND external_user_id = %s",
            (channel, external_user_id),
            fetch=True,
        )
        row = rows[0]
        return Contact(
            id=row[0],
            channel=row[1],
            external_user_id=row[2],
            external_chat_id=row[3],
            telegram_user_id=row[4],
            chat_id=row[5],
        )

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None:
        self._run(
            "INSERT INTO messages (contact_id, role, text, at) VALUES (%s, %s, %s, %s)",
            (contact_id, role, text, at),
        )

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]:
        rows = self._run(
            "SELECT role, text, at FROM messages WHERE contact_id = %s "
            "ORDER BY id DESC LIMIT %s",
            (contact_id, limit),
            fetch=True,
        )
        return [LastMessage(role=r[0], text=r[1], at=r[2]) for r in reversed(rows)]

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None:
        self._run(
            "INSERT INTO events (contact_id, type, reason, at) VALUES (%s, %s, %s, %s)",
            (contact_id, type, reason, at),
        )

    def link_case(
        self,
        case_id: str,
        contact_id: str,
        at: datetime,
        profile_id: str | None = None,
    ) -> None:
        self._run(
            "INSERT INTO case_links (case_id, contact_id, created_at, profile_id) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (case_id) DO NOTHING",
            (case_id, contact_id, at, profile_id),
        )

    def get_case_profile(self, case_id: str) -> str | None:
        rows = self._run(
            "SELECT profile_id FROM case_links WHERE case_id = %s",
            (case_id,),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def get_case_contact(self, case_id: str) -> Contact | None:
        rows = self._run(
            "SELECT c.id, c.channel, c.external_user_id, c.external_chat_id, "
            "c.telegram_user_id, c.chat_id FROM case_links l "
            "JOIN contacts c ON c.id = l.contact_id WHERE l.case_id = %s",
            (case_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Contact(
            id=row[0],
            channel=row[1],
            external_user_id=row[2],
            external_chat_id=row[3],
            telegram_user_id=row[4],
            chat_id=row[5],
        )

    def get_case_link(self, case_id: str) -> CaseLink | None:
        rows = self._run(
            "SELECT l.case_id, l.profile_id, l.created_at, c.id, c.channel, "
            "c.external_user_id, c.external_chat_id, c.telegram_user_id, c.chat_id "
            "FROM case_links l JOIN contacts c ON c.id = l.contact_id "
            "WHERE l.case_id = %s",
            (case_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        contact = Contact(
            id=row[3],
            channel=row[4],
            external_user_id=row[5],
            external_chat_id=row[6],
            telegram_user_id=row[7],
            chat_id=row[8],
        )
        return CaseLink(
            case_id=row[0], contact=contact, profile_id=row[1], created_at=row[2]
        )

    def case_activity(
        self, contact_id: str, since: datetime
    ) -> tuple[datetime | None, datetime | None]:
        rows = self._run(
            "SELECT MAX(at) FILTER (WHERE role = 'user'), "
            "MAX(at) FILTER (WHERE role = 'advisor') "
            "FROM messages WHERE contact_id = %s AND at >= %s",
            (contact_id, since),
            fetch=True,
        )
        row = rows[0]
        return row[0], row[1]

    def last_user_message_at(self, contact_id: str) -> datetime | None:
        rows = self._run(
            "SELECT MAX(at) FROM messages WHERE contact_id = %s AND role = 'user'",
            (contact_id,),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def case_messages(
        self, contact_id: str, since: datetime, limit: int
    ) -> list[tuple[str, str, datetime]]:
        rows = self._run(
            "SELECT role, text, at FROM ("
            "SELECT role, text, at, id FROM messages "
            "WHERE contact_id = %s AND at >= %s ORDER BY at DESC, id DESC LIMIT %s"
            ") AS recent ORDER BY at ASC, id ASC",
            (contact_id, since, limit),
            fetch=True,
        )
        return [(row[0], row[1], row[2]) for row in rows]

    def foreign_session_windows(
        self, contact_id: str, profile_id: str | None, idle_minutes: int, now: datetime
    ) -> list[tuple[datetime, datetime, datetime]]:
        rows = self._run(
            "SELECT profile_id, started_at, last_activity_at, ended_at "
            "FROM client_sessions WHERE contact_id = %s "
            "AND (%s IS NULL OR profile_id <> %s)",
            (contact_id, profile_id, profile_id),
            fetch=True,
        )
        return [
            session_window(row[1], row[2], row[3], now, idle_minutes) for row in rows
        ]

    def last_privacy_decision(
        self, channel: str, external_user_id: str
    ) -> tuple[str, str, datetime | None] | None:
        rows = self._run(
            "SELECT result, notice_version, COALESCE(occurred_at, accepted_at) "
            "FROM privacy_consents WHERE channel = %s AND external_user_id = %s "
            "ORDER BY occurred_at DESC NULLS LAST, id DESC LIMIT 1",
            (channel, external_user_id),
            fetch=True,
        )
        if not rows:
            return None
        return rows[0][0], rows[0][1], rows[0][2]

    def set_advisor_presence(
        self, profile_id: str, status: str, now: datetime
    ) -> None:
        self._run(
            "INSERT INTO advisor_presence "
            "(profile_id, status, updated_at, last_seen_at) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (profile_id) DO UPDATE SET status = EXCLUDED.status, "
            "updated_at = EXCLUDED.updated_at, last_seen_at = EXCLUDED.last_seen_at",
            (profile_id, status, now, now),
        )

    def touch_advisor_presence(self, profile_id: str, now: datetime) -> None:
        self._run(
            "INSERT INTO advisor_presence "
            "(profile_id, status, updated_at, last_seen_at) "
            "VALUES (%s, 'away', %s, %s) ON CONFLICT (profile_id) DO UPDATE "
            "SET last_seen_at = EXCLUDED.last_seen_at",
            (profile_id, now, now),
        )

    def get_advisor_presence(
        self, profile_ids: Sequence[str]
    ) -> dict[str, tuple[str, datetime]]:
        rows = self._run(
            "SELECT profile_id, status, last_seen_at FROM advisor_presence "
            "WHERE profile_id = ANY(%s)",
            (list(profile_ids),),
            fetch=True,
        )
        return {row[0]: (row[1], row[2]) for row in rows}

    def add_panel_audit(
        self,
        actor_profile_id: str,
        actor_role: str,
        action: str,
        case_id: str | None,
        request_id: str | None,
        target: str | None,
        result: str,
        at: datetime,
    ) -> None:
        self._run(
            "INSERT INTO panel_audit "
            "(actor_profile_id, actor_role, action, case_id, request_id, target, "
            "result, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                actor_profile_id,
                actor_role,
                action,
                case_id,
                request_id,
                target,
                result,
                at,
            ),
        )

    def list_panel_audit(self, limit: int) -> list[PanelAudit]:
        rows = self._run(
            "SELECT actor_profile_id, actor_role, action, case_id, request_id, "
            "target, result, at FROM panel_audit ORDER BY at DESC, id DESC LIMIT %s",
            (limit,),
            fetch=True,
        )
        return [
            PanelAudit(
                actor_profile_id=row[0],
                actor_role=row[1],
                action=row[2],
                case_id=row[3],
                request_id=row[4],
                target=row[5],
                result=row[6],
                at=row[7],
            )
            for row in rows
        ]

    def list_suppression_requests(
        self, executed_limit: int
    ) -> list[StoredSuppressionRequest]:
        rows = self._run(
            "SELECT id, profile_id, contact_id, channel, status, case_id, "
            "created_at, executed_at, executed_by, removed_counts, result_note, "
            "notification_result FROM suppression_requests "
            "WHERE status = 'pending' ORDER BY created_at ASC, id ASC",
            (),
            fetch=True,
        )
        executed = self._run(
            "SELECT id, profile_id, contact_id, channel, status, case_id, "
            "created_at, executed_at, executed_by, removed_counts, result_note, "
            "notification_result FROM suppression_requests "
            "WHERE status = 'executed' ORDER BY executed_at DESC NULLS LAST, id DESC "
            "LIMIT %s",
            (executed_limit,),
            fetch=True,
        )
        return [_row_to_suppression(row) for row in rows + executed]

    def set_suppression_outcome(
        self, request_id: str, note: str | None, notification_result: str
    ) -> None:
        self._run(
            "UPDATE suppression_requests SET result_note = %s, "
            "notification_result = %s WHERE id = %s",
            (note, notification_result, request_id),
        )

    def get_contact(self, contact_id: str) -> Contact | None:
        rows = self._run(
            "SELECT id, channel, external_user_id, external_chat_id, "
            "telegram_user_id, chat_id FROM contacts WHERE id = %s",
            (contact_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Contact(
            id=row[0],
            channel=row[1],
            external_user_id=row[2],
            external_chat_id=row[3],
            telegram_user_id=row[4],
            chat_id=row[5],
        )

    def get_contact_last_case(self, contact_id: str) -> str | None:
        rows = self._run(
            "SELECT case_id FROM case_links WHERE contact_id = %s "
            "ORDER BY created_at DESC, case_id DESC LIMIT 1",
            (contact_id,),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def record_rag_outcome(
        self,
        contact_id: str,
        update_id: int,
        outcome: str,
        threshold: int,
        failure_reasons: set[str],
    ) -> bool:
        if outcome not in RAG_OUTCOMES:
            raise ValueError("outcome de RAG no permitido")
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO auto_handover_outcomes "
                    "(contact_id, update_id, outcome) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING RETURNING update_id",
                    (contact_id, update_id, outcome),
                )
                if not list(cur.fetchall()):
                    conn.commit()
                    return False

                should_attempt = False
                if outcome == "rag_answer":
                    failure_count, state = 0, "open"
                else:
                    cur.execute(
                        "SELECT failure_count, state FROM auto_handover_streaks "
                        "WHERE contact_id = %s",
                        (contact_id,),
                    )
                    rows = list(cur.fetchall())
                    previous_count = int(rows[0][0]) if rows else 0
                    previous_state = rows[0][1] if rows else "open"
                    if previous_state == "retry":
                        failure_count = previous_count + (
                            1 if outcome in failure_reasons else 0
                        )
                        state = "pending"
                        should_attempt = True
                    elif outcome not in failure_reasons:
                        conn.commit()
                        return False
                    else:
                        failure_count = previous_count + 1
                        state = previous_state
                        if (
                            previous_state not in ("pending", "handed_over")
                            and failure_count >= threshold
                        ):
                            state = "pending"
                            should_attempt = True

                cur.execute(
                    "INSERT INTO auto_handover_streaks "
                    "(contact_id, failure_count, state) VALUES (%s, %s, %s) "
                    "ON CONFLICT (contact_id) DO UPDATE "
                    "SET failure_count = EXCLUDED.failure_count, "
                    "state = EXCLUDED.state",
                    (contact_id, failure_count, state),
                )
                conn.commit()
                return should_attempt
            except Exception:
                conn.rollback()
                raise

    def reset_rag_streak(self, contact_id: str) -> None:
        self._run(
            "INSERT INTO auto_handover_streaks "
            "(contact_id, failure_count, state) VALUES (%s, %s, %s) "
            "ON CONFLICT (contact_id) DO UPDATE "
            "SET failure_count = EXCLUDED.failure_count, state = EXCLUDED.state",
            (contact_id, 0, "open"),
        )

    def finish_auto_handover(self, contact_id: str, success: bool) -> None:
        self._run(
            "UPDATE auto_handover_streaks SET state = %s WHERE contact_id = %s",
            ("handed_over" if success else "retry", contact_id),
        )

    def create_profile(
        self, username: str, role: str, password_hash: str, now: datetime
    ) -> Profile:
        profile_id = self._new_id()
        rows = self._run(
            "INSERT INTO profiles (id, username, role, password_hash, created_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (username) DO NOTHING RETURNING id",
            (profile_id, username, role, password_hash, now),
            fetch=True,
        )
        if not rows:
            raise UsernameTaken("El nombre de usuario ya existe.")
        return Profile(id=profile_id, username=username, role=role)

    def get_profile(self, profile_id: str) -> Profile | None:
        rows = self._run(
            "SELECT id, username, role, telegram_user_id FROM profiles WHERE id = %s",
            (profile_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Profile(
            id=row[0], username=row[1], role=row[2], telegram_user_id=row[3]
        )

    def get_profile_by_telegram_user_id(
        self, telegram_user_id: int
    ) -> Profile | None:
        rows = self._run(
            "SELECT id, username, role, telegram_user_id FROM profiles "
            "WHERE telegram_user_id = %s",
            (telegram_user_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Profile(
            id=row[0], username=row[1], role=row[2], telegram_user_id=row[3]
        )

    def add_db_query_audit(
        self,
        profile_id: str | None,
        telegram_user_id: int,
        status: str,
        views: str,
        row_count: int,
        sql_sha256: str,
        at: datetime,
    ) -> None:
        self._run(
            "INSERT INTO db_query_audit "
            "(profile_id, telegram_user_id, status, views, row_count, sql_sha256, at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (profile_id, telegram_user_id, status, views, row_count, sql_sha256, at),
        )

    def add_tool_call(
        self,
        contact_id: str,
        profile_id: str | None,
        state: str,
        tool: str,
        origin: str,
        decision: str,
        result: str,
        args_sha256: str,
        detail: str,
        at: datetime,
    ) -> None:
        self._run(
            "INSERT INTO tool_calls "
            "(contact_id, profile_id, state, tool, origin, decision, result, "
            "args_sha256, detail, at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                contact_id,
                profile_id,
                state,
                tool,
                origin,
                decision,
                result,
                args_sha256,
                detail,
                at,
            ),
        )

    def create_or_get_pending_suppression(
        self,
        request_id: str,
        profile_id: str,
        contact_id: str,
        channel: str,
        at: datetime,
    ) -> tuple[str, bool]:
        inserted = self._run(
            "INSERT INTO suppression_requests "
            "(id, profile_id, contact_id, channel, status, case_id, created_at) "
            "VALUES (%s, %s, %s, %s, 'pending', NULL, %s) "
            "ON CONFLICT DO NOTHING RETURNING id",
            (request_id, profile_id, contact_id, channel, at),
            fetch=True,
        )
        if inserted:
            return request_id, True
        rows = self._run(
            "SELECT id FROM suppression_requests "
            "WHERE profile_id = %s AND status = 'pending' LIMIT 1",
            (profile_id,),
            fetch=True,
        )
        return (rows[0][0] if rows else request_id), False

    def set_suppression_case(self, request_id: str, case_id: str) -> None:
        self._run(
            "UPDATE suppression_requests SET case_id = %s WHERE id = %s",
            (case_id, request_id),
        )

    def add_link_token(self, token_hash: str, profile_id: str, expires_at: datetime) -> None:
        self._run(
            "INSERT INTO link_tokens (token_hash, profile_id, expires_at) "
            "VALUES (%s, %s, %s)",
            (token_hash, profile_id, expires_at),
        )

    def get_profile_credentials(self, username: str) -> tuple[Profile, str] | None:
        rows = self._run(
            "SELECT id, username, role, telegram_user_id, password_hash "
            "FROM profiles WHERE username = %s",
            (username,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        profile = Profile(
            id=row[0], username=row[1], role=row[2], telegram_user_id=row[3]
        )
        return profile, row[4]

    def list_profiles(self) -> list[Profile]:
        rows = self._run(
            "SELECT id, username, role, telegram_user_id FROM profiles ORDER BY username",
            (),
            fetch=True,
        )
        return [
            Profile(id=row[0], username=row[1], role=row[2], telegram_user_id=row[3])
            for row in rows
        ]

    def set_role(self, profile_id: str, role: str) -> bool:
        rows = self._run(
            "UPDATE profiles SET role = %s WHERE id = %s AND (%s = 'admin' "
            "OR role <> 'admin' "
            "OR (SELECT count(*) FROM profiles WHERE role = 'admin') > 1) "
            "RETURNING id",
            (role, profile_id, role),
            fetch=True,
        )
        return bool(rows)

    def create_session(
        self, token_hash: str, profile_id: str, csrf_token: str, expires_at: datetime
    ) -> None:
        self._run(
            "INSERT INTO admin_sessions (token_hash, profile_id, csrf_token, expires_at) "
            "VALUES (%s, %s, %s, %s)",
            (token_hash, profile_id, csrf_token, expires_at),
        )

    def get_session(self, token_hash: str, now: datetime) -> AdminSession | None:
        return self.get_session_for_role(token_hash, now, "admin")

    def get_session_for_role(
        self, token_hash: str, now: datetime, role: str
    ) -> AdminSession | None:
        rows = self._run(
            "SELECT s.token_hash, s.profile_id, s.csrf_token, s.expires_at "
            "FROM admin_sessions s JOIN profiles p ON p.id = s.profile_id "
            "WHERE s.token_hash = %s AND s.expires_at > %s AND p.role = %s",
            (token_hash, now, role),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return AdminSession(
            token_hash=row[0], profile_id=row[1], csrf_token=row[2], expires_at=row[3]
        )

    def delete_session(self, token_hash: str) -> None:
        self._run("DELETE FROM admin_sessions WHERE token_hash = %s", (token_hash,))

    def recent_events(self, limit: int) -> list[StoredEvent]:
        rows = self._run(
            "SELECT contact_id, type, reason, at FROM events "
            "ORDER BY at DESC, id DESC LIMIT %s",
            (limit,),
            fetch=True,
        )
        return [
            StoredEvent(contact_id=row[0], type=row[1], reason=row[2], at=row[3])
            for row in rows
        ]

    def count_login_failures(self, username: str, ip: str, since: datetime) -> tuple[int, int]:
        rows = self._run(
            "SELECT "
            "(SELECT count(*) FROM admin_login_attempts WHERE username = %s AND at > %s), "
            "(SELECT count(*) FROM admin_login_attempts WHERE ip = %s AND at > %s)",
            (username, since, ip, since),
            fetch=True,
        )
        row = rows[0]
        return int(row[0]), int(row[1])

    def record_login_failure(
        self, username: str, ip: str, at: datetime, purge_before: datetime
    ) -> None:
        self._run(
            "INSERT INTO admin_login_attempts (username, ip, at) VALUES (%s, %s, %s)",
            (username, ip, at),
        )
        self._run(
            "DELETE FROM admin_login_attempts WHERE at < %s", (purge_before,)
        )

    def clear_login_failures(self, username: str) -> None:
        self._run(
            "DELETE FROM admin_login_attempts WHERE username = %s", (username,)
        )

    def consume_link_token(
        self, token_hash: str, telegram_user_id: int, now: datetime
    ) -> bool:
        try:
            rows = self._run(
                "WITH t AS (UPDATE link_tokens SET used_at = %s "
                "WHERE token_hash = %s AND used_at IS NULL AND expires_at > %s "
                "RETURNING profile_id) "
                "UPDATE profiles SET telegram_user_id = %s FROM t "
                "WHERE profiles.id = t.profile_id RETURNING profiles.id",
                (now, token_hash, now, telegram_user_id),
                fetch=True,
            )
        except Exception:
            # Choque de UNIQUE en telegram_user_id: _run ya hizo rollback y el token
            # queda sin consumir (design §Atomicidad).
            return False
        return bool(rows)

    def get_link_token_role(self, token_hash: str, now: datetime) -> str | None:
        rows = self._run(
            "SELECT p.role FROM link_tokens t JOIN profiles p ON p.id = t.profile_id "
            "WHERE t.token_hash = %s AND t.used_at IS NULL AND t.expires_at > %s",
            (token_hash, now),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def list_categories(self) -> list[Category]:
        rows = self._run(
            "SELECT id, code, name, keywords, active FROM query_categories "
            "ORDER BY code",
            (),
            fetch=True,
        )
        return [
            Category(
                id=row[0],
                code=row[1],
                name=row[2],
                keywords=tuple(row[3].split("\n")) if row[3] else (),
                active=bool(row[4]),
            )
            for row in rows
        ]

    def create_category(self, category: Category, now: datetime) -> bool:
        rows = self._run(
            "INSERT INTO query_categories "
            "(id, code, name, keywords, active, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (code) DO NOTHING RETURNING id",
            (
                category.id,
                category.code,
                category.name,
                "\n".join(category.keywords),
                category.active,
                now,
            ),
            fetch=True,
        )
        return bool(rows)

    def update_category(
        self, category_id: str, name: str, keywords: tuple[str, ...]
    ) -> bool:
        rows = self._run(
            "UPDATE query_categories SET name = %s, keywords = %s "
            "WHERE id = %s RETURNING id",
            (name, "\n".join(keywords), category_id),
            fetch=True,
        )
        return bool(rows)

    def set_category_active(self, category_id: str, active: bool) -> bool:
        rows = self._run(
            "UPDATE query_categories SET active = %s WHERE id = %s RETURNING id",
            (active, category_id),
            fetch=True,
        )
        return bool(rows)

    def get_classifier_threshold(self) -> float | None:
        rows = self._run(
            "SELECT value FROM app_settings WHERE key = %s",
            ("classifier_threshold",),
            fetch=True,
        )
        if not rows:
            return None
        return float(rows[0][0])

    def set_classifier_threshold(self, value: float) -> None:
        self._run(
            "INSERT INTO app_settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            ("classifier_threshold", str(value)),
        )

    def has_privacy_consent(self, telegram_user_id: int, notice_version: str) -> bool:
        return self.has_channel_privacy_consent(
            "telegram", str(telegram_user_id), notice_version
        )

    def has_channel_privacy_consent(
        self, channel: str, external_user_id: str, notice_version: str
    ) -> bool:
        rows = self._run(
            "SELECT 1 FROM privacy_consents "
            "WHERE channel = %s AND external_user_id = %s "
            "AND notice_version = %s AND result = 'accepted' "
            "AND evidence_type = 'button' LIMIT 1",
            (channel, external_user_id, notice_version),
            fetch=True,
        )
        return bool(rows)

    def add_privacy_consent(
        self,
        telegram_user_id: int,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        self.add_channel_privacy_consent(
            "telegram",
            str(telegram_user_id),
            notice_version,
            notice_sha256,
            accepted_at,
        )

    def add_channel_privacy_consent(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        self.add_privacy_decision(
            channel,
            external_user_id,
            notice_version,
            notice_sha256,
            "accepted",
            "",
            "",
            accepted_at,
        )

    def add_privacy_decision(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        result: str,
        external_message_id: str,
        button_id: str,
        at: datetime,
        evidence_type: str = "button",
    ) -> None:
        telegram_user_id = (
            _telegram_value(external_user_id) if channel == "telegram" else None
        )
        self._run(
            "INSERT INTO privacy_consents "
            "(channel, external_user_id, telegram_user_id, notice_version, "
            "notice_sha256, accepted_at, result, evidence_type, "
            "external_message_id, button_id, occurred_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                channel,
                external_user_id,
                telegram_user_id,
                notice_version,
                notice_sha256,
                at if result == "accepted" else None,
                result,
                evidence_type,
                external_message_id,
                button_id,
                at,
            ),
        )

    def last_privacy_result(
        self, channel: str, external_user_id: str
    ) -> str | None:
        rows = self._run(
            "SELECT result FROM privacy_consents "
            "WHERE channel = %s AND external_user_id = %s "
            "ORDER BY occurred_at DESC NULLS LAST, id DESC LIMIT 1",
            (channel, external_user_id),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def find_channel_contact(
        self, channel: str, external_user_id: str
    ) -> Contact | None:
        rows = self._run(
            "SELECT id, channel, external_user_id, external_chat_id, "
            "telegram_user_id, chat_id FROM contacts "
            "WHERE channel = %s AND external_user_id = %s",
            (channel, external_user_id),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Contact(
            id=row[0],
            channel=row[1],
            external_user_id=row[2],
            external_chat_id=row[3],
            telegram_user_id=row[4],
            chat_id=row[5],
        )

    def delete_contact_content(
        self, channel: str, external_user_id: str
    ) -> None:
        """R29: borra el hilo del contacto en una transacción y conserva la evidencia."""
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id FROM contacts WHERE channel = %s AND external_user_id = %s",
                    (channel, external_user_id),
                )
                rows = list(cur.fetchall())
                if not rows:
                    conn.commit()
                    return
                contact_id = rows[0][0]
                cur.execute("DELETE FROM messages WHERE contact_id = %s", (contact_id,))
                cur.execute("DELETE FROM events WHERE contact_id = %s", (contact_id,))
                cur.execute("DELETE FROM case_links WHERE contact_id = %s", (contact_id,))
                cur.execute(
                    "DELETE FROM auto_handover_outcomes WHERE contact_id = %s",
                    (contact_id,),
                )
                cur.execute(
                    "DELETE FROM auto_handover_streaks WHERE contact_id = %s",
                    (contact_id,),
                )
                cur.execute(
                    "DELETE FROM conversation_states WHERE contact_id = %s",
                    (contact_id,),
                )
                cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_conversation_state(
        self, contact_id: str
    ) -> ConversationState | None:
        rows = self._run(
            "SELECT state FROM conversation_states WHERE contact_id = %s",
            (contact_id,),
            fetch=True,
        )
        if not rows:
            return None
        try:
            return ConversationState(rows[0][0])
        except ValueError:
            return None

    def set_conversation_state(
        self, contact_id: str, state: ConversationState, at: datetime
    ) -> None:
        self._run(
            "INSERT INTO conversation_states (contact_id, state, updated_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (contact_id) DO UPDATE "
            "SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at",
            (contact_id, str(state), at),
        )

    def get_conversation_texts(self) -> ConversationTexts:
        rows = self._run(
            "SELECT key, value FROM app_settings WHERE key LIKE %s",
            ("conversation_texts.%",),
            fetch=True,
        )
        return parse_conversation_texts({key: value for key, value in rows})

    def save_conversation_texts(
        self, texts: ConversationTexts, admin_profile_id: str, at: datetime
    ) -> None:
        """R16, R17: versión nueva por campo cambiado, en la misma transacción."""
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT key, value FROM app_settings "
                    "WHERE key LIKE %s",
                    ("conversation_texts.%",),
                )
                current = parse_conversation_texts(
                    {key: value for key, value in cur.fetchall()}
                )
                for key, value in conversation_text_settings(texts).items():
                    field = key.rsplit(".", 1)[1]
                    if value != getattr(current, field):
                        cur.execute(
                            "SELECT COALESCE(MAX(version), 0) + 1 "
                            "FROM text_versions WHERE field = %s",
                            (field,),
                        )
                        version = cur.fetchall()[0][0]
                        cur.execute(
                            "INSERT INTO text_versions "
                            "(field, version, value, created_by, created_at) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (field, version, value, admin_profile_id, at),
                        )
                    cur.execute(
                        "INSERT INTO app_settings (key, value) VALUES (%s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                        (key, value),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def create_client_credential(
        self,
        username: str,
        password_hash: str,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
    ) -> Profile:
        profile_id = self._new_id()
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO profiles (id, username, role, password_hash, created_at) "
                    "VALUES (%s, %s, 'cliente', %s, %s) "
                    "ON CONFLICT (username) DO NOTHING RETURNING id",
                    (profile_id, username.lower(), password_hash, now),
                )
                if not list(cur.fetchall()):
                    conn.rollback()
                    raise UsernameTaken("El nombre de usuario ya existe.")
                cur.execute(
                    "INSERT INTO client_credentials "
                    "(profile_id, valid_from, valid_until, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (profile_id, valid_from, valid_until, now, now),
                )
                conn.commit()
            except UsernameTaken:
                raise
            except Exception:
                conn.rollback()
                raise
        return Profile(id=profile_id, username=username.lower(), role="cliente")

    def get_client_credential(self, profile_id: str) -> ClientCredential | None:
        rows = self._run(
            "SELECT profile_id, valid_from, valid_until, revoked_at "
            "FROM client_credentials WHERE profile_id = %s",
            (profile_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return ClientCredential(
            profile_id=row[0],
            valid_from=row[1],
            valid_until=row[2],
            revoked_at=row[3],
        )

    def get_client_credentials_by_username(
        self, username: str
    ) -> tuple[Profile, str, ClientCredential | None] | None:
        rows = self._run(
            "SELECT p.id, p.username, p.role, p.telegram_user_id, p.password_hash, "
            "c.valid_from, c.valid_until, c.revoked_at "
            "FROM profiles p LEFT JOIN client_credentials c ON c.profile_id = p.id "
            "WHERE p.username = %s",
            (username.lower(),),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        profile = Profile(
            id=row[0], username=row[1], role=row[2], telegram_user_id=row[3]
        )
        credential = None
        if row[5] is not None:
            credential = ClientCredential(
                profile_id=row[0],
                valid_from=row[5],
                valid_until=row[6],
                revoked_at=row[7],
            )
        return profile, row[4], credential

    def renew_client_credential(
        self, profile_id: str, valid_until: datetime, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE client_credentials SET valid_until = %s, updated_at = %s "
            "WHERE profile_id = %s AND revoked_at IS NULL RETURNING profile_id",
            (valid_until, now, profile_id),
            fetch=True,
        )
        return bool(rows)

    def revoke_client_credential(self, profile_id: str, now: datetime) -> bool:
        rows = self._run(
            "UPDATE client_credentials SET revoked_at = COALESCE(revoked_at, %s), "
            "updated_at = %s WHERE profile_id = %s RETURNING profile_id",
            (now, now, profile_id),
            fetch=True,
        )
        return bool(rows)

    def add_login_link(
        self,
        token_hash: str,
        contact_id: str,
        channel: str,
        external_chat_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "DELETE FROM login_links WHERE contact_id = %s "
                    "AND (used_at IS NOT NULL OR expires_at <= %s)",
                    (contact_id, now),
                )
                cur.execute(
                    "UPDATE login_links SET used_at = %s "
                    "WHERE contact_id = %s AND used_at IS NULL",
                    (now, contact_id),
                )
                cur.execute(
                    "INSERT INTO login_links "
                    "(token_hash, contact_id, channel, external_chat_id, "
                    "created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (token_hash, contact_id, channel, external_chat_id, now, expires_at),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_login_link(self, token_hash: str, now: datetime) -> LoginLink | None:
        rows = self._run(
            "SELECT token_hash, contact_id, channel, external_chat_id, expires_at, "
            "used_at FROM login_links WHERE token_hash = %s "
            "AND used_at IS NULL AND expires_at > %s",
            (token_hash, now),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return LoginLink(
            token_hash=row[0],
            contact_id=row[1],
            channel=row[2],
            external_chat_id=row[3],
            expires_at=row[4],
            used_at=row[5],
        )

    def start_client_session(
        self, token_hash: str, profile_id: str, session_id: str, now: datetime
    ) -> str:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "WITH l AS (UPDATE login_links SET used_at = %s "
                    "WHERE token_hash = %s AND used_at IS NULL AND expires_at > %s "
                    "RETURNING contact_id) "
                    "INSERT INTO client_sessions "
                    "(id, profile_id, contact_id, started_at, last_activity_at) "
                    "SELECT %s, %s, l.contact_id, %s, %s FROM l "
                    "RETURNING contact_id",
                    (now, token_hash, now, session_id, profile_id, now, now),
                )
                if not list(cur.fetchall()):
                    conn.commit()
                    return "invalid_link"
                conn.commit()
                return "ok"
            except Exception as error:
                conn.rollback()
                # Solo el índice parcial único significa conflicto; el resto de
                # errores de BD (caída, SQL inválido) se propagan.
                if _is_unique_violation(error):
                    # El token queda sin usar por el rollback.
                    return "conflict"
                raise

    def get_active_session_by_contact(self, contact_id: str) -> ClientSession | None:
        return self._get_active_session("contact_id", contact_id)

    def get_active_session_by_profile(self, profile_id: str) -> ClientSession | None:
        return self._get_active_session("profile_id", profile_id)

    def _get_active_session(self, column: str, value: str) -> ClientSession | None:
        if column not in ("contact_id", "profile_id"):
            raise ValueError("columna de sesión inválida")
        rows = self._run(
            f"SELECT id, profile_id, contact_id, started_at, last_activity_at "
            f"FROM client_sessions WHERE {column} = %s AND ended_at IS NULL",
            (value,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return ClientSession(
            id=row[0],
            profile_id=row[1],
            contact_id=row[2],
            started_at=row[3],
            last_activity_at=row[4],
        )

    def touch_client_session(self, session_id: str, now: datetime) -> None:
        self._run(
            "UPDATE client_sessions SET last_activity_at = %s "
            "WHERE id = %s AND ended_at IS NULL",
            (now, session_id),
        )

    def end_client_session(
        self, session_id: str, reason: str, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE client_sessions SET ended_at = %s, end_reason = %s "
            "WHERE id = %s AND ended_at IS NULL RETURNING id",
            (now, reason, session_id),
            fetch=True,
        )
        return bool(rows)

    def count_identity_login_failures(
        self, username: str, ip: str, since: datetime
    ) -> tuple[int, int]:
        rows = self._run(
            "SELECT "
            "(SELECT count(*) FROM identity_login_attempts "
            "WHERE username = %s AND at > %s), "
            "(SELECT count(*) FROM identity_login_attempts "
            "WHERE ip = %s AND at > %s)",
            (username, since, ip, since),
            fetch=True,
        )
        row = rows[0]
        return int(row[0]), int(row[1])

    def record_identity_login_failure(
        self, username: str, ip: str, now: datetime, prune_before: datetime
    ) -> None:
        self._run(
            "INSERT INTO identity_login_attempts (username, ip, at) "
            "VALUES (%s, %s, %s)",
            (username, ip, now),
        )
        self._run(
            "DELETE FROM identity_login_attempts WHERE at < %s", (prune_before,)
        )

    def clear_identity_login_failures(self, username: str) -> None:
        self._run(
            "DELETE FROM identity_login_attempts WHERE username = %s", (username,)
        )

    def add_identity_audit(
        self,
        profile_id: str | None,
        contact_id: str | None,
        action: str,
        reason: str,
        at: datetime,
    ) -> None:
        self._run(
            "INSERT INTO identity_audit "
            "(profile_id, contact_id, action, reason, at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (profile_id, contact_id, action, reason, at),
        )

    def get_identity_overrides(self) -> dict[str, str]:
        rows = self._run(
            "SELECT key, value FROM app_settings WHERE key LIKE %s",
            ("identity.%",),
            fetch=True,
        )
        return {key: value for key, value in rows}

    def session_messages(
        self,
        contact_id: str,
        since: datetime,
        until: datetime,
        idle_limit: datetime,
        limit: int,
    ) -> list[tuple[str, str, datetime]]:
        rows = self._run(
            "SELECT role, text, at FROM ("
            "SELECT id, role, text, at FROM messages "
            "WHERE contact_id = %s AND at >= %s AND at <= %s AND at < %s "
            "ORDER BY at DESC, id DESC LIMIT %s"
            ") recent ORDER BY at, id",
            (contact_id, since, until, idle_limit, limit),
            fetch=True,
        )
        return [(row[0], row[1], row[2]) for row in rows]

    def get_client_memory(
        self, profile_id: str
    ) -> tuple[tuple[str, ...], datetime | None]:
        rows = self._run(
            "SELECT items, updated_at FROM client_memory WHERE profile_id = %s",
            (profile_id,),
            fetch=True,
        )
        if not rows:
            return (), None
        items, updated_at = rows[0]
        if isinstance(items, str):
            import json as _json

            items = _json.loads(items)
        return tuple(items or ()), updated_at

    def set_client_memory(
        self,
        profile_id: str,
        items: Sequence[str],
        source_session_id: str,
        now: datetime,
    ) -> None:
        self._run(
            "INSERT INTO client_memory "
            "(profile_id, items, source_session_id, updated_at) "
            "VALUES (%s, CAST(%s AS JSONB), %s, %s) "
            "ON CONFLICT (profile_id) DO UPDATE SET "
            "items = EXCLUDED.items, "
            "source_session_id = EXCLUDED.source_session_id, "
            "updated_at = EXCLUDED.updated_at",
            (profile_id, json.dumps(list(items), ensure_ascii=False), source_session_id, now),
        )

    def upsert_conversation_summary(
        self,
        session_id: str,
        profile_id: str,
        contact_id: str,
        channel: str,
        summary: str,
        trigger: str,
        now: datetime,
    ) -> None:
        self._run(
            "INSERT INTO conversation_summaries "
            "(session_id, profile_id, contact_id, channel, summary, trigger, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (session_id) DO UPDATE SET "
            "summary = EXCLUDED.summary, trigger = EXCLUDED.trigger, "
            "updated_at = EXCLUDED.updated_at",
            (session_id, profile_id, contact_id, channel, summary, trigger, now, now),
        )

    def list_conversation_summaries(
        self, profile_id: str, limit: int
    ) -> list[SummaryView]:
        rows = self._run(
            "SELECT session_id, channel, summary, trigger, updated_at "
            "FROM conversation_summaries WHERE profile_id = %s "
            "ORDER BY updated_at DESC, session_id DESC LIMIT %s",
            (profile_id, limit),
            fetch=True,
        )
        return [
            SummaryView(
                session_id=row[0],
                channel=row[1],
                summary=row[2],
                trigger=row[3],
                updated_at=row[4],
            )
            for row in rows
        ]

    def get_suppression_request(
        self, request_id: str
    ) -> "StoredSuppressionRequest | None":
        rows = self._run(
            "SELECT id, profile_id, contact_id, channel, status, case_id, created_at, "
            "executed_at, executed_by, removed_counts, result_note, notification_result "
            "FROM suppression_requests WHERE id = %s",
            (request_id,),
            fetch=True,
        )
        if not rows:
            return None
        return _row_to_suppression(rows[0])

    def execute_suppression(
        self, request_id: str, executed_by: str, idle_minutes: int, now: datetime
    ) -> dict[str, int] | None:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT profile_id FROM suppression_requests "
                    "WHERE id = %s AND status = 'pending' FOR UPDATE",
                    (request_id,),
                )
                rows = list(cur.fetchall())
                if not rows:
                    conn.commit()
                    return None
                profile_id = rows[0][0]

                cur.execute(
                    "SELECT contact_id, started_at, last_activity_at, ended_at "
                    "FROM client_sessions WHERE profile_id = %s",
                    (profile_id,),
                )
                sessions = list(cur.fetchall())

                deleted_messages = 0
                for contact_id, started_at, last_activity_at, ended_at in sessions:
                    since, until, idle_limit = session_window(
                        started_at, last_activity_at, ended_at, now, idle_minutes
                    )
                    cur.execute(
                        "DELETE FROM messages WHERE contact_id = %s "
                        "AND at >= %s AND at <= %s AND at < %s RETURNING id",
                        (contact_id, since, until, idle_limit),
                    )
                    deleted_messages += len(list(cur.fetchall()))

                cur.execute(
                    "DELETE FROM conversation_summaries WHERE profile_id = %s "
                    "RETURNING session_id",
                    (profile_id,),
                )
                deleted_summaries = len(list(cur.fetchall()))

                cur.execute(
                    "DELETE FROM client_memory WHERE profile_id = %s "
                    "RETURNING profile_id",
                    (profile_id,),
                )
                deleted_memory = len(list(cur.fetchall()))

                counts = {
                    "messages": deleted_messages,
                    "conversation_summaries": deleted_summaries,
                    "client_memory": deleted_memory,
                }
                cur.execute(
                    "UPDATE suppression_requests SET status = 'executed', "
                    "executed_at = %s, executed_by = %s, removed_counts = CAST(%s AS JSONB) "
                    "WHERE id = %s",
                    (now, executed_by, json.dumps(counts), request_id),
                )
                conn.commit()
                return counts
            except Exception:
                conn.rollback()
                raise

    def purge_personal_data(self, cutoff: datetime, ran_at: datetime) -> dict[str, int]:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id FROM contacts c WHERE c.created_at < %s "
                    "AND NOT EXISTS (SELECT 1 FROM messages m "
                    "WHERE m.contact_id = c.id AND m.at >= %s) "
                    "AND NOT EXISTS (SELECT 1 FROM case_links l "
                    "WHERE l.contact_id = c.id AND l.created_at >= %s)",
                    (cutoff, cutoff, cutoff),
                )
                inactive_ids = [row[0] for row in cur.fetchall()]

                deleted_links = 0
                deleted_contacts = 0
                if inactive_ids:
                    cur.execute(
                        "DELETE FROM case_links WHERE contact_id = ANY(%s) "
                        "RETURNING case_id",
                        (inactive_ids,),
                    )
                    deleted_links = len(cur.fetchall())
                    cur.execute(
                        "DELETE FROM contacts WHERE id = ANY(%s) RETURNING id",
                        (inactive_ids,),
                    )
                    deleted_contacts = len(cur.fetchall())

                if inactive_ids:
                    cur.execute(
                        "DELETE FROM auto_handover_outcomes "
                        "WHERE at < %s OR contact_id = ANY(%s) "
                        "RETURNING contact_id, update_id",
                        (cutoff, inactive_ids),
                    )
                else:
                    cur.execute(
                        "DELETE FROM auto_handover_outcomes WHERE at < %s "
                        "RETURNING contact_id, update_id",
                        (cutoff,),
                    )
                deleted_outcomes = len(cur.fetchall())

                deleted_streaks = 0
                if inactive_ids:
                    cur.execute(
                        "DELETE FROM auto_handover_streaks "
                        "WHERE contact_id = ANY(%s) RETURNING contact_id",
                        (inactive_ids,),
                    )
                    deleted_streaks = len(cur.fetchall())
                    cur.execute(
                        "DELETE FROM conversation_states "
                        "WHERE contact_id = ANY(%s) RETURNING contact_id",
                        (inactive_ids,),
                    )

                cur.execute(
                    "DELETE FROM messages WHERE at < %s RETURNING id", (cutoff,)
                )
                deleted_messages = len(cur.fetchall())
                cur.execute(
                    "DELETE FROM events WHERE at < %s RETURNING id", (cutoff,)
                )
                deleted_events = len(cur.fetchall())

                if inactive_ids:
                    cur.execute(
                        "DELETE FROM tool_calls "
                        "WHERE at < %s OR contact_id = ANY(%s) RETURNING id",
                        (cutoff, inactive_ids),
                    )
                else:
                    cur.execute(
                        "DELETE FROM tool_calls WHERE at < %s RETURNING id",
                        (cutoff,),
                    )
                deleted_tool_calls = len(cur.fetchall())

                cur.execute(
                    "DELETE FROM conversation_summaries WHERE updated_at < %s "
                    "RETURNING session_id",
                    (cutoff,),
                )
                deleted_summaries = len(cur.fetchall())

                counts = {
                    "messages": deleted_messages,
                    "events": deleted_events,
                    "contacts": deleted_contacts,
                    "case_links": deleted_links,
                    "auto_handover_outcomes": deleted_outcomes,
                    "auto_handover_streaks": deleted_streaks,
                    "tool_calls": deleted_tool_calls,
                    "conversation_summaries": deleted_summaries,
                }
                cur.execute(
                    "INSERT INTO privacy_purge_runs (ran_at, cutoff, counts) "
                    "VALUES (%s, %s, CAST(%s AS JSONB))",
                    (ran_at, cutoff, json.dumps(counts)),
                )
                conn.commit()
                return counts
            except Exception:
                conn.rollback()
                raise

    def get_app_settings(self, prefixes: Sequence[str]) -> dict[str, str]:
        patterns = [f"{prefix}%" for prefix in prefixes]
        rows = self._run(
            "SELECT key, value FROM app_settings WHERE key LIKE ANY(%s)",
            (patterns,),
            fetch=True,
        )
        return {key: value for key, value in rows}

    def save_app_settings(
        self, upserts: dict[str, str], deletes: Sequence[str]
    ) -> None:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                for key in deletes:
                    cur.execute("DELETE FROM app_settings WHERE key = %s", (key,))
                for key, value in upserts.items():
                    cur.execute(
                        "INSERT INTO app_settings (key, value) VALUES (%s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                        (key, value),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def current_text_versions(self) -> dict[str, int]:
        rows = self._run(
            "SELECT field, MAX(version) FROM text_versions GROUP BY field",
            (),
            fetch=True,
        )
        return {field: int(version) for field, version in rows}

    def text_history(self, field: str, limit: int) -> list[TextVersion]:
        rows = self._run(
            "SELECT field, version, value, created_by, created_at FROM text_versions "
            "WHERE field = %s ORDER BY version DESC LIMIT %s",
            (field, limit),
            fetch=True,
        )
        return [
            TextVersion(
                field=row[0],
                version=row[1],
                value=row[2],
                created_by=row[3],
                created_at=row[4],
            )
            for row in rows
        ]

    def list_client_credentials(self) -> list[ClientCredentialRow]:
        rows = self._run(
            "SELECT p.id, p.username, p.role, p.telegram_user_id, "
            "c.valid_from, c.valid_until, c.revoked_at, "
            "EXISTS(SELECT 1 FROM client_sessions s "
            "WHERE s.profile_id = p.id AND s.ended_at IS NULL) "
            "FROM profiles p JOIN client_credentials c ON c.profile_id = p.id "
            "WHERE p.role = 'cliente' ORDER BY p.username",
            (),
            fetch=True,
        )
        return [
            ClientCredentialRow(
                profile=Profile(
                    id=row[0], username=row[1], role=row[2], telegram_user_id=row[3]
                ),
                credential=ClientCredential(
                    profile_id=row[0],
                    valid_from=row[4],
                    valid_until=row[5],
                    revoked_at=row[6],
                ),
                has_active_session=bool(row[7]),
            )
            for row in rows
        ]

    def current_expiry_notice_status(
        self, profile_id: str, valid_until: datetime
    ) -> str | None:
        rows = self._run(
            "SELECT status FROM credential_expiry_notices "
            "WHERE profile_id = %s AND valid_until = %s",
            (profile_id, valid_until),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def list_whatsapp_templates(self) -> list[WhatsAppTemplate]:
        rows = self._run(
            "SELECT name, purpose, language, variables, body, status, "
            "approved_by, approved_at, updated_at FROM whatsapp_templates "
            "ORDER BY name",
            (),
            fetch=True,
        )
        return [
            WhatsAppTemplate(
                name=row[0],
                purpose=row[1],
                language=row[2],
                variables=row[3],
                body=row[4],
                status=row[5],
                approved_by=row[6],
                approved_at=row[7],
                updated_at=row[8],
            )
            for row in rows
        ]

    def create_whatsapp_template(self, template: WhatsAppTemplate) -> None:
        rows = self._run(
            "INSERT INTO whatsapp_templates "
            "(name, purpose, language, variables, body, status, approved_by, "
            "approved_at, updated_by, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO NOTHING RETURNING name",
            (
                template.name,
                template.purpose,
                template.language,
                template.variables,
                template.body,
                template.status,
                template.approved_by,
                template.approved_at,
                template.approved_by or "",
                template.updated_at,
            ),
            fetch=True,
        )
        if not rows:
            raise TemplateExists("La plantilla ya existe.")

    def update_whatsapp_template(
        self,
        name: str,
        language: str,
        variables: int,
        body: str,
        actor: str,
        at: datetime,
    ) -> bool:
        rows = self._run(
            "UPDATE whatsapp_templates SET language = %s, variables = %s, "
            "body = %s, status = 'draft', approved_by = NULL, approved_at = NULL, "
            "updated_by = %s, updated_at = %s WHERE name = %s RETURNING name",
            (language, variables, body, actor, at, name),
            fetch=True,
        )
        return bool(rows)

    def set_whatsapp_template_status(
        self,
        name: str,
        from_status: str,
        to_status: str,
        actor: str,
        at: datetime,
    ) -> bool:
        if to_status == "approved":
            rows = self._run(
                "UPDATE whatsapp_templates SET status = %s, approved_by = %s, "
                "approved_at = %s, updated_by = %s, updated_at = %s "
                "WHERE name = %s AND status = %s RETURNING name",
                (to_status, actor, at, actor, at, name, from_status),
                fetch=True,
            )
        else:
            rows = self._run(
                "UPDATE whatsapp_templates SET status = %s, updated_by = %s, "
                "updated_at = %s WHERE name = %s AND status = %s RETURNING name",
                (to_status, actor, at, name, from_status),
                fetch=True,
            )
        return bool(rows)

    def list_expiring_credentials(
        self, now: datetime, horizon: datetime
    ) -> list[ExpiringCredential]:
        rows = self._run(
            "SELECT profile_id, valid_until FROM client_credentials "
            "WHERE revoked_at IS NULL AND valid_from <= %s "
            "AND valid_until > %s AND valid_until <= %s "
            "ORDER BY valid_until, profile_id",
            (now, now, horizon),
            fetch=True,
        )
        return [ExpiringCredential(row[0], row[1]) for row in rows]

    def last_client_contact(self, profile_id: str) -> Contact | None:
        rows = self._run(
            "SELECT c.id, c.channel, c.external_user_id, c.external_chat_id, "
            "c.telegram_user_id, c.chat_id FROM client_sessions s "
            "JOIN contacts c ON c.id = s.contact_id "
            "WHERE s.profile_id = %s "
            "ORDER BY s.last_activity_at DESC, s.id DESC LIMIT 1",
            (profile_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Contact(
            id=row[0],
            channel=row[1],
            external_user_id=row[2] or "",
            external_chat_id=row[3] or "",
            telegram_user_id=row[4],
            chat_id=row[5],
        )

    def claim_expiry_notice(
        self,
        profile_id: str,
        valid_until: datetime,
        now: datetime,
        max_attempts: int,
    ) -> bool:
        rows = self._run(
            "INSERT INTO credential_expiry_notices "
            "(profile_id, valid_until, status, method, attempts, created_at, updated_at) "
            "VALUES (%s, %s, 'sending', NULL, 1, %s, %s) "
            "ON CONFLICT (profile_id, valid_until) DO UPDATE "
            "SET status = 'sending', "
            "attempts = credential_expiry_notices.attempts + 1, "
            "updated_at = EXCLUDED.updated_at "
            "WHERE credential_expiry_notices.status = 'failed' "
            "AND credential_expiry_notices.attempts < %s "
            "RETURNING profile_id",
            (profile_id, valid_until, now, now, max_attempts),
            fetch=True,
        )
        return bool(rows)

    def finish_expiry_notice(
        self,
        profile_id: str,
        valid_until: datetime,
        status: str,
        method: str,
        now: datetime,
    ) -> None:
        self._run(
            "UPDATE credential_expiry_notices SET status = %s, method = %s, "
            "updated_at = %s WHERE profile_id = %s AND valid_until = %s",
            (status, method, now, profile_id, valid_until),
        )

    def case_first_responses(
        self, since: datetime, until: datetime
    ) -> list[tuple[datetime, datetime | None]]:
        rows = self._run(
            "SELECT l.created_at, (SELECT MIN(m.at) FROM messages m "
            "WHERE m.contact_id = l.contact_id AND m.role = 'advisor' "
            "AND m.at >= l.created_at) FROM case_links l "
            "WHERE l.created_at >= %s AND l.created_at < %s "
            "ORDER BY l.created_at",
            (since, until),
            fetch=True,
        )
        return [(row[0], row[1]) for row in rows]

    def advisor_reply_contacts(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, int]]:
        rows = self._run(
            "SELECT reason, contact_id FROM events "
            "WHERE type = 'advisor_reply' AND at >= %s AND at < %s",
            (since, until),
            fetch=True,
        )
        contacts_by_ref: dict[str, set[str]] = {}
        for reason, contact_id in rows:
            if not reason.startswith("advisor:"):
                continue
            contacts_by_ref.setdefault(reason.split(":", 1)[1], set()).add(contact_id)
        result = [(ref, len(values)) for ref, values in contacts_by_ref.items()]
        result.sort(key=lambda row: (-row[1], row[0]))
        return result

    def event_reason_counts(
        self, event_type: str, since: datetime, until: datetime
    ) -> list[tuple[str, int]]:
        rows = self._run(
            "SELECT reason, COUNT(*) FROM events "
            "WHERE type = %s AND at >= %s AND at < %s "
            "GROUP BY reason ORDER BY COUNT(*) DESC, reason",
            (event_type, since, until),
            fetch=True,
        )
        return [(row[0], int(row[1])) for row in rows]

    def count_events(
        self, types: tuple[str, ...], since: datetime, until: datetime
    ) -> int:
        rows = self._run(
            "SELECT COUNT(*) FROM events WHERE type = ANY(%s) "
            "AND at >= %s AND at < %s",
            (list(types), since, until),
            fetch=True,
        )
        return int(rows[0][0]) if rows else 0

    def unanswered_samples(
        self, since: datetime, until: datetime, limit: int
    ) -> list[tuple[datetime, str]]:
        rows = self._run(
            "SELECT e.at, (SELECT m.text FROM messages m "
            "WHERE m.contact_id = e.contact_id AND m.role = 'user' "
            "AND m.at <= e.at ORDER BY m.at DESC, m.id DESC LIMIT 1) "
            "FROM events e WHERE e.type = ANY(%s) AND e.at >= %s AND e.at < %s "
            "ORDER BY e.at DESC, e.id DESC LIMIT %s",
            (["no_results", "invalid_answer"], since, until, limit),
            fetch=True,
        )
        return [(row[0], row[1]) for row in rows if row[1] is not None]
