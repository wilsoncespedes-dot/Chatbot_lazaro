"""Persistencia (contactos, historial, eventos, update_id, casos) detrás de un Repository."""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import unquote, urlparse

from lazaro_contracts import LastMessage

from ..classifier import Category
from ..client_id import PublicIdGenerationError, PublicIdTaken, generate_public_id
from ..panel_live import PanelEvent
from ..domain import (
    CaseNote,
    CaseTag,
    ClientCredential,
    ClientHistoryMessage,
    ClientSearchResult,
    ClientSession,
    ClientStatus,
    Contact,
    ConversationRef,
    ConversationState,
    DedupKey,
    FailedSend,
    InboundEntry,
    InboundQueueRow,
    OutboxEntry,
    OutboxRow,
    Profile,
    QuickReply,
    QuickReplyImage,
    SavedReply,
    ServiceUnavailable,
    SummaryView,
    TemplateExists,
    UsernameTaken,
    conversation_key,
    destination_key,
)
from ..legacy import LEGACY_CHANNEL
from ..memory import in_window, session_window
from ..privacy import (
    ConversationTexts,
    conversation_text_settings,
    parse_conversation_texts,
)

logger = logging.getLogger(__name__)


class Repository(Protocol):
    def health_check(self, timeout_seconds: float) -> None:
        """Comprueba PostgreSQL con `SELECT 1` y un timeout acotado (solo lectura)."""
        ...

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

    # cola de entrada y outbox (#64)
    def enqueue_inbound(
        self, entry: InboundEntry, dedup: DedupKey | None
    ) -> bool: ...

    def claim_inbound(
        self, now: datetime, lease_seconds: float
    ) -> InboundQueueRow | None: ...

    def finish_inbound(self, row_id: int, now: datetime) -> None: ...

    def retry_inbound(
        self, row_id: int, next_attempt_at: datetime, error: str
    ) -> None: ...

    def fail_inbound(self, row_id: int, now: datetime, error: str) -> None: ...

    def enqueue_outbound(self, entry: OutboxEntry) -> int: ...

    def add_message_with_outbox(
        self,
        contact_id: str,
        role: str,
        text: str,
        at: datetime,
        entry: OutboxEntry,
    ) -> None: ...

    def claim_outbound(
        self, now: datetime, lease_seconds: float
    ) -> OutboxRow | None: ...

    def finish_outbound(self, row_id: int, now: datetime) -> None: ...

    def retry_outbound(
        self, row_id: int, next_attempt_at: datetime, error: str
    ) -> None: ...

    def fail_outbound(self, row_id: int, now: datetime, error: str) -> None: ...

    def list_failed_outbound(self, limit: int) -> list[FailedSend]: ...

    def requeue_outbound(self, row_id: int, now: datetime) -> str: ...

    def publish_panel_event(self, case_id: str, kind: str, at: datetime) -> None: ...

    def panel_events_cursor(self) -> int: ...

    def panel_events_since(
        self, after_id: int, since: datetime, limit: int
    ) -> list[PanelEvent]: ...

    def delete_panel_events_before(self, before: datetime) -> int: ...

    def latest_case_for_contact(self, contact_id: str) -> str | None: ...

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]: ...

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None: ...

    def last_event_at(self, contact_id: str, type: str) -> datetime | None: ...

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

    def list_conversations(
        self, states: Sequence[str], limit: int
    ) -> list[ConversationRef]: ...

    def conversation_ref(self, contact_id: str) -> ConversationRef | None: ...

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

    def get_advisor_roster_state(self) -> tuple[int, str]: ...

    def begin_advisor_roster_change(self) -> int: ...

    def mark_advisor_roster_synced(self, generation: int) -> bool: ...

    def set_role(self, profile_id: str, role: str) -> bool: ...

    def create_session(
        self,
        token_hash: str,
        profile_id: str,
        csrf_token: str,
        expires_at: datetime,
        enroll_only: bool = False,
    ) -> None: ...

    def get_session(self, token_hash: str, now: datetime) -> "AdminSession | None": ...

    def get_session_any(
        self, token_hash: str, now: datetime
    ) -> "AdminSession | None": ...

    def get_session_for_role(
        self, token_hash: str, now: datetime, role: str
    ) -> "AdminSession | None": ...

    def get_session_for_roles(
        self, token_hash: str, now: datetime, roles: Sequence[str]
    ) -> "AdminSession | None": ...

    def promote_session(self, token_hash: str) -> None: ...

    def delete_session(self, token_hash: str) -> None: ...

    def delete_sessions_for_profile(
        self, profile_id: str, keep_token_hash: str | None = None
    ) -> None: ...

    def get_two_factor(self, profile_id: str) -> "TwoFactorRecord | None": ...

    def save_pending_two_factor(
        self, profile_id: str, ciphertext: str, now: datetime
    ) -> bool: ...

    def activate_two_factor(
        self, profile_id: str, step: int, code_hashes: Sequence[str], now: datetime
    ) -> bool: ...

    def advance_two_factor_step(self, profile_id: str, step: int) -> bool: ...

    def consume_recovery_code(
        self, profile_id: str, code_hash: str, now: datetime
    ) -> bool: ...

    def delete_two_factor(self, profile_id: str) -> bool: ...

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

    # consentimiento por cliente (#72)
    def has_client_consent_for_identity(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        not_before: datetime | None,
    ) -> bool: ...

    def register_client_login(
        self,
        cliente_id: str,
        channel: str,
        external_user_id: str,
        notice_version: str,
        now: datetime,
    ) -> None: ...

    def register_client_acceptance_if_linked(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None: ...

    def client_history(
        self, cliente_id: str, limit: int
    ) -> list[ClientHistoryMessage]: ...

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

    def purge_personal_data(
        self,
        cutoff: datetime,
        ran_at: datetime,
        client_cutoff: datetime | None = None,
    ) -> dict[str, int]: ...

    def create_client_credential(
        self,
        username: str,
        password_hash: str,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
        public_id: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Profile: ...

    def find_client_id_by_email(self, email: str) -> str | None: ...

    def find_client_id_by_phone(self, phone: str) -> str | None: ...

    def update_client_contact(
        self,
        profile_id: str,
        now: datetime,
        *,
        email: str | None = None,
        phone: str | None = None,
    ) -> bool: ...

    def ensure_public_ids(self, generate: Callable[[], str]) -> int: ...

    def find_client_by_public_id(
        self, public_id: str
    ) -> ClientSearchResult | None: ...

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

    # notas internas y etiquetas (#50)
    def add_case_note(self, note: CaseNote, contact_id: str) -> None: ...

    def list_case_notes(self, case_id: str) -> list[CaseNote]: ...

    def get_case_note(self, note_id: str) -> CaseNote | None: ...

    def delete_case_note(self, note_id: str) -> bool: ...

    def count_case_notes(self, case_id: str) -> int: ...

    def create_case_tag(
        self, tag: CaseTag, name_key: str, now: datetime
    ) -> bool: ...

    def rename_case_tag(
        self, tag_id: str, name: str, name_key: str, now: datetime
    ) -> bool: ...

    def set_case_tag_active(
        self, tag_id: str, active: bool, now: datetime
    ) -> bool: ...

    def get_case_tag(self, tag_id: str) -> CaseTag | None: ...

    def list_case_tags(self, only_active: bool = False) -> list[CaseTag]: ...

    def add_case_tag(
        self,
        case_id: str,
        tag_id: str,
        contact_id: str,
        assigned_by: str,
        now: datetime,
    ) -> None: ...

    def remove_case_tag(self, case_id: str, tag_id: str) -> bool: ...

    def count_case_tags(self, case_id: str) -> int: ...

    def case_tag_map(
        self, case_ids: Sequence[str]
    ) -> dict[str, tuple[str, ...]]: ...

    # respuestas guardadas (#51)
    def add_saved_reply(self, reply: SavedReply) -> None: ...

    def update_saved_reply(
        self, reply_id: str, title: str, body: str, now: datetime
    ) -> bool: ...

    def set_saved_reply_active(
        self, reply_id: str, active: bool, now: datetime
    ) -> bool: ...

    def get_saved_reply(self, reply_id: str) -> SavedReply | None: ...

    def list_saved_replies(self, only_active: bool = False) -> list[SavedReply]: ...

    def count_saved_replies(self) -> int: ...

    # respuestas rápidas del bot (#71)
    def add_quick_reply(self, reply: QuickReply) -> None: ...

    def update_quick_reply(
        self,
        reply_id: str,
        name: str,
        triggers: Sequence[str],
        blocks: Sequence[dict],
        image_id: str | None,
        priority: int,
        now: datetime,
    ) -> bool: ...

    def set_quick_reply_active(
        self, reply_id: str, active: bool, now: datetime
    ) -> bool: ...

    def get_quick_reply(self, reply_id: str) -> QuickReply | None: ...

    def list_quick_replies(self, only_active: bool = False) -> list[QuickReply]: ...

    def add_quick_reply_image(self, image: QuickReplyImage) -> None: ...

    def get_quick_reply_image(self, image_id: str) -> QuickReplyImage | None: ...

    def delete_quick_reply_image(self, image_id: str) -> None: ...

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
        self,
        since: datetime,
        until: datetime,
        exclude_channels: frozenset[str] = frozenset(),
    ) -> list[tuple[datetime, datetime | None]]: ...

    def dashboard_messages(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, str, str, datetime]]: ...

    def case_channels(self, since: datetime, until: datetime) -> dict[str, str]: ...

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
PANEL_MESSAGE_ROLES = frozenset({"user", "bot", "advisor"})


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
    canal_id: str | None = None


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
    public_id: str | None = None
    email: str | None = None
    phone: str | None = None
    contact_updated_at: datetime | None = None


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
    enroll_only: bool = False


@dataclass
class TwoFactorRecord:
    profile_id: str
    secret_ciphertext: str
    enabled_at: datetime | None
    last_used_step: int
    created_at: datetime


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
    channel: str = LEGACY_CHANNEL
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


def _blocks_json(blocks: Sequence) -> list:
    """Serializa bloques del contrato a JSON apto para JSONB."""
    result: list = []
    for block in blocks:
        if isinstance(block, dict):
            result.append(block)
        else:
            result.append(block.model_dump(mode="json"))
    return result


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _quick_reply_from_row(row: Sequence) -> QuickReply:
    triggers = _json_value(row[2]) or []
    blocks = _json_value(row[3]) or []
    return QuickReply(
        id=row[0],
        name=row[1],
        triggers=tuple(triggers),
        blocks=tuple(blocks),
        image_id=row[4],
        active=bool(row[5]),
        priority=int(row[6]),
        created_at=row[7],
        updated_at=row[8],
    )


class FakeRepository:
    def __init__(self) -> None:
        self.contacts: dict[object, Contact] = {}
        # #65 R31: `canal_id` guardado al crear cada contacto.
        self.contact_canal_ids: dict[str, str] = {}
        self.messages: list[StoredMessage] = []
        self.events: list[StoredEvent] = []
        self.processed: set[int] = set()
        self.processed_messages: set[tuple[str, str]] = set()
        self.case_links: dict[str, str] = {}
        self.profiles: dict[str, StoredProfile] = {}
        self.link_tokens: dict[str, StoredLinkToken] = {}
        self.sessions: dict[str, AdminSession] = {}
        self.two_factor: dict[str, TwoFactorRecord] = {}
        self.recovery_codes: dict[str, dict[str, Any]] = {}
        self._two_factor_lock = threading.Lock()
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
        self.panel_events: list[PanelEvent] = []
        self.panel_events_retention_hours = 24
        self._panel_event_times: dict[int, datetime] = {}
        self._panel_event_seq = 0
        self.privacy_consents: list[PrivacyConsent] = []
        self.privacy_purge_runs: list[dict[str, Any]] = []
        self.fail_privacy_consent = False
        self.fail_privacy_consent_delete = False
        # #72: identidad -> (cliente_id, vinculado_en) y aceptación por cliente.
        self.identidades_cliente: dict[tuple[str, str], tuple[str, datetime]] = {}
        self.consentimientos_cliente: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail_client_link = False
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
        self.case_notes: list[tuple[CaseNote, str]] = []
        self.case_tags: dict[str, dict[str, Any]] = {}
        self.case_tag_assignments: list[tuple[str, str, str, str, datetime]] = []
        self.saved_replies: dict[str, SavedReply] = {}
        self.quick_replies: dict[str, QuickReply] = {}
        self.quick_reply_images: dict[str, QuickReplyImage] = {}
        self.text_versions: list[TextVersion] = []
        self.whatsapp_templates: dict[str, WhatsAppTemplate] = {}
        self.expiry_notices: dict[tuple[str, datetime], dict[str, Any]] = {}
        self._expiry_lock = threading.Lock()
        self._app_settings: dict[str, str] = {}
        self._profiles_lock = threading.Lock()
        self._rag_lock = threading.Lock()
        self._processed_lock = threading.Lock()
        self._identity_lock = threading.Lock()
        self.health_checks: list[float] = []
        self.health_error: BaseException | None = None
        self.advisor_roster_generation = 0
        self.advisor_roster_status = "synced"
        # cola de entrada y outbox (#64)
        self.inbox: dict[int, dict[str, Any]] = {}
        self.outbox: dict[int, dict[str, Any]] = {}
        self._inbox_seq = 0
        self._outbox_seq = 0
        self._queue_lock = threading.Lock()
        self.fail_inbox_insert = False
        self.fail_outbox_insert = False

    def get_advisor_roster_state(self) -> tuple[int, str]:
        return self.advisor_roster_generation, self.advisor_roster_status

    def begin_advisor_roster_change(self) -> int:
        self.advisor_roster_generation += 1
        self.advisor_roster_status = "pending"
        return self.advisor_roster_generation

    def mark_advisor_roster_synced(self, generation: int) -> bool:
        if generation != self.advisor_roster_generation:
            return False
        self.advisor_roster_status = "synced"
        return True

    def health_check(self, timeout_seconds: float) -> None:
        """healthcheck_dependencias R4, R8: fallo y timeout controlables en tests."""
        self.health_checks.append(timeout_seconds)
        if self.health_error is not None:
            raise self.health_error

    def mark_message_if_new(
        self, channel: str, external_message_id: str
    ) -> bool:
        """R5, R6: la clave es (canal, mensaje externo), no el id aislado."""
        with self._processed_lock:
            legacy_id: int | None = None
            if channel == LEGACY_CHANNEL:
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
            if (LEGACY_CHANNEL, str(update_id)) in self.processed_messages:
                return False
            self.processed.add(update_id)
            return True

    # --- cola de entrada y outbox (#64) ----------------------------------
    def _dedup_exists_locked(self, dedup: DedupKey) -> bool:
        if dedup.kind == "message":
            if (dedup.channel, dedup.external_message_id) in self.processed_messages:
                return True
            if dedup.channel == LEGACY_CHANNEL:
                legacy = _telegram_value(dedup.external_message_id)
                if legacy is not None and legacy in self.processed:
                    return True
            return False
        if dedup.update_id in self.processed:
            return True
        return (LEGACY_CHANNEL, str(dedup.update_id)) in self.processed_messages

    def _add_dedup_locked(self, dedup: DedupKey) -> None:
        if dedup.kind == "message":
            self.processed_messages.add((dedup.channel, dedup.external_message_id))
        else:
            self.processed.add(dedup.update_id)

    def _remove_dedup_locked(self, dedup: DedupKey) -> None:
        if dedup.kind == "message":
            self.processed_messages.discard(
                (dedup.channel, dedup.external_message_id)
            )
        else:
            self.processed.discard(dedup.update_id)

    def _insert_inbox_locked(self, entry: InboundEntry) -> int:
        self._inbox_seq += 1
        row_id = self._inbox_seq
        self.inbox[row_id] = {
            "id": row_id,
            "conversation_key": entry.conversation_key,
            "channel": entry.channel,
            "external_user_id": entry.external_user_id,
            "payload_kind": entry.payload_kind,
            "payload": dict(entry.payload),
            "status": "pending",
            "attempts": 0,
            "next_attempt_at": datetime.min.replace(tzinfo=timezone.utc),
            "locked_until": None,
            "last_error": None,
            "created_at": datetime.now(timezone.utc),
            "finished_at": None,
        }
        return row_id

    def enqueue_inbound(
        self, entry: InboundEntry, dedup: DedupKey | None
    ) -> bool:
        """R1, R4, R5, R7: dedup + INSERT atómicos (o solo INSERT sin dedup)."""
        with self._queue_lock:
            added: DedupKey | None = None
            if dedup is not None:
                with self._processed_lock:
                    if self._dedup_exists_locked(dedup):
                        return False
                    self._add_dedup_locked(dedup)
                    added = dedup
            if self.fail_inbox_insert:
                if added is not None:
                    with self._processed_lock:
                        self._remove_dedup_locked(added)
                raise ServiceUnavailable("inbox no disponible")
            self._insert_inbox_locked(entry)
            return True

    def _claim_locked(
        self,
        rows: dict[int, dict[str, Any]],
        key: str,
        now: datetime,
        lease_seconds: float,
        pending: str,
        active: str,
        active_statuses: tuple[str, str],
    ) -> dict[str, Any] | None:
        eligible = [
            row
            for row in rows.values()
            if (
                row["status"] == pending
                and row["next_attempt_at"] <= now
            )
            or (
                row["status"] == active
                and row["locked_until"] is not None
                and row["locked_until"] < now
            )
        ]
        eligible.sort(key=lambda row: row["id"])
        for row in eligible:
            if any(
                other["id"] < row["id"]
                and other[key] == row[key]
                and other["status"] in active_statuses
                for other in rows.values()
            ):
                continue
            row["status"] = active
            row["attempts"] += 1
            row["locked_until"] = now + timedelta(seconds=lease_seconds)
            return dict(row)
        return None

    def claim_inbound(
        self, now: datetime, lease_seconds: float
    ) -> InboundQueueRow | None:
        with self._queue_lock:
            row = self._claim_locked(
                self.inbox,
                "conversation_key",
                now,
                lease_seconds,
                "pending",
                "processing",
                ("pending", "processing"),
            )
            if row is None:
                return None
            return InboundQueueRow(
                id=row["id"],
                conversation_key=row["conversation_key"],
                channel=row["channel"],
                payload_kind=row["payload_kind"],
                payload=dict(row["payload"]),
                attempts=row["attempts"],
                created_at=row["created_at"],
            )

    def finish_inbound(self, row_id: int, now: datetime) -> None:
        with self._queue_lock:
            row = self.inbox.get(row_id)
            if row is None:
                return
            row["status"] = "done"
            row["payload"] = {}
            row["finished_at"] = now
            row["locked_until"] = None

    def retry_inbound(
        self, row_id: int, next_attempt_at: datetime, error: str
    ) -> None:
        with self._queue_lock:
            row = self.inbox.get(row_id)
            if row is None:
                return
            row["status"] = "pending"
            row["next_attempt_at"] = next_attempt_at
            row["last_error"] = error
            row["locked_until"] = None

    def fail_inbound(self, row_id: int, now: datetime, error: str) -> None:
        with self._queue_lock:
            row = self.inbox.get(row_id)
            if row is None:
                return
            row["status"] = "failed"
            row["payload"] = {}
            row["last_error"] = error
            row["finished_at"] = now
            row["locked_until"] = None

    def _insert_outbox_locked(self, entry: OutboxEntry) -> int:
        self._outbox_seq += 1
        row_id = self._outbox_seq
        now = datetime.now(timezone.utc)
        self.outbox[row_id] = {
            "id": row_id,
            "contact_id": entry.contact_id,
            "destination_key": entry.destination_key,
            "channel": entry.channel,
            "destination": entry.destination,
            "kind": entry.kind,
            "blocks": _blocks_json(entry.blocks),
            "status": "pending",
            "attempts": 0,
            "next_attempt_at": datetime.min.replace(tzinfo=timezone.utc),
            "locked_until": None,
            "last_error": None,
            "created_at": now,
            "finished_at": None,
        }
        return row_id

    def enqueue_outbound(self, entry: OutboxEntry) -> int:
        with self._queue_lock:
            if self.fail_outbox_insert:
                raise ServiceUnavailable("outbox no disponible")
            return self._insert_outbox_locked(entry)

    def add_message_with_outbox(
        self,
        contact_id: str,
        role: str,
        text: str,
        at: datetime,
        entry: OutboxEntry,
    ) -> None:
        """R17, R18, R20: mensaje y salida en una sola transacción."""
        with self._queue_lock:
            if self.fail_outbox_insert:
                raise ServiceUnavailable("outbox no disponible")
            self.messages.append(
                StoredMessage(contact_id, role, text, at, self._canal_id_of(contact_id))
            )
            try:
                self._insert_outbox_locked(entry)
            except Exception:
                self.messages.pop()
                raise
            case_id = (
                self.latest_case_for_contact(contact_id)
                if role in PANEL_MESSAGE_ROLES
                else None
            )
        if case_id is None:
            return
        try:
            self.publish_panel_event(case_id, "message", at)
        except Exception:
            return

    def claim_outbound(
        self, now: datetime, lease_seconds: float
    ) -> OutboxRow | None:
        with self._queue_lock:
            row = self._claim_locked(
                self.outbox,
                "destination_key",
                now,
                lease_seconds,
                "pending",
                "sending",
                ("pending", "sending"),
            )
            if row is None:
                return None
            return OutboxRow(
                id=row["id"],
                destination_key=row["destination_key"],
                channel=row["channel"],
                destination=row["destination"],
                blocks=list(row["blocks"]),
                attempts=row["attempts"],
                created_at=row["created_at"],
            )

    def finish_outbound(self, row_id: int, now: datetime) -> None:
        with self._queue_lock:
            row = self.outbox.get(row_id)
            if row is None:
                return
            row["status"] = "sent"
            row["blocks"] = []
            row["finished_at"] = now
            row["locked_until"] = None

    def retry_outbound(
        self, row_id: int, next_attempt_at: datetime, error: str
    ) -> None:
        with self._queue_lock:
            row = self.outbox.get(row_id)
            if row is None:
                return
            row["status"] = "pending"
            row["next_attempt_at"] = next_attempt_at
            row["last_error"] = error
            row["locked_until"] = None

    def fail_outbound(self, row_id: int, now: datetime, error: str) -> None:
        with self._queue_lock:
            row = self.outbox.get(row_id)
            if row is None:
                return
            row["status"] = "failed"
            row["last_error"] = error
            row["finished_at"] = now
            row["locked_until"] = None

    def list_failed_outbound(self, limit: int) -> list[FailedSend]:
        rows = [
            row for row in self.outbox.values() if row["status"] == "failed"
        ]
        rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
        return [
            FailedSend(
                id=row["id"],
                channel=row["channel"],
                destination=row["destination"],
                kind=row["kind"],
                attempts=row["attempts"],
                last_error=row["last_error"],
                created_at=row["created_at"],
            )
            for row in rows[:limit]
        ]

    def requeue_outbound(self, row_id: int, now: datetime) -> str:
        with self._queue_lock:
            row = self.outbox.get(row_id)
            if row is None:
                return "not_found"
            if row["status"] != "failed":
                return "not_failed"
            row["status"] = "pending"
            row["attempts"] = 0
            row["next_attempt_at"] = now
            row["last_error"] = None
            row["locked_until"] = None
            row["finished_at"] = None
            return "ok"

    def _contact_key(self, channel: str, external_user_id: str) -> object:
        """Clave interna de `contacts`; Telegram conserva la clave entera histórica."""
        if channel == LEGACY_CHANNEL:
            legacy = _telegram_value(external_user_id)
            if legacy is not None:
                return legacy
        return (channel, external_user_id)

    def get_or_create_contact(self, telegram_user_id: int, chat_id: int, now: datetime) -> Contact:
        return self.get_or_create_channel_contact(
            LEGACY_CHANNEL, str(telegram_user_id), str(chat_id), now
        )

    def get_or_create_channel_contact(
        self, channel: str, external_user_id: str, external_chat_id: str, now: datetime
    ) -> Contact:
        key = self._contact_key(channel, external_user_id)
        contact = self.contacts.get(key)
        if contact is None:
            telegram_user_id = (
                _telegram_value(external_user_id) if channel == LEGACY_CHANNEL else None
            )
            chat_id = (
                _telegram_value(external_chat_id) if channel == LEGACY_CHANNEL else None
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
            self.contact_canal_ids[contact.id] = channel
        return contact

    def _canal_id_of(self, contact_id: str) -> str | None:
        """#65 R32: `canal_id` del mensaje = canal de su contacto."""
        if contact_id in self.contact_canal_ids:
            return self.contact_canal_ids[contact_id]
        for contact in self.contacts.values():
            if contact.id == contact_id:
                return contact.channel
        return None

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None:
        self.messages.append(
            StoredMessage(contact_id, role, text, at, self._canal_id_of(contact_id))
        )
        if role not in PANEL_MESSAGE_ROLES:
            return
        case_id = self.latest_case_for_contact(contact_id)
        if case_id is None:
            return
        try:
            self.publish_panel_event(case_id, "message", at)
        except Exception:
            # R18: el evento es un aviso; nunca debe hacer fallar el mensaje.
            return

    def publish_panel_event(self, case_id: str, kind: str, at: datetime) -> None:
        next_id = max(
            max((event.id for event in self.panel_events), default=0),
            self._panel_event_seq,
        ) + 1
        self._panel_event_seq = next_id
        self.panel_events.append(PanelEvent(id=next_id, case_id=case_id, kind=kind))
        self._panel_event_times[next_id] = at
        self.delete_panel_events_before(
            at - timedelta(hours=self.panel_events_retention_hours)
        )

    def panel_events_cursor(self) -> int:
        return max((event.id for event in self.panel_events), default=0)

    def panel_events_since(
        self, after_id: int, since: datetime, limit: int
    ) -> list[PanelEvent]:
        events = [
            event
            for event in self.panel_events
            if event.id > after_id or self._panel_event_at(event) >= since
        ]
        events.sort(key=lambda event: event.id)
        return events[:limit]

    def _panel_event_at(self, event: PanelEvent) -> datetime:
        return self._panel_event_times.get(
            event.id, datetime.min.replace(tzinfo=timezone.utc)
        )

    def delete_panel_events_before(self, before: datetime) -> int:
        kept = [
            event
            for event in self.panel_events
            if self._panel_event_at(event) >= before
        ]
        deleted = len(self.panel_events) - len(kept)
        self.panel_events = kept
        if deleted:
            live_ids = {event.id for event in kept}
            self._panel_event_times = {
                event_id: at
                for event_id, at in self._panel_event_times.items()
                if event_id in live_ids
            }
        return deleted

    def latest_case_for_contact(self, contact_id: str) -> str | None:
        latest: tuple[datetime, int, str] | None = None
        for index, (case_id, linked_contact_id) in enumerate(self.case_links.items()):
            if linked_contact_id != contact_id:
                continue
            created_at = self.case_link_created_at.get(case_id)
            if created_at is None:
                continue
            candidate = (created_at, index, case_id)
            if latest is None or candidate > latest:
                latest = candidate
        return latest[2] if latest is not None else None

    def link_case(
        self,
        case_id: str,
        contact_id: str,
        at: datetime,
        profile_id: str | None = None,
    ) -> None:
        is_new = case_id not in self.case_links
        self.case_links.setdefault(case_id, contact_id)
        self.case_link_created_at.setdefault(case_id, at)
        self.case_profiles.setdefault(case_id, profile_id)
        if not is_new:
            return
        try:
            self.publish_panel_event(case_id, "case_created", at)
        except Exception:
            # R18: el enlace del caso no falla porque no se pueda publicar el aviso.
            return

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]:
        own = [m for m in self.messages if m.contact_id == contact_id]
        return [LastMessage(role=m.role, text=m.text, at=m.at) for m in own[-limit:]]  # type: ignore[arg-type]

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None:
        self.events.append(StoredEvent(contact_id, type, reason, at))

    def last_event_at(self, contact_id: str, type: str) -> datetime | None:
        values = [
            event.at
            for event in self.events
            if event.contact_id == contact_id and event.type == type
        ]
        return max(values) if values else None

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

    def _conversation_ref(self, contact: Contact) -> ConversationRef | None:
        stored = self.conversation_states.get(contact.id)
        if stored is None:
            return None
        messages = [
            message for message in self.messages if message.contact_id == contact.id
        ]
        if not messages:
            return None
        user_messages = [message.at for message in messages if message.role == "user"]
        closed = [
            event.at
            for event in self.events
            if event.contact_id == contact.id and event.type == "case_closed"
        ]
        purchase_intent = [
            event.at
            for event in self.events
            if event.contact_id == contact.id and event.type == "purchase_intent"
        ]
        return ConversationRef(
            contact=contact,
            state=stored[0],
            last_activity_at=max(message.at for message in messages),
            last_user_at=max(user_messages) if user_messages else None,
            last_closed_at=max(closed) if closed else None,
            case_id=self.latest_case_for_contact(contact.id),
            last_purchase_intent_at=(
                max(purchase_intent) if purchase_intent else None
            ),
        )

    def list_conversations(
        self, states: Sequence[str], limit: int
    ) -> list[ConversationRef]:
        wanted = set(states)
        contacts = {contact.id: contact for contact in self.contacts.values()}
        refs: list[ConversationRef] = []
        for contact in contacts.values():
            stored = self.conversation_states.get(contact.id)
            if stored is None or stored[0].value not in wanted:
                continue
            ref = self._conversation_ref(contact)
            if ref is not None:
                refs.append(ref)
        refs.sort(key=lambda ref: (ref.last_activity_at, ref.contact.id), reverse=True)
        return refs[:limit]

    def conversation_ref(self, contact_id: str) -> ConversationRef | None:
        contact = self.get_contact(contact_id)
        if contact is None:
            return None
        return self._conversation_ref(contact)

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
            public_id=stored.public_id,
            email=stored.email,
            phone=stored.phone,
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
                    public_id=stored.public_id,
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
        self,
        token_hash: str,
        profile_id: str,
        csrf_token: str,
        expires_at: datetime,
        enroll_only: bool = False,
    ) -> None:
        self.sessions[token_hash] = AdminSession(
            token_hash=token_hash,
            profile_id=profile_id,
            csrf_token=csrf_token,
            expires_at=expires_at,
            enroll_only=enroll_only,
        )

    def get_session(self, token_hash: str, now: datetime) -> AdminSession | None:
        return self.get_session_for_role(token_hash, now, "admin")

    def get_session_any(self, token_hash: str, now: datetime) -> AdminSession | None:
        session = self.sessions.get(token_hash)
        if session is None or session.expires_at <= now:
            return None
        return session

    def get_session_for_role(
        self, token_hash: str, now: datetime, role: str
    ) -> AdminSession | None:
        return self.get_session_for_roles(token_hash, now, [role])

    def get_session_for_roles(
        self, token_hash: str, now: datetime, roles: Sequence[str]
    ) -> AdminSession | None:
        session = self.get_session_any(token_hash, now)
        if session is None:
            return None
        profile = self.profiles.get(session.profile_id)
        if profile is None or profile.role not in set(roles):
            return None
        return session

    def promote_session(self, token_hash: str) -> None:
        session = self.sessions.get(token_hash)
        if session is not None:
            session.enroll_only = False

    def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    def delete_sessions_for_profile(
        self, profile_id: str, keep_token_hash: str | None = None
    ) -> None:
        for token_hash in [
            token
            for token, session in self.sessions.items()
            if session.profile_id == profile_id and token != keep_token_hash
        ]:
            self.sessions.pop(token_hash, None)

    def get_two_factor(self, profile_id: str) -> TwoFactorRecord | None:
        return self.two_factor.get(profile_id)

    def save_pending_two_factor(
        self, profile_id: str, ciphertext: str, now: datetime
    ) -> bool:
        with self._two_factor_lock:
            current = self.two_factor.get(profile_id)
            if current is not None and current.enabled_at is not None:
                return False
            self.two_factor[profile_id] = TwoFactorRecord(
                profile_id=profile_id,
                secret_ciphertext=ciphertext,
                enabled_at=None,
                last_used_step=0,
                created_at=now,
            )
            return True

    def activate_two_factor(
        self, profile_id: str, step: int, code_hashes: Sequence[str], now: datetime
    ) -> bool:
        with self._two_factor_lock:
            record = self.two_factor.get(profile_id)
            if record is None or record.enabled_at is not None:
                return False
            record.enabled_at = now
            record.last_used_step = step
            for code_hash in code_hashes:
                self.recovery_codes[code_hash] = {
                    "profile_id": profile_id,
                    "created_at": now,
                    "used_at": None,
                }
            return True

    def advance_two_factor_step(self, profile_id: str, step: int) -> bool:
        with self._two_factor_lock:
            record = self.two_factor.get(profile_id)
            if (
                record is None
                or record.enabled_at is None
                or record.last_used_step >= step
            ):
                return False
            record.last_used_step = step
            return True

    def consume_recovery_code(
        self, profile_id: str, code_hash: str, now: datetime
    ) -> bool:
        with self._two_factor_lock:
            stored = self.recovery_codes.get(code_hash)
            if (
                stored is None
                or stored["profile_id"] != profile_id
                or stored["used_at"] is not None
            ):
                return False
            stored["used_at"] = now
            return True

    def delete_two_factor(self, profile_id: str) -> bool:
        with self._two_factor_lock:
            existed = self.two_factor.pop(profile_id, None) is not None
            for code_hash in [
                code
                for code, stored in self.recovery_codes.items()
                if stored["profile_id"] == profile_id
            ]:
                self.recovery_codes.pop(code_hash, None)
            return existed

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
            LEGACY_CHANNEL, str(telegram_user_id), notice_version
        )

    def has_channel_privacy_consent(
        self, channel: str, external_user_id: str, notice_version: str
    ) -> bool:
        """R4, R34, R46 R13: una aceptación vigente por botón o por texto habilita."""
        return any(
            consent.channel == channel
            and consent.external_user_id == external_user_id
            and consent.notice_version == notice_version
            and consent.result == "accepted"
            and consent.evidence_type in ("button", "text")
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
            LEGACY_CHANNEL,
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
            _telegram_value(external_user_id) if channel == LEGACY_CHANNEL else None
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
            _telegram_value(external_user_id) if channel == LEGACY_CHANNEL else None
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

    def has_client_consent_for_identity(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        not_before: datetime | None,
    ) -> bool:
        """R4, R21: identidad vinculada -> cliente con aceptación vigente."""
        linked = self.identidades_cliente.get((channel, external_user_id))
        if linked is None:
            return False
        cliente_id, _ = linked
        consent = self.consentimientos_cliente.get((cliente_id, notice_version))
        if consent is None:
            return False
        if not_before is not None and consent["aceptado_en"] < not_before:
            return False
        return True

    def register_client_login(
        self,
        cliente_id: str,
        channel: str,
        external_user_id: str,
        notice_version: str,
        now: datetime,
    ) -> None:
        """R1, R3, R13, R15: asocia la identidad y copia la evidencia si es su primer login."""
        if self.fail_client_link:
            raise RuntimeError("vinculación de cliente no disponible")
        previous = self.identidades_cliente.get((channel, external_user_id))
        reassigned = previous is not None and previous[0] != cliente_id
        self.identidades_cliente[(channel, external_user_id)] = (cliente_id, now)
        if reassigned or (cliente_id, notice_version) in self.consentimientos_cliente:
            return
        evidence = next(
            (
                consent
                for consent in reversed(self.privacy_consents)
                if consent.channel == channel
                and consent.external_user_id == external_user_id
                and consent.notice_version == notice_version
                and consent.result == "accepted"
                and consent.evidence_type in ("button", "text")
                and consent.accepted_at is not None
            ),
            None,
        )
        if evidence is None:
            return
        self.consentimientos_cliente[(cliente_id, notice_version)] = {
            "notice_sha256": evidence.notice_sha256,
            "aceptado_en": evidence.accepted_at,
            "canal_id": evidence.channel,
        }

    def register_client_acceptance_if_linked(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        """R8, R9: solo una identidad ya vinculada cubre a su cliente."""
        linked = self.identidades_cliente.get((channel, external_user_id))
        if linked is None:
            return
        cliente_id, _ = linked
        key = (cliente_id, notice_version)
        if key in self.consentimientos_cliente:
            return
        self.consentimientos_cliente[key] = {
            "notice_sha256": notice_sha256,
            "aceptado_en": accepted_at,
            "canal_id": channel,
        }

    def client_history(
        self, cliente_id: str, limit: int
    ) -> list[ClientHistoryMessage]:
        """R16: mensajes de los contactos de todas las identidades del cliente."""
        channels = {
            self._contact_key(channel, external_user_id): channel
            for (channel, external_user_id), (owner, _) in self.identidades_cliente.items()
            if owner == cliente_id
        }
        contact_channels: dict[str, str] = {}
        for key, channel in channels.items():
            contact = self.contacts.get(key)
            if contact is not None:
                contact_channels[contact.id] = channel
        rows = [
            ClientHistoryMessage(
                channel=contact_channels[message.contact_id],
                role=message.role,
                text=message.text,
                at=message.at,
            )
            for message in self.messages
            if message.contact_id in contact_channels
        ]
        rows.sort(key=lambda row: row.at)
        return rows[-limit:] if limit > 0 else []

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
        # R39: borra las colas del contacto por conversación, contact_id y destino.
        key = conversation_key(channel, external_user_id)
        destinations = {destination_key(channel, contact.external_chat_id)}
        if contact.chat_id is not None:
            destinations.add(destination_key(channel, str(contact.chat_id)))
        self.inbox = {
            row_id: row
            for row_id, row in self.inbox.items()
            if row["conversation_key"] != key
        }
        self.outbox = {
            row_id: row
            for row_id, row in self.outbox.items()
            if row["contact_id"] != contact_id
            and row["destination_key"] not in destinations
        }
        self.events = [
            event for event in self.events if event.contact_id != contact_id
        ]
        self.case_notes = [
            (note, note_contact_id)
            for note, note_contact_id in self.case_notes
            if note_contact_id != contact_id
        ]
        self.case_tag_assignments = [
            assignment
            for assignment in self.case_tag_assignments
            if assignment[2] != contact_id
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

    def purge_personal_data(
        self,
        cutoff: datetime,
        ran_at: datetime,
        client_cutoff: datetime | None = None,
    ) -> dict[str, int]:
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

        expired_notes = {
            note.id
            for note, contact_id in self.case_notes
            if note.created_at < cutoff or contact_id in inactive_ids
        }
        self.case_notes = [
            (note, contact_id)
            for note, contact_id in self.case_notes
            if note.id not in expired_notes
        ]
        self.case_tag_assignments = [
            assignment
            for assignment in self.case_tag_assignments
            if assignment[2] not in inactive_ids
        ]

        kept_consents = [
            consent
            for consent in self.privacy_consents
            if (consent.occurred_at or consent.accepted_at) is None
            or (consent.occurred_at or consent.accepted_at) >= cutoff
        ]
        deleted_consents = len(self.privacy_consents) - len(kept_consents)
        self.privacy_consents = kept_consents

        kept_inbox = {
            row_id: row
            for row_id, row in self.inbox.items()
            if row["created_at"] >= cutoff
        }
        deleted_inbox = len(self.inbox) - len(kept_inbox)
        self.inbox = kept_inbox

        kept_outbox = {
            row_id: row
            for row_id, row in self.outbox.items()
            if row["created_at"] >= cutoff
        }
        deleted_outbox = len(self.outbox) - len(kept_outbox)
        self.outbox = kept_outbox

        counts = {
            "messages": deleted_messages,
            "events": deleted_events,
            "contacts": len(deleted_contacts),
            "case_links": len(deleted_links),
            "auto_handover_outcomes": len(expired_outcomes),
            "auto_handover_streaks": len(expired_streaks),
            "tool_calls": deleted_tool_calls,
            "conversation_summaries": len(expired_summaries),
            "case_notes": len(expired_notes),
            "privacy_consents": deleted_consents,
            "inbox": deleted_inbox,
            "outbox": deleted_outbox,
        }
        if client_cutoff is not None:
            kept_client_consents = {
                key: row
                for key, row in self.consentimientos_cliente.items()
                if row["aceptado_en"] >= client_cutoff
            }
            counts["consentimientos_cliente"] = (
                len(self.consentimientos_cliente) - len(kept_client_consents)
            )
            self.consentimientos_cliente = kept_client_consents
        for stored in self.profiles.values():
            if (
                stored.contact_updated_at is not None
                and stored.contact_updated_at < cutoff
            ):
                stored.email = None
                stored.phone = None
                stored.contact_updated_at = None
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
        public_id: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Profile:
        normalized = username.lower()
        with self._identity_lock:
            if any(
                profile.username == normalized
                for profile in self.profiles.values()
            ):
                raise UsernameTaken("El nombre de usuario ya existe.")
            assigned = public_id or self._unique_public_id()
            if any(p.public_id == assigned for p in self.profiles.values()):
                raise PublicIdTaken("El ID de cliente ya existe.")
            profile_id = f"p{len(self.profiles) + 1}"
            self.profiles[profile_id] = StoredProfile(
                id=profile_id,
                username=normalized,
                role="cliente",
                password_hash=password_hash,
                public_id=assigned,
                email=email.strip().lower() if email else None,
                phone=phone.strip() if phone else None,
                contact_updated_at=now if email or phone else None,
            )
            self.client_credentials[profile_id] = ClientCredential(
                profile_id=profile_id,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        return Profile(
            id=profile_id,
            username=normalized,
            role="cliente",
            public_id=assigned,
            email=email.strip().lower() if email else None,
            phone=phone.strip() if phone else None,
        )

    def find_client_id_by_email(self, email: str) -> str | None:
        normalized = email.strip().lower()
        for stored in self.profiles.values():
            if stored.role == "cliente" and stored.email == normalized:
                return stored.id
        return None

    def find_client_id_by_phone(self, phone: str) -> str | None:
        normalized = phone.strip()
        for stored in self.profiles.values():
            if stored.role == "cliente" and stored.phone == normalized:
                return stored.id
        return None

    def update_client_contact(
        self,
        profile_id: str,
        now: datetime,
        *,
        email: str | None = None,
        phone: str | None = None,
    ) -> bool:
        with self._identity_lock:
            stored = self.profiles.get(profile_id)
            if stored is None or stored.role != "cliente":
                return False
            if email is not None:
                stored.email = email.strip().lower()
            if phone is not None:
                stored.phone = phone.strip()
            if email is not None or phone is not None:
                stored.contact_updated_at = now
            return True

    def _unique_public_id(self) -> str:
        used = {p.public_id for p in self.profiles.values() if p.public_id}
        for _ in range(5):
            candidate = generate_public_id()
            if candidate not in used:
                return candidate
        raise PublicIdGenerationError("No se pudo asignar un ID de cliente único.")

    def ensure_public_ids(self, generate: Callable[[], str]) -> int:
        """R7: asigna ID a clientes sin él; nunca cambia uno existente."""
        assigned = 0
        with self._identity_lock:
            used = {p.public_id for p in self.profiles.values() if p.public_id}
            for stored in self.profiles.values():
                if stored.role != "cliente" or stored.public_id:
                    continue
                for _ in range(5):
                    candidate = generate()
                    if candidate not in used:
                        break
                else:
                    raise PublicIdGenerationError(
                        "No se pudo asignar un ID de cliente único."
                    )
                stored.public_id = candidate
                used.add(candidate)
                assigned += 1
        return assigned

    def find_client_by_public_id(
        self, public_id: str
    ) -> ClientSearchResult | None:
        stored = next(
            (
                profile
                for profile in self.profiles.values()
                if profile.role == "cliente" and profile.public_id == public_id
            ),
            None,
        )
        if stored is None:
            return None
        credential = self.client_credentials.get(stored.id)
        if credential is None:
            return None
        contacts = tuple(
            contact
            for (channel, external_user_id), (owner, _) in (
                self.identidades_cliente.items()
            )
            if owner == stored.id
            for contact in [self.find_channel_contact(channel, external_user_id)]
            if contact is not None
        )
        return ClientSearchResult(
            profile=Profile(
                id=stored.id,
                username=stored.username,
                role=stored.role,
                telegram_user_id=stored.telegram_user_id,
                public_id=stored.public_id,
                email=stored.email,
                phone=stored.phone,
            ),
            credential=credential,
            has_active_session=self.get_active_session_by_profile(stored.id)
            is not None,
            contacts=contacts,
        )

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
                        public_id=stored.public_id,
                        email=stored.email,
                        phone=stored.phone,
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
            session_contact_ids = {session.contact_id for session in sessions}
            linked_identities = {
                (channel, external_user_id)
                for (channel, external_user_id), (owner, _) in (
                    self.identidades_cliente.items()
                )
                if owner == request.profile_id
            }
            identities = {
                (
                    contact.channel,
                    contact.external_user_id or str(contact.telegram_user_id),
                )
                for contact in self.contacts.values()
                if contact.id in session_contact_ids
            } | linked_identities
            kept_consents = [
                consent
                for consent in self.privacy_consents
                if (consent.channel, consent.external_user_id) not in identities
            ]
            deleted_consents = len(self.privacy_consents) - len(kept_consents)
            if self.fail_privacy_consent_delete:
                raise RuntimeError("evidencia de consentimiento no disponible")
            purged_case_ids = {
                case_id
                for case_id, contact_id in self.case_links.items()
                if contact_id in session_contact_ids
            }
            if purged_case_ids:
                # R22: los avisos de los casos purgados no sobreviven a la supresión.
                self.panel_events = [
                    event
                    for event in self.panel_events
                    if event.case_id not in purged_case_ids
                ]
                live_ids = {event.id for event in self.panel_events}
                self._panel_event_times = {
                    event_id: at
                    for event_id, at in self._panel_event_times.items()
                    if event_id in live_ids
                }
            deleted_notes = sum(
                1
                for note, contact_id in self.case_notes
                if contact_id in session_contact_ids
            )
            self.case_notes = [
                (note, contact_id)
                for note, contact_id in self.case_notes
                if contact_id not in session_contact_ids
            ]
            self.case_tag_assignments = [
                assignment
                for assignment in self.case_tag_assignments
                if assignment[2] not in session_contact_ids
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

            self.privacy_consents = kept_consents

            deleted_client_consents = sum(
                1
                for (owner, _) in self.consentimientos_cliente
                if owner == request.profile_id
            )
            self.consentimientos_cliente = {
                key: row
                for key, row in self.consentimientos_cliente.items()
                if key[0] != request.profile_id
            }
            deleted_identities = len(linked_identities)
            for identity in linked_identities:
                self.identidades_cliente.pop(identity, None)
            stored_profile = self.profiles.get(request.profile_id)
            if stored_profile is not None:
                stored_profile.public_id = None
                stored_profile.email = None
                stored_profile.phone = None
                stored_profile.contact_updated_at = None

            counts = {
                "messages": deleted_messages,
                "conversation_summaries": deleted_summaries,
                "client_memory": deleted_memory,
                "case_notes": deleted_notes,
                "privacy_consents": deleted_consents,
                "consentimientos_cliente": deleted_client_consents,
                "identidades_cliente": deleted_identities,
            }
            request.status = "executed"
            request.executed_at = now
            request.executed_by = executed_by
            request.removed_counts = dict(counts)
            return counts

    def add_case_note(self, note: CaseNote, contact_id: str) -> None:
        self.case_notes.append((note, contact_id))

    def _note_with_username(self, note: CaseNote) -> CaseNote:
        stored = self.profiles.get(note.author_profile_id)
        username = stored.username if stored is not None else note.author_username
        return CaseNote(
            id=note.id,
            case_id=note.case_id,
            author_profile_id=note.author_profile_id,
            author_username=username,
            body=note.body,
            created_at=note.created_at,
        )

    def list_case_notes(self, case_id: str) -> list[CaseNote]:
        notes = [
            (note, contact_id)
            for note, contact_id in self.case_notes
            if note.case_id == case_id
        ]
        notes.sort(key=lambda pair: (pair[0].created_at, pair[0].id))
        return [self._note_with_username(note) for note, _ in notes]

    def get_case_note(self, note_id: str) -> CaseNote | None:
        for note, _ in self.case_notes:
            if note.id == note_id:
                return self._note_with_username(note)
        return None

    def delete_case_note(self, note_id: str) -> bool:
        kept = [
            (note, contact_id)
            for note, contact_id in self.case_notes
            if note.id != note_id
        ]
        changed = len(kept) != len(self.case_notes)
        self.case_notes = kept
        return changed

    def count_case_notes(self, case_id: str) -> int:
        return sum(1 for note, _ in self.case_notes if note.case_id == case_id)

    def create_case_tag(self, tag: CaseTag, name_key: str, now: datetime) -> bool:
        if any(
            stored["name_key"] == name_key for stored in self.case_tags.values()
        ):
            return False
        self.case_tags[tag.id] = {
            "tag": tag,
            "name_key": name_key,
            "created_at": now,
            "updated_at": now,
        }
        return True

    def rename_case_tag(
        self, tag_id: str, name: str, name_key: str, now: datetime
    ) -> bool:
        stored = self.case_tags.get(tag_id)
        if stored is None:
            return False
        if any(
            other_id != tag_id and row["name_key"] == name_key
            for other_id, row in self.case_tags.items()
        ):
            return False
        current = stored["tag"]
        stored["tag"] = CaseTag(id=current.id, name=name, active=current.active)
        stored["name_key"] = name_key
        stored["updated_at"] = now
        return True

    def set_case_tag_active(
        self, tag_id: str, active: bool, now: datetime
    ) -> bool:
        stored = self.case_tags.get(tag_id)
        if stored is None:
            return False
        current = stored["tag"]
        stored["tag"] = CaseTag(id=current.id, name=current.name, active=active)
        stored["updated_at"] = now
        return True

    def get_case_tag(self, tag_id: str) -> CaseTag | None:
        stored = self.case_tags.get(tag_id)
        return stored["tag"] if stored is not None else None

    def list_case_tags(self, only_active: bool = False) -> list[CaseTag]:
        tags = [
            stored["tag"]
            for stored in self.case_tags.values()
            if not only_active or stored["tag"].active
        ]
        tags.sort(key=lambda tag: (tag.name.casefold(), tag.id))
        return tags

    def add_case_tag(
        self,
        case_id: str,
        tag_id: str,
        contact_id: str,
        assigned_by: str,
        now: datetime,
    ) -> None:
        if any(
            assignment[0] == case_id and assignment[1] == tag_id
            for assignment in self.case_tag_assignments
        ):
            return
        self.case_tag_assignments.append(
            (case_id, tag_id, contact_id, assigned_by, now)
        )

    def remove_case_tag(self, case_id: str, tag_id: str) -> bool:
        kept = [
            assignment
            for assignment in self.case_tag_assignments
            if not (assignment[0] == case_id and assignment[1] == tag_id)
        ]
        changed = len(kept) != len(self.case_tag_assignments)
        self.case_tag_assignments = kept
        return changed

    def count_case_tags(self, case_id: str) -> int:
        return sum(
            1 for assignment in self.case_tag_assignments if assignment[0] == case_id
        )

    def case_tag_map(
        self, case_ids: Sequence[str]
    ) -> dict[str, tuple[str, ...]]:
        selected = set(case_ids)
        grouped: dict[str, list[str]] = {case_id: [] for case_id in case_ids}
        for case_id, tag_id, _contact_id, _assigned_by, _at in (
            self.case_tag_assignments
        ):
            if case_id in selected:
                grouped[case_id].append(tag_id)
        return {case_id: tuple(tag_ids) for case_id, tag_ids in grouped.items()}

    def add_saved_reply(self, reply: SavedReply) -> None:
        self.saved_replies[reply.id] = reply

    def update_saved_reply(
        self, reply_id: str, title: str, body: str, now: datetime
    ) -> bool:
        current = self.saved_replies.get(reply_id)
        if current is None:
            return False
        self.saved_replies[reply_id] = SavedReply(
            id=current.id,
            title=title,
            body=body,
            active=current.active,
            updated_at=now,
        )
        return True

    def set_saved_reply_active(
        self, reply_id: str, active: bool, now: datetime
    ) -> bool:
        current = self.saved_replies.get(reply_id)
        if current is None:
            return False
        self.saved_replies[reply_id] = SavedReply(
            id=current.id,
            title=current.title,
            body=current.body,
            active=active,
            updated_at=now,
        )
        return True

    def get_saved_reply(self, reply_id: str) -> SavedReply | None:
        return self.saved_replies.get(reply_id)

    def list_saved_replies(self, only_active: bool = False) -> list[SavedReply]:
        replies = [
            reply
            for reply in self.saved_replies.values()
            if not only_active or reply.active
        ]
        replies.sort(key=lambda reply: (reply.updated_at, reply.id), reverse=True)
        return replies

    def count_saved_replies(self) -> int:
        return len(self.saved_replies)

    def add_quick_reply(self, reply: QuickReply) -> None:
        self.quick_replies[reply.id] = reply

    def update_quick_reply(
        self,
        reply_id: str,
        name: str,
        triggers: Sequence[str],
        blocks: Sequence[dict],
        image_id: str | None,
        priority: int,
        now: datetime,
    ) -> bool:
        current = self.quick_replies.get(reply_id)
        if current is None:
            return False
        self.quick_replies[reply_id] = QuickReply(
            id=current.id,
            name=name,
            triggers=tuple(triggers),
            blocks=tuple(blocks),
            image_id=image_id,
            active=current.active,
            priority=priority,
            created_at=current.created_at,
            updated_at=now,
        )
        return True

    def set_quick_reply_active(
        self, reply_id: str, active: bool, now: datetime
    ) -> bool:
        current = self.quick_replies.get(reply_id)
        if current is None:
            return False
        self.quick_replies[reply_id] = QuickReply(
            id=current.id,
            name=current.name,
            triggers=current.triggers,
            blocks=current.blocks,
            image_id=current.image_id,
            active=active,
            priority=current.priority,
            created_at=current.created_at,
            updated_at=now,
        )
        return True

    def get_quick_reply(self, reply_id: str) -> QuickReply | None:
        return self.quick_replies.get(reply_id)

    def list_quick_replies(self, only_active: bool = False) -> list[QuickReply]:
        replies = [
            reply
            for reply in self.quick_replies.values()
            if not only_active or reply.active
        ]
        replies.sort(key=lambda reply: (-reply.priority, reply.created_at, reply.id))
        return replies

    def add_quick_reply_image(self, image: QuickReplyImage) -> None:
        self.quick_reply_images[image.id] = image

    def get_quick_reply_image(self, image_id: str) -> QuickReplyImage | None:
        return self.quick_reply_images.get(image_id)

    def delete_quick_reply_image(self, image_id: str) -> None:
        self.quick_reply_images.pop(image_id, None)

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
                        public_id=stored.public_id,
                        email=stored.email,
                        phone=stored.phone,
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
        self,
        since: datetime,
        until: datetime,
        exclude_channels: frozenset[str] = frozenset(),
    ) -> list[tuple[datetime, datetime | None]]:
        rows: list[tuple[datetime, datetime | None]] = []
        for case_id, contact_id in self.case_links.items():
            created_at = self.case_link_created_at.get(case_id)
            if created_at is None or created_at < since or created_at >= until:
                continue
            if self._canal_id_of(contact_id) in exclude_channels:
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

    def dashboard_messages(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, str, str, datetime]]:
        """R9: (contact_id, canal, rol, at) de los mensajes del intervalo."""
        rows = [
            (
                message.contact_id,
                self._canal_id_of(message.contact_id) or message.canal_id or "",
                message.role,
                message.at,
            )
            for message in self.messages
            if since <= message.at < until
        ]
        rows.sort(key=lambda row: row[3])
        return rows

    def case_channels(self, since: datetime, until: datetime) -> dict[str, str]:
        """R14: canal del contacto de cada caso creado en el intervalo."""
        channels: dict[str, str] = {}
        for case_id, contact_id in self.case_links.items():
            created_at = self.case_link_created_at.get(case_id)
            if created_at is None or created_at < since or created_at >= until:
                continue
            channel = self._canal_id_of(contact_id)
            if channel is not None:
                channels[case_id] = channel
        return channels

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


# Turno global para crear el esquema: la misma clave en todos los servicios que
# comparten la base, para que nunca ejecuten DDL a la vez. Se libera al commit.
SCHEMA_LOCK_SQL = "SELECT pg_advisory_xact_lock(7301984)"

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
    "csrf_token TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL, "
    "enroll_only BOOLEAN NOT NULL DEFAULT FALSE)",
    "CREATE TABLE IF NOT EXISTS staff_two_factor ("
    "profile_id TEXT PRIMARY KEY REFERENCES profiles(id), "
    "secret_ciphertext TEXT NOT NULL, enabled_at TIMESTAMPTZ, "
    "last_used_step BIGINT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS staff_recovery_codes ("
    "code_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), "
    "created_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ)",
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
    "CREATE TABLE IF NOT EXISTS advisor_roster_sync ("
    "singleton_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, "
    "status TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS case_notes ("
    "id TEXT PRIMARY KEY, case_id TEXT NOT NULL, contact_id TEXT NOT NULL, "
    "author_profile_id TEXT NOT NULL, body TEXT NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS case_tags ("
    "id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, "
    "active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS case_tag_assignments ("
    "case_id TEXT NOT NULL, tag_id TEXT NOT NULL, contact_id TEXT NOT NULL, "
    "assigned_by TEXT NOT NULL, assigned_at TIMESTAMPTZ NOT NULL, "
    "PRIMARY KEY (case_id, tag_id))",
    "CREATE TABLE IF NOT EXISTS saved_replies ("
    "id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, "
    "active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quick_replies ("
    "id TEXT PRIMARY KEY, name TEXT NOT NULL, triggers JSONB NOT NULL, "
    "blocks JSONB NOT NULL, image_id TEXT, active BOOLEAN NOT NULL, "
    "priority INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quick_reply_images ("
    "id TEXT PRIMARY KEY, content_type TEXT NOT NULL, data BYTEA NOT NULL, "
    "size INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS panel_events ("
    "id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS inbox ("
    "id BIGSERIAL PRIMARY KEY, conversation_key TEXT NOT NULL, "
    "channel TEXT NOT NULL, external_user_id TEXT NOT NULL, "
    "payload_kind TEXT NOT NULL, payload JSONB NOT NULL, "
    "status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
    "next_attempt_at TIMESTAMPTZ NOT NULL, locked_until TIMESTAMPTZ NULL, "
    "last_error TEXT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "finished_at TIMESTAMPTZ NULL)",
    "CREATE TABLE IF NOT EXISTS outbox ("
    "id BIGSERIAL PRIMARY KEY, contact_id TEXT NULL, destination_key TEXT NOT NULL, "
    "channel TEXT NOT NULL, destination TEXT NOT NULL, kind TEXT NOT NULL, "
    "blocks JSONB NOT NULL, status TEXT NOT NULL, "
    "attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ NOT NULL, "
    "locked_until TIMESTAMPTZ NULL, last_error TEXT NULL, "
    "created_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ NULL)",
    "CREATE TABLE IF NOT EXISTS identidades_cliente ("
    "cliente_id TEXT NOT NULL, canal_id TEXT NOT NULL, id_externo TEXT NOT NULL, "
    "vinculado_en TIMESTAMPTZ NOT NULL, PRIMARY KEY (canal_id, id_externo))",
    "CREATE TABLE IF NOT EXISTS consentimientos_cliente ("
    "cliente_id TEXT NOT NULL, notice_version TEXT NOT NULL, "
    "notice_sha256 TEXT NOT NULL, aceptado_en TIMESTAMPTZ NOT NULL, "
    "canal_id TEXT NOT NULL, PRIMARY KEY (cliente_id, notice_version))",
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
    "CREATE INDEX IF NOT EXISTS case_notes_case ON case_notes (case_id, created_at)",
    "CREATE INDEX IF NOT EXISTS case_notes_contact ON case_notes (contact_id)",
    "CREATE INDEX IF NOT EXISTS case_tag_assignments_tag "
    "ON case_tag_assignments (tag_id)",
    "CREATE INDEX IF NOT EXISTS case_tag_assignments_contact "
    "ON case_tag_assignments (contact_id)",
    "CREATE INDEX IF NOT EXISTS panel_events_created "
    "ON panel_events (created_at)",
    "CREATE INDEX IF NOT EXISTS staff_recovery_codes_profile "
    "ON staff_recovery_codes (profile_id)",
    "CREATE INDEX IF NOT EXISTS inbox_conversation ON inbox (conversation_key, id)",
    "CREATE INDEX IF NOT EXISTS inbox_created ON inbox (created_at)",
    "CREATE INDEX IF NOT EXISTS outbox_destination ON outbox (destination_key, id)",
    "CREATE INDEX IF NOT EXISTS outbox_status ON outbox (status, created_at)",
    "CREATE INDEX IF NOT EXISTS identidades_cliente_cliente "
    "ON identidades_cliente (cliente_id)",
)

# Migración aditiva e idempotente para instalaciones anteriores a #36. Se ejecuta
# después de `_SCHEMA`/`_INDEXES` y nunca cambia ids, mensajes, casos ni fechas.
_MIGRATIONS = (
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS channel TEXT",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS external_user_id TEXT",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS external_chat_id TEXT",
    "ALTER TABLE contacts ALTER COLUMN telegram_user_id DROP NOT NULL",
    "ALTER TABLE contacts ALTER COLUMN chat_id DROP NOT NULL",
    f"UPDATE contacts SET channel = '{LEGACY_CHANNEL}' WHERE channel IS NULL",
    "UPDATE contacts SET external_user_id = CAST(telegram_user_id AS TEXT) "
    "WHERE external_user_id IS NULL AND telegram_user_id IS NOT NULL",
    "UPDATE contacts SET external_chat_id = CAST(chat_id AS TEXT) "
    "WHERE external_chat_id IS NULL AND chat_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS contacts_channel_external_user "
    "ON contacts (channel, external_user_id)",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS channel TEXT",
    "ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS external_user_id TEXT",
    "ALTER TABLE privacy_consents ALTER COLUMN telegram_user_id DROP NOT NULL",
    f"UPDATE privacy_consents SET channel = '{LEGACY_CHANNEL}' WHERE channel IS NULL",
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
    # segundo factor del panel (#54)
    "ALTER TABLE admin_sessions ADD COLUMN IF NOT EXISTS enroll_only "
    "BOOLEAN NOT NULL DEFAULT FALSE",
    # #73: ID público de cliente. El índice único permite NULL en perfiles de staff.
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS public_id TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS profiles_public_id_key "
    "ON profiles (public_id)",
    # #77: correo y teléfono del perfil, opcionales y limpiados por retención/supresión.
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS contact_updated_at TIMESTAMPTZ",
    # #77: índices no únicos; la unicidad de correo/teléfono se decide en la aplicación.
    "CREATE INDEX IF NOT EXISTS profiles_email ON profiles (email)",
    "CREATE INDEX IF NOT EXISTS profiles_phone ON profiles (phone)",
    # #65: id de canal explícito en contactos y mensajes; se escribe en paralelo a
    # `contacts.channel` (que sigue siendo la fuente de lectura). Idempotente.
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS canal_id TEXT",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS canal_id TEXT",
    "UPDATE contacts SET canal_id = channel WHERE canal_id IS NULL",
    "UPDATE messages SET canal_id = c.channel FROM contacts c "
    "WHERE messages.contact_id = c.id AND messages.canal_id IS NULL",
    "CREATE INDEX IF NOT EXISTS messages_canal_id ON messages (canal_id)",
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


IDLE_PROBE_SECONDS = 10.0


def is_connection_error(exc: BaseException) -> bool:
    """Errores de red/socket (p. ej. Postgres reiniciado), no errores de SQL."""
    return isinstance(exc, OSError) or type(exc).__name__ == "InterfaceError"


def _connection_alive(conn: Any) -> bool:
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchall()
        conn.commit()
        return True
    except Exception:
        return False


def _pg_connect(database_url: str, timeout: float | None = None) -> Any:
    import pg8000.dbapi

    parsed = urlparse(database_url)
    kwargs: dict[str, Any] = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/").lstrip("/"),
        **kwargs,
    )


def _row_to_conversation_ref(row: tuple) -> ConversationRef:
    return ConversationRef(
        contact=Contact(
            id=row[0],
            channel=row[1],
            external_user_id=row[2],
            external_chat_id=row[3],
            telegram_user_id=row[4],
            chat_id=row[5],
        ),
        state=ConversationState(row[6]),
        last_activity_at=row[7],
        last_user_at=row[8],
        last_closed_at=row[9],
        case_id=row[10],
        last_purchase_intent_at=row[11],
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
        connect_health: Callable[[float], Any] | None = None,
        panel_events_retention_hours: int = 24,
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._connect_health = connect_health or (
            lambda timeout: _pg_connect(self._database_url, timeout)
        )
        self._panel_events_retention_hours = panel_events_retention_hours
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        # En producción (conexión real) se aplica el esquema y la migración; las
        # conexiones falsas de los tests pueden activarla para probar el DDL.
        self._run_migrations = (
            connect is None if run_migrations is None else run_migrations
        )
        self._conn: Any = None
        self._last_used = 0.0
        self._lock = threading.Lock()

    def _discard_connection(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with suppress(Exception):
                conn.close()

    def _connection(self) -> Any:
        # Si Postgres se reinicia, la conexión guardada queda rota; tras un rato
        # sin uso se comprueba con `SELECT 1` y, si falla, se abre otra.
        if (
            self._conn is not None
            and time.monotonic() - self._last_used > IDLE_PROBE_SECONDS
            and not _connection_alive(self._conn)
        ):
            self._discard_connection()
        if self._conn is None:
            conn = self._connect()
            cur = conn.cursor()
            # El orquestador y sus workers arrancan a la vez y crean el mismo
            # esquema: sin turno, Postgres detecta un deadlock y el proceso cae.
            cur.execute(SCHEMA_LOCK_SQL)
            for statement in _SCHEMA:
                cur.execute(statement)
            for statement in _INDEXES:
                cur.execute(statement)
            if self._run_migrations:
                for statement in _MIGRATIONS:
                    cur.execute(statement)
            conn.commit()
            self._conn = conn
        self._last_used = time.monotonic()
        return self._conn

    def ensure_schema(self) -> None:
        """Crea el esquema y aplica la migración idempotente de #36."""
        self._connection()

    def health_check(self, timeout_seconds: float) -> None:
        """Conexión independiente y acotada; solo `SELECT 1`, sin esquema ni migraciones."""
        conn = self._connect_health(timeout_seconds)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            with suppress(Exception):
                conn.close()

    def _run(self, sql: str, params: tuple, fetch: bool = False) -> list:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                rows = list(cur.fetchall()) if fetch else []
                conn.commit()
                return rows
            except Exception as exc:
                with suppress(Exception):
                    conn.rollback()
                if is_connection_error(exc):
                    self._discard_connection()
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
        if channel == LEGACY_CHANNEL:
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
        params = (update_id, LEGACY_CHANNEL, str(update_id))
        rows = self._run(sql, params, fetch=True)
        return bool(rows)

    # --- cola de entrada y outbox (#64) ----------------------------------
    def _mark_dedup_cursor(self, cur: Any, dedup: DedupKey) -> bool:
        if dedup.kind == "message":
            legacy_update_id = (
                _telegram_value(dedup.external_message_id)
                if dedup.channel == LEGACY_CHANNEL
                else None
            )
            if legacy_update_id is None:
                cur.execute(
                    "INSERT INTO processed_messages "
                    "(channel, external_message_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING RETURNING external_message_id",
                    (dedup.channel, dedup.external_message_id),
                )
            else:
                cur.execute(
                    "INSERT INTO processed_messages (channel, external_message_id) "
                    "SELECT %s, %s WHERE NOT EXISTS ("
                    "SELECT 1 FROM processed_updates WHERE update_id = %s"
                    ") ON CONFLICT DO NOTHING RETURNING external_message_id",
                    (dedup.channel, dedup.external_message_id, legacy_update_id),
                )
            return bool(cur.fetchall())
        cur.execute(
            "INSERT INTO processed_updates (update_id) "
            "SELECT %s WHERE NOT EXISTS ("
            "SELECT 1 FROM processed_messages "
            "WHERE channel = %s AND external_message_id = %s"
            ") ON CONFLICT DO NOTHING RETURNING update_id",
            (dedup.update_id, LEGACY_CHANNEL, str(dedup.update_id)),
        )
        return bool(cur.fetchall())

    def enqueue_inbound(
        self, entry: InboundEntry, dedup: DedupKey | None
    ) -> bool:
        """R1, R4, R5, R7: marca de dedup e INSERT de inbox en una transacción."""
        now = datetime.now(timezone.utc)
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                if dedup is not None and not self._mark_dedup_cursor(cur, dedup):
                    conn.rollback()
                    return False
                cur.execute(
                    "INSERT INTO inbox (conversation_key, channel, "
                    "external_user_id, payload_kind, payload, status, attempts, "
                    "next_attempt_at, created_at) "
                    "VALUES (%s, %s, %s, %s, CAST(%s AS JSONB), 'pending', 0, "
                    "%s, %s)",
                    (
                        entry.conversation_key,
                        entry.channel,
                        entry.external_user_id,
                        entry.payload_kind,
                        json.dumps(entry.payload),
                        now,
                        now,
                    ),
                )
                conn.commit()
                return True
            except Exception as exc:
                conn.rollback()
                if is_connection_error(exc):
                    self._discard_connection()
                raise

    def claim_inbound(
        self, now: datetime, lease_seconds: float
    ) -> InboundQueueRow | None:
        locked_until = now + timedelta(seconds=lease_seconds)
        sql = (
            "UPDATE inbox SET status = 'processing', attempts = attempts + 1, "
            "locked_until = %s WHERE id = ("
            "SELECT i.id FROM inbox i WHERE (("
            "i.status = 'pending' AND i.next_attempt_at <= %s) OR ("
            "i.status = 'processing' AND i.locked_until < %s)) "
            "AND NOT EXISTS (SELECT 1 FROM inbox e "
            "WHERE e.conversation_key = i.conversation_key AND e.id < i.id "
            "AND e.status IN ('pending', 'processing')) "
            "ORDER BY i.id FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING id, conversation_key, channel, payload_kind, payload, "
            "attempts, created_at"
        )
        rows = self._run(sql, (locked_until, now, now), fetch=True)
        if not rows:
            return None
        row = rows[0]
        payload = row[4]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return InboundQueueRow(
            id=row[0],
            conversation_key=row[1],
            channel=row[2],
            payload_kind=row[3],
            payload=payload or {},
            attempts=row[5],
            created_at=row[6],
        )

    def finish_inbound(self, row_id: int, now: datetime) -> None:
        self._run(
            "UPDATE inbox SET status = 'done', payload = '{}'::jsonb, "
            "finished_at = %s, locked_until = NULL, last_error = NULL "
            "WHERE id = %s",
            (now, row_id),
        )

    def retry_inbound(
        self, row_id: int, next_attempt_at: datetime, error: str
    ) -> None:
        self._run(
            "UPDATE inbox SET status = 'pending', next_attempt_at = %s, "
            "last_error = %s, locked_until = NULL WHERE id = %s",
            (next_attempt_at, error, row_id),
        )

    def fail_inbound(self, row_id: int, now: datetime, error: str) -> None:
        self._run(
            "UPDATE inbox SET status = 'failed', payload = '{}'::jsonb, "
            "last_error = %s, finished_at = %s, locked_until = NULL WHERE id = %s",
            (error, now, row_id),
        )

    def _insert_outbox_cursor(self, cur: Any, entry: OutboxEntry, at: datetime) -> int:
        cur.execute(
            "INSERT INTO outbox (contact_id, destination_key, channel, "
            "destination, kind, blocks, status, attempts, next_attempt_at, "
            "created_at) VALUES (%s, %s, %s, %s, %s, CAST(%s AS JSONB), "
            "'pending', 0, %s, %s) RETURNING id",
            (
                entry.contact_id,
                entry.destination_key,
                entry.channel,
                entry.destination,
                entry.kind,
                json.dumps(_blocks_json(entry.blocks)),
                at,
                at,
            ),
        )
        return cur.fetchall()[0][0]

    def enqueue_outbound(self, entry: OutboxEntry) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                row_id = self._insert_outbox_cursor(cur, entry, now)
                conn.commit()
                return row_id
            except Exception as exc:
                conn.rollback()
                if is_connection_error(exc):
                    self._discard_connection()
                raise

    def add_message_with_outbox(
        self,
        contact_id: str,
        role: str,
        text: str,
        at: datetime,
        entry: OutboxEntry,
    ) -> None:
        """R17, R18, R20: mensaje y salida en la misma transacción."""
        message_sql = (
            "INSERT INTO messages (contact_id, role, text, at, canal_id) "
            "VALUES (%s, %s, %s, %s, (SELECT channel FROM contacts WHERE id = %s))"
        )
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(message_sql, (contact_id, role, text, at, contact_id))
                self._insert_outbox_cursor(cur, entry, at)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                if is_connection_error(exc):
                    self._discard_connection()
                raise
        if role not in PANEL_MESSAGE_ROLES:
            return
        try:
            self._run(
                "INSERT INTO panel_events (case_id, kind, created_at) "
                "SELECT case_id, %s, %s FROM case_links "
                "WHERE contact_id = %s ORDER BY created_at DESC, case_id DESC LIMIT 1",
                ("message", at, contact_id),
            )
            self.delete_panel_events_before(
                at - timedelta(hours=self._panel_events_retention_hours)
            )
        except Exception:
            logger.error("panel_event_publish_failed kind=message")

    def claim_outbound(
        self, now: datetime, lease_seconds: float
    ) -> OutboxRow | None:
        locked_until = now + timedelta(seconds=lease_seconds)
        sql = (
            "UPDATE outbox SET status = 'sending', attempts = attempts + 1, "
            "locked_until = %s WHERE id = ("
            "SELECT o.id FROM outbox o WHERE (("
            "o.status = 'pending' AND o.next_attempt_at <= %s) OR ("
            "o.status = 'sending' AND o.locked_until < %s)) "
            "AND NOT EXISTS (SELECT 1 FROM outbox e "
            "WHERE e.destination_key = o.destination_key AND e.id < o.id "
            "AND e.status IN ('pending', 'sending')) "
            "ORDER BY o.id FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING id, destination_key, channel, destination, blocks, "
            "attempts, created_at"
        )
        rows = self._run(sql, (locked_until, now, now), fetch=True)
        if not rows:
            return None
        row = rows[0]
        blocks = row[4]
        if isinstance(blocks, str):
            blocks = json.loads(blocks)
        return OutboxRow(
            id=row[0],
            destination_key=row[1],
            channel=row[2],
            destination=row[3],
            blocks=blocks or [],
            attempts=row[5],
            created_at=row[6],
        )

    def finish_outbound(self, row_id: int, now: datetime) -> None:
        self._run(
            "UPDATE outbox SET status = 'sent', blocks = '[]'::jsonb, "
            "finished_at = %s, locked_until = NULL WHERE id = %s",
            (now, row_id),
        )

    def retry_outbound(
        self, row_id: int, next_attempt_at: datetime, error: str
    ) -> None:
        self._run(
            "UPDATE outbox SET status = 'pending', next_attempt_at = %s, "
            "last_error = %s, locked_until = NULL WHERE id = %s",
            (next_attempt_at, error, row_id),
        )

    def fail_outbound(self, row_id: int, now: datetime, error: str) -> None:
        self._run(
            "UPDATE outbox SET status = 'failed', last_error = %s, "
            "finished_at = %s, locked_until = NULL WHERE id = %s",
            (error, now, row_id),
        )

    def list_failed_outbound(self, limit: int) -> list[FailedSend]:
        rows = self._run(
            "SELECT id, channel, destination, kind, attempts, last_error, "
            "created_at FROM outbox WHERE status = 'failed' "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
            fetch=True,
        )
        return [
            FailedSend(
                id=row[0],
                channel=row[1],
                destination=row[2],
                kind=row[3],
                attempts=row[4],
                last_error=row[5],
                created_at=row[6],
            )
            for row in rows
        ]

    def requeue_outbound(self, row_id: int, now: datetime) -> str:
        rows = self._run(
            "SELECT status FROM outbox WHERE id = %s", (row_id,), fetch=True
        )
        if not rows:
            return "not_found"
        if rows[0][0] != "failed":
            return "not_failed"
        updated = self._run(
            "UPDATE outbox SET status = 'pending', attempts = 0, "
            "next_attempt_at = %s, last_error = NULL, locked_until = NULL, "
            "finished_at = NULL WHERE id = %s AND status = 'failed' "
            "RETURNING id",
            (now, row_id),
            fetch=True,
        )
        return "ok" if updated else "not_failed"

    def get_or_create_contact(
        self, telegram_user_id: int, chat_id: int, now: datetime
    ) -> Contact:
        self._run(
            "INSERT INTO contacts "
            "(id, channel, external_user_id, external_chat_id, telegram_user_id, "
            "chat_id, created_at, canal_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (telegram_user_id) DO NOTHING",
            (
                self._new_id(),
                LEGACY_CHANNEL,
                str(telegram_user_id),
                str(chat_id),
                telegram_user_id,
                chat_id,
                now,
                LEGACY_CHANNEL,
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
            channel=LEGACY_CHANNEL,
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
            _telegram_value(external_user_id) if channel == LEGACY_CHANNEL else None
        )
        chat_id = (
            _telegram_value(external_chat_id) if channel == LEGACY_CHANNEL else None
        )
        self._run(
            "INSERT INTO contacts "
            "(id, channel, external_user_id, external_chat_id, telegram_user_id, "
            "chat_id, created_at, canal_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (channel, external_user_id) DO NOTHING",
            (
                self._new_id(),
                channel,
                external_user_id,
                external_chat_id,
                telegram_user_id,
                chat_id,
                now,
                channel,
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
        params = (contact_id, role, text, at)
        if role not in PANEL_MESSAGE_ROLES:
            self._run(
                "INSERT INTO messages (contact_id, role, text, at, canal_id) "
                "VALUES (%s, %s, %s, %s, (SELECT channel FROM contacts WHERE id = %s))",
                params + (contact_id,),
            )
            return
        message_sql = (
            "INSERT INTO messages (contact_id, role, text, at, canal_id) "
            "VALUES (%s, %s, %s, %s, (SELECT channel FROM contacts WHERE id = %s))"
        )
        event_sql = (
            "INSERT INTO panel_events (case_id, kind, created_at) "
            "SELECT case_id, %s, %s FROM case_links "
            "WHERE contact_id = %s ORDER BY created_at DESC, case_id DESC LIMIT 1"
        )
        purge_sql = "DELETE FROM panel_events WHERE created_at < %s"
        retention_at = at - timedelta(hours=self._panel_events_retention_hours)
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(message_sql, params + (contact_id,))
                cur.execute(event_sql, ("message", at, contact_id))
                cur.execute(purge_sql, (retention_at,))
                conn.commit()
            except Exception:
                conn.rollback()
                logger.error("panel_event_publish_failed kind=message")
                try:
                    # R18: el mensaje se conserva aunque falle la publicación.
                    cur.execute(message_sql, params)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    def publish_panel_event(self, case_id: str, kind: str, at: datetime) -> None:
        self._run(
            "INSERT INTO panel_events (case_id, kind, created_at) "
            "VALUES (%s, %s, %s)",
            (case_id, kind, at),
        )
        self.delete_panel_events_before(
            at - timedelta(hours=self._panel_events_retention_hours)
        )

    def panel_events_cursor(self) -> int:
        rows = self._run(
            "SELECT COALESCE(MAX(id), 0) FROM panel_events", (), fetch=True
        )
        return int(rows[0][0]) if rows else 0

    def panel_events_since(
        self, after_id: int, since: datetime, limit: int
    ) -> list[PanelEvent]:
        rows = self._run(
            "SELECT id, case_id, kind FROM panel_events "
            "WHERE id > %s OR created_at >= %s ORDER BY id ASC LIMIT %s",
            (after_id, since, limit),
            fetch=True,
        )
        return [PanelEvent(id=row[0], case_id=row[1], kind=row[2]) for row in rows]

    def delete_panel_events_before(self, before: datetime) -> int:
        rows = self._run(
            "DELETE FROM panel_events WHERE created_at < %s RETURNING id",
            (before,),
            fetch=True,
        )
        return len(rows)

    def latest_case_for_contact(self, contact_id: str) -> str | None:
        rows = self._run(
            "SELECT case_id FROM case_links WHERE contact_id = %s "
            "ORDER BY created_at DESC, case_id DESC LIMIT 1",
            (contact_id,),
            fetch=True,
        )
        return rows[0][0] if rows else None

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

    def last_event_at(self, contact_id: str, type: str) -> datetime | None:
        rows = self._run(
            "SELECT MAX(at) FROM events WHERE contact_id = %s AND type = %s",
            (contact_id, type),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def link_case(
        self,
        case_id: str,
        contact_id: str,
        at: datetime,
        profile_id: str | None = None,
    ) -> None:
        params = (case_id, contact_id, at, profile_id)
        link_sql = (
            "INSERT INTO case_links (case_id, contact_id, created_at, profile_id) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (case_id) DO NOTHING "
            "RETURNING case_id"
        )
        fallback_sql = (
            "INSERT INTO case_links (case_id, contact_id, created_at, profile_id) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (case_id) DO NOTHING"
        )
        retention_at = at - timedelta(hours=self._panel_events_retention_hours)
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(link_sql, params)
                inserted = list(cur.fetchall())
                if inserted:
                    cur.execute(
                        "INSERT INTO panel_events (case_id, kind, created_at) "
                        "VALUES (%s, %s, %s)",
                        (case_id, "case_created", at),
                    )
                    cur.execute(
                        "DELETE FROM panel_events WHERE created_at < %s",
                        (retention_at,),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                logger.error("panel_event_publish_failed kind=case_created")
                try:
                    # R18: el caso queda enlazado aunque no se pueda publicar.
                    cur.execute(fallback_sql, params)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

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

    def list_conversations(
        self, states: Sequence[str], limit: int
    ) -> list[ConversationRef]:
        rows = self._run(
            "SELECT c.id, c.channel, c.external_user_id, c.external_chat_id, "
            "c.telegram_user_id, c.chat_id, cs.state, MAX(m.at), "
            "MAX(m.at) FILTER (WHERE m.role = 'user'), "
            "(SELECT MAX(e.at) FROM events e WHERE e.contact_id = c.id "
            "AND e.type = 'case_closed'), "
            "(SELECT l.case_id FROM case_links l WHERE l.contact_id = c.id "
            "ORDER BY l.created_at DESC, l.case_id DESC LIMIT 1), "
            "(SELECT MAX(e.at) FROM events e WHERE e.contact_id = c.id "
            "AND e.type = 'purchase_intent') "
            "FROM contacts c JOIN conversation_states cs ON cs.contact_id = c.id "
            "JOIN messages m ON m.contact_id = c.id "
            "WHERE cs.state = ANY(%s) "
            "GROUP BY c.id, c.channel, c.external_user_id, c.external_chat_id, "
            "c.telegram_user_id, c.chat_id, cs.state "
            "ORDER BY MAX(m.at) DESC, c.id DESC LIMIT %s",
            (list(states), limit),
            fetch=True,
        )
        return [_row_to_conversation_ref(row) for row in rows]

    def conversation_ref(self, contact_id: str) -> ConversationRef | None:
        rows = self._run(
            "SELECT c.id, c.channel, c.external_user_id, c.external_chat_id, "
            "c.telegram_user_id, c.chat_id, cs.state, "
            "(SELECT MAX(m.at) FROM messages m WHERE m.contact_id = c.id), "
            "(SELECT MAX(m.at) FROM messages m WHERE m.contact_id = c.id "
            "AND m.role = 'user'), "
            "(SELECT MAX(e.at) FROM events e WHERE e.contact_id = c.id "
            "AND e.type = 'case_closed'), "
            "(SELECT l.case_id FROM case_links l WHERE l.contact_id = c.id "
            "ORDER BY l.created_at DESC, l.case_id DESC LIMIT 1), "
            "(SELECT MAX(e.at) FROM events e WHERE e.contact_id = c.id "
            "AND e.type = 'purchase_intent') "
            "FROM contacts c JOIN conversation_states cs ON cs.contact_id = c.id "
            "WHERE c.id = %s AND EXISTS ("
            "SELECT 1 FROM messages m WHERE m.contact_id = c.id)",
            (contact_id,),
            fetch=True,
        )
        if not rows:
            return None
        return _row_to_conversation_ref(rows[0])

    def foreign_session_windows(
        self, contact_id: str, profile_id: str | None, idle_minutes: int, now: datetime
    ) -> list[tuple[datetime, datetime, datetime]]:
        base = (
            "SELECT profile_id, started_at, last_activity_at, ended_at "
            "FROM client_sessions WHERE contact_id = %s"
        )
        if profile_id is None:
            rows = self._run(base, (contact_id,), fetch=True)
        else:
            rows = self._run(
                base + " AND profile_id <> %s", (contact_id, profile_id), fetch=True
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
            "SELECT id, username, role, telegram_user_id, public_id "
            "FROM profiles WHERE id = %s",
            (profile_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Profile(
            id=row[0],
            username=row[1],
            role=row[2],
            telegram_user_id=row[3],
            public_id=row[4],
        )

    def get_profile_by_telegram_user_id(
        self, telegram_user_id: int
    ) -> Profile | None:
        rows = self._run(
            "SELECT id, username, role, telegram_user_id, public_id FROM profiles "
            "WHERE telegram_user_id = %s",
            (telegram_user_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Profile(
            id=row[0],
            username=row[1],
            role=row[2],
            telegram_user_id=row[3],
            public_id=row[4],
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

    def get_advisor_roster_state(self) -> tuple[int, str]:
        rows = self._run(
            "SELECT generation, status FROM advisor_roster_sync WHERE singleton_id = 1",
            (),
            fetch=True,
        )
        if not rows:
            return 0, "synced"
        return int(rows[0][0]), str(rows[0][1])

    def begin_advisor_roster_change(self) -> int:
        rows = self._run(
            "INSERT INTO advisor_roster_sync (singleton_id, generation, status) "
            "VALUES (%s, %s, %s) ON CONFLICT (singleton_id) DO UPDATE "
            "SET generation = advisor_roster_sync.generation + 1, status = %s "
            "RETURNING generation",
            (1, 1, "pending", "pending"),
            fetch=True,
        )
        return int(rows[0][0]) if rows else 0

    def mark_advisor_roster_synced(self, generation: int) -> bool:
        rows = self._run(
            "UPDATE advisor_roster_sync SET status = %s "
            "WHERE singleton_id = %s AND generation = %s AND status = %s "
            "RETURNING generation",
            ("synced", 1, generation, "pending"),
            fetch=True,
        )
        return bool(rows)

    def create_session(
        self,
        token_hash: str,
        profile_id: str,
        csrf_token: str,
        expires_at: datetime,
        enroll_only: bool = False,
    ) -> None:
        self._run(
            "INSERT INTO admin_sessions "
            "(token_hash, profile_id, csrf_token, expires_at, enroll_only) "
            "VALUES (%s, %s, %s, %s, %s)",
            (token_hash, profile_id, csrf_token, expires_at, enroll_only),
        )

    def get_session(self, token_hash: str, now: datetime) -> AdminSession | None:
        return self.get_session_for_role(token_hash, now, "admin")

    def get_session_any(self, token_hash: str, now: datetime) -> AdminSession | None:
        rows = self._run(
            "SELECT token_hash, profile_id, csrf_token, expires_at, enroll_only "
            "FROM admin_sessions WHERE token_hash = %s AND expires_at > %s",
            (token_hash, now),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return AdminSession(
            token_hash=row[0],
            profile_id=row[1],
            csrf_token=row[2],
            expires_at=row[3],
            enroll_only=bool(row[4]),
        )

    def get_session_for_role(
        self, token_hash: str, now: datetime, role: str
    ) -> AdminSession | None:
        return self.get_session_for_roles(token_hash, now, [role])

    def get_session_for_roles(
        self, token_hash: str, now: datetime, roles: Sequence[str]
    ) -> AdminSession | None:
        rows = self._run(
            "SELECT s.token_hash, s.profile_id, s.csrf_token, s.expires_at, "
            "s.enroll_only FROM admin_sessions s "
            "JOIN profiles p ON p.id = s.profile_id "
            "WHERE s.token_hash = %s AND s.expires_at > %s AND p.role = ANY(%s)",
            (token_hash, now, list(roles)),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return AdminSession(
            token_hash=row[0],
            profile_id=row[1],
            csrf_token=row[2],
            expires_at=row[3],
            enroll_only=bool(row[4]),
        )

    def promote_session(self, token_hash: str) -> None:
        self._run(
            "UPDATE admin_sessions SET enroll_only = FALSE WHERE token_hash = %s",
            (token_hash,),
        )

    def delete_session(self, token_hash: str) -> None:
        self._run("DELETE FROM admin_sessions WHERE token_hash = %s", (token_hash,))

    def delete_sessions_for_profile(
        self, profile_id: str, keep_token_hash: str | None = None
    ) -> None:
        if keep_token_hash is None:
            self._run(
                "DELETE FROM admin_sessions WHERE profile_id = %s", (profile_id,)
            )
            return
        self._run(
            "DELETE FROM admin_sessions WHERE profile_id = %s AND token_hash <> %s",
            (profile_id, keep_token_hash),
        )

    def get_two_factor(self, profile_id: str) -> TwoFactorRecord | None:
        rows = self._run(
            "SELECT profile_id, secret_ciphertext, enabled_at, last_used_step, "
            "created_at FROM staff_two_factor WHERE profile_id = %s",
            (profile_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return TwoFactorRecord(
            profile_id=row[0],
            secret_ciphertext=row[1],
            enabled_at=row[2],
            last_used_step=int(row[3]),
            created_at=row[4],
        )

    def save_pending_two_factor(
        self, profile_id: str, ciphertext: str, now: datetime
    ) -> bool:
        rows = self._run(
            "INSERT INTO staff_two_factor "
            "(profile_id, secret_ciphertext, enabled_at, last_used_step, created_at) "
            "SELECT %s, %s, NULL, 0, %s WHERE NOT EXISTS ("
            "SELECT 1 FROM staff_two_factor "
            "WHERE profile_id = %s AND enabled_at IS NOT NULL) "
            "ON CONFLICT (profile_id) DO UPDATE "
            "SET secret_ciphertext = EXCLUDED.secret_ciphertext, enabled_at = NULL, "
            "last_used_step = 0, created_at = EXCLUDED.created_at "
            "WHERE staff_two_factor.enabled_at IS NULL "
            "RETURNING profile_id",
            (profile_id, ciphertext, now, profile_id),
            fetch=True,
        )
        return bool(rows)

    def activate_two_factor(
        self, profile_id: str, step: int, code_hashes: Sequence[str], now: datetime
    ) -> bool:
        rows = self._run(
            "WITH activated AS ("
            "UPDATE staff_two_factor SET enabled_at = %s, last_used_step = %s "
            "WHERE profile_id = %s AND enabled_at IS NULL RETURNING profile_id) "
            "INSERT INTO staff_recovery_codes (code_hash, profile_id, created_at) "
            "SELECT code, %s, %s FROM unnest(%s::text[]) AS code "
            "WHERE EXISTS (SELECT 1 FROM activated) "
            "RETURNING code_hash",
            (now, step, profile_id, profile_id, now, list(code_hashes)),
            fetch=True,
        )
        return bool(rows)

    def advance_two_factor_step(self, profile_id: str, step: int) -> bool:
        rows = self._run(
            "UPDATE staff_two_factor SET last_used_step = %s "
            "WHERE profile_id = %s AND enabled_at IS NOT NULL AND last_used_step < %s "
            "RETURNING profile_id",
            (step, profile_id, step),
            fetch=True,
        )
        return bool(rows)

    def consume_recovery_code(
        self, profile_id: str, code_hash: str, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE staff_recovery_codes SET used_at = %s "
            "WHERE code_hash = %s AND profile_id = %s AND used_at IS NULL "
            "RETURNING code_hash",
            (now, code_hash, profile_id),
            fetch=True,
        )
        return bool(rows)

    def delete_two_factor(self, profile_id: str) -> bool:
        rows = self._run(
            "DELETE FROM staff_two_factor WHERE profile_id = %s RETURNING profile_id",
            (profile_id,),
            fetch=True,
        )
        self._run(
            "DELETE FROM staff_recovery_codes WHERE profile_id = %s", (profile_id,)
        )
        return bool(rows)

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
            LEGACY_CHANNEL, str(telegram_user_id), notice_version
        )

    def has_channel_privacy_consent(
        self, channel: str, external_user_id: str, notice_version: str
    ) -> bool:
        rows = self._run(
            "SELECT 1 FROM privacy_consents "
            "WHERE channel = %s AND external_user_id = %s "
            "AND notice_version = %s AND result = 'accepted' "
            "AND evidence_type IN ('button', 'text') LIMIT 1",
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
            LEGACY_CHANNEL,
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
            _telegram_value(external_user_id) if channel == LEGACY_CHANNEL else None
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

    def has_client_consent_for_identity(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        not_before: datetime | None,
    ) -> bool:
        """R4, R21: cobertura por cliente con filtro opcional de retención."""
        sql = (
            "SELECT 1 FROM identidades_cliente i "
            "JOIN consentimientos_cliente c ON c.cliente_id = i.cliente_id "
            "WHERE i.canal_id = %s AND i.id_externo = %s "
            "AND c.notice_version = %s"
        )
        params: tuple = (channel, external_user_id, notice_version)
        if not_before is not None:
            sql += " AND c.aceptado_en >= %s"
            params += (not_before,)
        rows = self._run(sql + " LIMIT 1", params, fetch=True)
        return bool(rows)

    def register_client_login(
        self,
        cliente_id: str,
        channel: str,
        external_user_id: str,
        notice_version: str,
        now: datetime,
    ) -> None:
        """R1, R3, R13, R15: vinculación y evidencia por cliente en una transacción."""
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT cliente_id FROM identidades_cliente "
                    "WHERE canal_id = %s AND id_externo = %s",
                    (channel, external_user_id),
                )
                previous = list(cur.fetchall())
                reassigned = bool(previous) and previous[0][0] != cliente_id
                cur.execute(
                    "INSERT INTO identidades_cliente "
                    "(cliente_id, canal_id, id_externo, vinculado_en) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (canal_id, id_externo) DO UPDATE SET "
                    "cliente_id = EXCLUDED.cliente_id, "
                    "vinculado_en = EXCLUDED.vinculado_en",
                    (cliente_id, channel, external_user_id, now),
                )
                if not reassigned:
                    cur.execute(
                        "INSERT INTO consentimientos_cliente "
                        "(cliente_id, notice_version, notice_sha256, aceptado_en, "
                        "canal_id) "
                        "SELECT %s, %s, p.notice_sha256, p.accepted_at, p.channel "
                        "FROM privacy_consents p "
                        "WHERE p.channel = %s AND p.external_user_id = %s "
                        "AND p.notice_version = %s AND p.result = 'accepted' "
                        "AND p.evidence_type IN ('button', 'text') "
                        "AND p.accepted_at IS NOT NULL "
                        "ORDER BY p.occurred_at DESC NULLS LAST, p.id DESC LIMIT 1 "
                        "ON CONFLICT (cliente_id, notice_version) DO NOTHING",
                        (
                            cliente_id,
                            notice_version,
                            channel,
                            external_user_id,
                            notice_version,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def register_client_acceptance_if_linked(
        self,
        channel: str,
        external_user_id: str,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        """R8, R9: la aceptación de una identidad vinculada cubre a su cliente."""
        self._run(
            "INSERT INTO consentimientos_cliente "
            "(cliente_id, notice_version, notice_sha256, aceptado_en, canal_id) "
            "SELECT cliente_id, %s, %s, %s, %s FROM identidades_cliente "
            "WHERE canal_id = %s AND id_externo = %s "
            "ON CONFLICT (cliente_id, notice_version) DO NOTHING",
            (
                notice_version,
                notice_sha256,
                accepted_at,
                channel,
                channel,
                external_user_id,
            ),
        )

    def client_history(
        self, cliente_id: str, limit: int
    ) -> list[ClientHistoryMessage]:
        """R16: mensajes de los contactos de todas las identidades del cliente."""
        rows = self._run(
            "SELECT channel, role, text, at FROM ("
            "SELECT c.channel AS channel, m.role AS role, m.text AS text, "
            "m.at AS at, m.id AS message_id "
            "FROM messages m "
            "JOIN contacts c ON c.id = m.contact_id "
            "JOIN identidades_cliente i ON i.canal_id = c.channel "
            "AND i.id_externo = COALESCE("
            "c.external_user_id, CAST(c.telegram_user_id AS TEXT)) "
            "WHERE i.cliente_id = %s "
            "ORDER BY m.at DESC, m.id DESC LIMIT %s"
            ") recent ORDER BY at, message_id",
            (cliente_id, limit),
            fetch=True,
        )
        return [
            ClientHistoryMessage(
                channel=row[0], role=row[1], text=row[2], at=row[3]
            )
            for row in rows
        ]

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
                    "SELECT id, external_chat_id, chat_id FROM contacts "
                    "WHERE channel = %s AND external_user_id = %s",
                    (channel, external_user_id),
                )
                rows = list(cur.fetchall())
                if not rows:
                    conn.commit()
                    return
                contact_id, external_chat_id, chat_id = rows[0]
                # R39: borra las colas del contacto por conversación, id y destino.
                cur.execute(
                    "DELETE FROM inbox WHERE conversation_key = %s",
                    (conversation_key(channel, external_user_id),),
                )
                destinations = {
                    destination_key(channel, str(external_chat_id or ""))
                }
                if chat_id is not None:
                    destinations.add(destination_key(channel, str(chat_id)))
                cur.execute(
                    "DELETE FROM outbox WHERE contact_id = %s "
                    "OR destination_key = ANY(%s)",
                    (contact_id, list(destinations)),
                )
                cur.execute("DELETE FROM messages WHERE contact_id = %s", (contact_id,))
                cur.execute("DELETE FROM events WHERE contact_id = %s", (contact_id,))
                cur.execute(
                    "DELETE FROM case_notes WHERE contact_id = %s", (contact_id,)
                )
                cur.execute(
                    "DELETE FROM case_tag_assignments WHERE contact_id = %s",
                    (contact_id,),
                )
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
        public_id: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Profile:
        profile_id = self._new_id()
        assigned = public_id or generate_public_id()
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO profiles "
                    "(id, username, role, password_hash, created_at, public_id, "
                    "email, phone, contact_updated_at) "
                    "VALUES (%s, %s, 'cliente', %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (username) DO NOTHING RETURNING id",
                    (
                        profile_id,
                        username.lower(),
                        password_hash,
                        now,
                        assigned,
                        email.strip().lower() if email else None,
                        phone.strip() if phone else None,
                        now if email or phone else None,
                    ),
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
            except Exception as error:
                conn.rollback()
                if _is_unique_violation(error):
                    raise PublicIdTaken("El ID de cliente ya existe.") from error
                raise
        return Profile(
            id=profile_id,
            username=username.lower(),
            role="cliente",
            public_id=assigned,
            email=email.strip().lower() if email else None,
            phone=phone.strip() if phone else None,
        )

    def find_client_id_by_email(self, email: str) -> str | None:
        rows = self._run(
            "SELECT id FROM profiles WHERE role = 'cliente' AND email = %s "
            "ORDER BY id LIMIT 1",
            (email.strip().lower(),),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def find_client_id_by_phone(self, phone: str) -> str | None:
        rows = self._run(
            "SELECT id FROM profiles WHERE role = 'cliente' AND phone = %s "
            "ORDER BY id LIMIT 1",
            (phone.strip(),),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def update_client_contact(
        self,
        profile_id: str,
        now: datetime,
        *,
        email: str | None = None,
        phone: str | None = None,
    ) -> bool:
        rows = self._run(
            "UPDATE profiles SET email = COALESCE(%s, email), "
            "phone = COALESCE(%s, phone), "
            "contact_updated_at = CASE WHEN %s OR %s THEN %s "
            "ELSE contact_updated_at END "
            "WHERE id = %s AND role = 'cliente' RETURNING id",
            (
                email.strip().lower() if email is not None else None,
                phone.strip() if phone is not None else None,
                email is not None,
                phone is not None,
                now,
                profile_id,
            ),
            fetch=True,
        )
        return bool(rows)

    def ensure_public_ids(self, generate: Callable[[], str]) -> int:
        """R7: rellena `profiles.public_id` en clientes anteriores, una sola vez."""
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id FROM profiles "
                    "WHERE role = 'cliente' AND public_id IS NULL"
                )
                profile_ids = [row[0] for row in cur.fetchall()]
                assigned = 0
                for profile_id in profile_ids:
                    for _ in range(5):
                        candidate = generate()
                        try:
                            cur.execute(
                                "UPDATE profiles SET public_id = %s "
                                "WHERE id = %s AND public_id IS NULL",
                                (candidate, profile_id),
                            )
                        except Exception as error:
                            if _is_unique_violation(error):
                                conn.rollback()
                                continue
                            raise
                        conn.commit()
                        assigned += 1
                        break
                    else:
                        conn.rollback()
                        raise PublicIdGenerationError(
                            "No se pudo asignar un ID de cliente único."
                        )
                conn.commit()
                return assigned
            except PublicIdGenerationError:
                raise
            except Exception:
                conn.rollback()
                raise

    def find_client_by_public_id(
        self, public_id: str
    ) -> ClientSearchResult | None:
        rows = self._run(
            "SELECT p.id, p.username, p.role, p.telegram_user_id, p.public_id, "
            "c.valid_from, c.valid_until, c.revoked_at, "
            "EXISTS(SELECT 1 FROM client_sessions s "
            "WHERE s.profile_id = p.id AND s.ended_at IS NULL) "
            "FROM profiles p JOIN client_credentials c ON c.profile_id = p.id "
            "WHERE p.role = 'cliente' AND p.public_id = %s",
            (public_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        contacts = self._run(
            "SELECT c.id, c.channel, c.external_user_id, c.external_chat_id, "
            "c.telegram_user_id, c.chat_id FROM contacts c "
            "JOIN identidades_cliente i ON i.canal_id = c.channel "
            "AND i.id_externo = COALESCE("
            "c.external_user_id, CAST(c.telegram_user_id AS TEXT)) "
            "WHERE i.cliente_id = %s ORDER BY c.channel, c.id",
            (row[0],),
            fetch=True,
        )
        return ClientSearchResult(
            profile=Profile(
                id=row[0],
                username=row[1],
                role=row[2],
                telegram_user_id=row[3],
                public_id=row[4],
            ),
            credential=ClientCredential(
                profile_id=row[0],
                valid_from=row[5],
                valid_until=row[6],
                revoked_at=row[7],
            ),
            has_active_session=bool(row[8]),
            contacts=tuple(
                Contact(
                    id=contact[0],
                    channel=contact[1],
                    external_user_id=contact[2],
                    external_chat_id=contact[3],
                    telegram_user_id=contact[4],
                    chat_id=contact[5],
                )
                for contact in contacts
            ),
        )

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
            "c.valid_from, c.valid_until, c.revoked_at, p.public_id "
            "FROM profiles p LEFT JOIN client_credentials c ON c.profile_id = p.id "
            "WHERE p.username = %s",
            (username.lower(),),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        profile = Profile(
            id=row[0],
            username=row[1],
            role=row[2],
            telegram_user_id=row[3],
            public_id=row[8],
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

                session_contact_ids = [row[0] for row in sessions]
                if session_contact_ids:
                    # R22: borra los avisos de los casos purgados.
                    cur.execute(
                        "DELETE FROM panel_events WHERE case_id IN ("
                        "SELECT case_id FROM case_links WHERE contact_id = ANY(%s))",
                        (session_contact_ids,),
                    )
                deleted_notes = 0
                if session_contact_ids:
                    cur.execute(
                        "DELETE FROM case_notes WHERE contact_id = ANY(%s) "
                        "RETURNING id",
                        (session_contact_ids,),
                    )
                    deleted_notes = len(list(cur.fetchall()))
                    cur.execute(
                        "DELETE FROM case_tag_assignments "
                        "WHERE contact_id = ANY(%s)",
                        (session_contact_ids,),
                    )

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

                cur.execute(
                    "DELETE FROM privacy_consents p "
                    "WHERE EXISTS (SELECT 1 FROM contacts c "
                    "WHERE c.id = ANY(%s) AND p.channel = c.channel "
                    "AND p.external_user_id = COALESCE("
                    "c.external_user_id, CAST(c.telegram_user_id AS TEXT))) "
                    "OR EXISTS (SELECT 1 FROM identidades_cliente i "
                    "WHERE i.cliente_id = %s AND i.canal_id = p.channel "
                    "AND i.id_externo = p.external_user_id) "
                    "RETURNING p.id",
                    (session_contact_ids, profile_id),
                )
                deleted_consents = len(list(cur.fetchall()))

                cur.execute(
                    "DELETE FROM consentimientos_cliente WHERE cliente_id = %s "
                    "RETURNING cliente_id",
                    (profile_id,),
                )
                deleted_client_consents = len(list(cur.fetchall()))
                cur.execute(
                    "DELETE FROM identidades_cliente WHERE cliente_id = %s "
                    "RETURNING canal_id",
                    (profile_id,),
                )
                deleted_identities = len(list(cur.fetchall()))
                cur.execute(
                    "UPDATE profiles SET public_id = NULL, email = NULL, "
                    "phone = NULL, contact_updated_at = NULL WHERE id = %s",
                    (profile_id,),
                )

                counts = {
                    "messages": deleted_messages,
                    "conversation_summaries": deleted_summaries,
                    "client_memory": deleted_memory,
                    "case_notes": deleted_notes,
                    "privacy_consents": deleted_consents,
                    "consentimientos_cliente": deleted_client_consents,
                    "identidades_cliente": deleted_identities,
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

    def purge_personal_data(
        self,
        cutoff: datetime,
        ran_at: datetime,
        client_cutoff: datetime | None = None,
    ) -> dict[str, int]:
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

                if inactive_ids:
                    cur.execute(
                        "DELETE FROM case_notes "
                        "WHERE created_at < %s OR contact_id = ANY(%s) "
                        "RETURNING id",
                        (cutoff, inactive_ids),
                    )
                else:
                    cur.execute(
                        "DELETE FROM case_notes WHERE created_at < %s RETURNING id",
                        (cutoff,),
                    )
                deleted_notes = len(cur.fetchall())
                if inactive_ids:
                    cur.execute(
                        "DELETE FROM case_tag_assignments "
                        "WHERE contact_id = ANY(%s)",
                        (inactive_ids,),
                    )

                deleted_links = 0
                deleted_contacts = 0
                if inactive_ids:
                    cur.execute(
                        "DELETE FROM panel_events WHERE case_id IN ("
                        "SELECT case_id FROM case_links WHERE contact_id = ANY(%s))",
                        (inactive_ids,),
                    )
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

                cur.execute(
                    "DELETE FROM privacy_consents "
                    "WHERE COALESCE(occurred_at, accepted_at) < %s RETURNING id",
                    (cutoff,),
                )
                deleted_consents = len(cur.fetchall())

                deleted_client_consents = 0
                if client_cutoff is not None:
                    cur.execute(
                        "DELETE FROM consentimientos_cliente "
                        "WHERE aceptado_en < %s RETURNING cliente_id",
                        (client_cutoff,),
                    )
                    deleted_client_consents = len(cur.fetchall())

                cur.execute(
                    "UPDATE profiles SET email = NULL, phone = NULL, "
                    "contact_updated_at = NULL "
                    "WHERE contact_updated_at IS NOT NULL AND contact_updated_at < %s",
                    (cutoff,),
                )
                cur.execute(
                    "DELETE FROM inbox WHERE created_at < %s RETURNING id",
                    (cutoff,),
                )
                deleted_inbox = len(cur.fetchall())
                cur.execute(
                    "DELETE FROM outbox WHERE created_at < %s RETURNING id",
                    (cutoff,),
                )
                deleted_outbox = len(cur.fetchall())

                counts = {
                    "messages": deleted_messages,
                    "events": deleted_events,
                    "contacts": deleted_contacts,
                    "case_links": deleted_links,
                    "auto_handover_outcomes": deleted_outcomes,
                    "auto_handover_streaks": deleted_streaks,
                    "tool_calls": deleted_tool_calls,
                    "conversation_summaries": deleted_summaries,
                    "case_notes": deleted_notes,
                    "privacy_consents": deleted_consents,
                    "inbox": deleted_inbox,
                    "outbox": deleted_outbox,
                }
                if client_cutoff is not None:
                    counts["consentimientos_cliente"] = deleted_client_consents
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

    def add_case_note(self, note: CaseNote, contact_id: str) -> None:
        self._run(
            "INSERT INTO case_notes "
            "(id, case_id, contact_id, author_profile_id, body, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                note.id,
                note.case_id,
                contact_id,
                note.author_profile_id,
                note.body,
                note.created_at,
            ),
        )

    def _notes_from_rows(self, rows: list) -> list[CaseNote]:
        return [
            CaseNote(
                id=row[0],
                case_id=row[1],
                author_profile_id=row[2],
                author_username=row[3],
                body=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    def list_case_notes(self, case_id: str) -> list[CaseNote]:
        rows = self._run(
            "SELECT n.id, n.case_id, n.author_profile_id, p.username, n.body, "
            "n.created_at FROM case_notes n "
            "LEFT JOIN profiles p ON p.id = n.author_profile_id "
            "WHERE n.case_id = %s ORDER BY n.created_at ASC, n.id ASC",
            (case_id,),
            fetch=True,
        )
        return self._notes_from_rows(rows)

    def get_case_note(self, note_id: str) -> CaseNote | None:
        rows = self._run(
            "SELECT n.id, n.case_id, n.author_profile_id, p.username, n.body, "
            "n.created_at FROM case_notes n "
            "LEFT JOIN profiles p ON p.id = n.author_profile_id "
            "WHERE n.id = %s",
            (note_id,),
            fetch=True,
        )
        return self._notes_from_rows(rows)[0] if rows else None

    def delete_case_note(self, note_id: str) -> bool:
        rows = self._run(
            "DELETE FROM case_notes WHERE id = %s RETURNING id",
            (note_id,),
            fetch=True,
        )
        return bool(rows)

    def count_case_notes(self, case_id: str) -> int:
        rows = self._run(
            "SELECT COUNT(*) FROM case_notes WHERE case_id = %s",
            (case_id,),
            fetch=True,
        )
        return int(rows[0][0]) if rows else 0

    def create_case_tag(self, tag: CaseTag, name_key: str, now: datetime) -> bool:
        rows = self._run(
            "INSERT INTO case_tags "
            "(id, name, name_key, active, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name_key) DO NOTHING RETURNING id",
            (tag.id, tag.name, name_key, tag.active, now, now),
            fetch=True,
        )
        return bool(rows)

    def rename_case_tag(
        self, tag_id: str, name: str, name_key: str, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE case_tags SET name = %s, name_key = %s, updated_at = %s "
            "WHERE id = %s AND NOT EXISTS ("
            "SELECT 1 FROM case_tags WHERE name_key = %s AND id <> %s"
            ") RETURNING id",
            (name, name_key, now, tag_id, name_key, tag_id),
            fetch=True,
        )
        return bool(rows)

    def set_case_tag_active(
        self, tag_id: str, active: bool, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE case_tags SET active = %s, updated_at = %s "
            "WHERE id = %s RETURNING id",
            (active, now, tag_id),
            fetch=True,
        )
        return bool(rows)

    def get_case_tag(self, tag_id: str) -> CaseTag | None:
        rows = self._run(
            "SELECT id, name, active FROM case_tags WHERE id = %s",
            (tag_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return CaseTag(id=row[0], name=row[1], active=bool(row[2]))

    def list_case_tags(self, only_active: bool = False) -> list[CaseTag]:
        sql = "SELECT id, name, active FROM case_tags"
        if only_active:
            sql += " WHERE active = TRUE"
        sql += " ORDER BY name ASC, id ASC"
        rows = self._run(sql, (), fetch=True)
        return [
            CaseTag(id=row[0], name=row[1], active=bool(row[2])) for row in rows
        ]

    def add_case_tag(
        self,
        case_id: str,
        tag_id: str,
        contact_id: str,
        assigned_by: str,
        now: datetime,
    ) -> None:
        self._run(
            "INSERT INTO case_tag_assignments "
            "(case_id, tag_id, contact_id, assigned_by, assigned_at) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (case_id, tag_id, contact_id, assigned_by, now),
        )

    def remove_case_tag(self, case_id: str, tag_id: str) -> bool:
        rows = self._run(
            "DELETE FROM case_tag_assignments "
            "WHERE case_id = %s AND tag_id = %s RETURNING case_id",
            (case_id, tag_id),
            fetch=True,
        )
        return bool(rows)

    def count_case_tags(self, case_id: str) -> int:
        rows = self._run(
            "SELECT COUNT(*) FROM case_tag_assignments WHERE case_id = %s",
            (case_id,),
            fetch=True,
        )
        return int(rows[0][0]) if rows else 0

    def case_tag_map(
        self, case_ids: Sequence[str]
    ) -> dict[str, tuple[str, ...]]:
        if not case_ids:
            return {}
        rows = self._run(
            "SELECT case_id, tag_id FROM case_tag_assignments "
            "WHERE case_id = ANY(%s) ORDER BY assigned_at ASC, tag_id ASC",
            (list(case_ids),),
            fetch=True,
        )
        grouped: dict[str, list[str]] = {case_id: [] for case_id in case_ids}
        for case_id, tag_id in rows:
            grouped.setdefault(case_id, []).append(tag_id)
        return {case_id: tuple(tag_ids) for case_id, tag_ids in grouped.items()}

    def add_saved_reply(self, reply: SavedReply) -> None:
        self._run(
            "INSERT INTO saved_replies "
            "(id, title, body, active, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                reply.id,
                reply.title,
                reply.body,
                reply.active,
                reply.updated_at,
                reply.updated_at,
            ),
        )

    def update_saved_reply(
        self, reply_id: str, title: str, body: str, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE saved_replies SET title = %s, body = %s, updated_at = %s "
            "WHERE id = %s RETURNING id",
            (title, body, now, reply_id),
            fetch=True,
        )
        return bool(rows)

    def set_saved_reply_active(
        self, reply_id: str, active: bool, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE saved_replies SET active = %s, updated_at = %s "
            "WHERE id = %s RETURNING id",
            (active, now, reply_id),
            fetch=True,
        )
        return bool(rows)

    def get_saved_reply(self, reply_id: str) -> SavedReply | None:
        rows = self._run(
            "SELECT id, title, body, active, updated_at "
            "FROM saved_replies WHERE id = %s",
            (reply_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return SavedReply(
            id=row[0],
            title=row[1],
            body=row[2],
            active=bool(row[3]),
            updated_at=row[4],
        )

    def list_saved_replies(self, only_active: bool = False) -> list[SavedReply]:
        sql = "SELECT id, title, body, active, updated_at FROM saved_replies"
        if only_active:
            sql += " WHERE active = TRUE"
        sql += " ORDER BY updated_at DESC, id ASC"
        rows = self._run(sql, (), fetch=True)
        return [
            SavedReply(
                id=row[0],
                title=row[1],
                body=row[2],
                active=bool(row[3]),
                updated_at=row[4],
            )
            for row in rows
        ]

    def count_saved_replies(self) -> int:
        rows = self._run("SELECT COUNT(*) FROM saved_replies", (), fetch=True)
        return int(rows[0][0]) if rows else 0

    def add_quick_reply(self, reply: QuickReply) -> None:
        self._run(
            "INSERT INTO quick_replies "
            "(id, name, triggers, blocks, image_id, active, priority, "
            "created_at, updated_at) VALUES "
            "(%s, %s, CAST(%s AS JSONB), CAST(%s AS JSONB), %s, %s, %s, %s, %s)",
            (
                reply.id,
                reply.name,
                json.dumps(list(reply.triggers), ensure_ascii=False),
                json.dumps(_blocks_json(reply.blocks), ensure_ascii=False),
                reply.image_id,
                reply.active,
                reply.priority,
                reply.created_at,
                reply.updated_at,
            ),
        )

    def update_quick_reply(
        self,
        reply_id: str,
        name: str,
        triggers: Sequence[str],
        blocks: Sequence[dict],
        image_id: str | None,
        priority: int,
        now: datetime,
    ) -> bool:
        rows = self._run(
            "UPDATE quick_replies SET name = %s, triggers = CAST(%s AS JSONB), "
            "blocks = CAST(%s AS JSONB), image_id = %s, priority = %s, "
            "updated_at = %s WHERE id = %s RETURNING id",
            (
                name,
                json.dumps(list(triggers), ensure_ascii=False),
                json.dumps(_blocks_json(blocks), ensure_ascii=False),
                image_id,
                priority,
                now,
                reply_id,
            ),
            fetch=True,
        )
        return bool(rows)

    def set_quick_reply_active(
        self, reply_id: str, active: bool, now: datetime
    ) -> bool:
        rows = self._run(
            "UPDATE quick_replies SET active = %s, updated_at = %s "
            "WHERE id = %s RETURNING id",
            (active, now, reply_id),
            fetch=True,
        )
        return bool(rows)

    def get_quick_reply(self, reply_id: str) -> QuickReply | None:
        rows = self._run(
            "SELECT id, name, triggers, blocks, image_id, active, priority, "
            "created_at, updated_at FROM quick_replies WHERE id = %s",
            (reply_id,),
            fetch=True,
        )
        if not rows:
            return None
        return _quick_reply_from_row(rows[0])

    def list_quick_replies(self, only_active: bool = False) -> list[QuickReply]:
        sql = (
            "SELECT id, name, triggers, blocks, image_id, active, priority, "
            "created_at, updated_at FROM quick_replies"
        )
        if only_active:
            sql += " WHERE active = TRUE"
        sql += " ORDER BY priority DESC, created_at ASC, id ASC"
        rows = self._run(sql, (), fetch=True)
        return [_quick_reply_from_row(row) for row in rows]

    def add_quick_reply_image(self, image: QuickReplyImage) -> None:
        self._run(
            "INSERT INTO quick_reply_images "
            "(id, content_type, data, size, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                image.id,
                image.content_type,
                image.data,
                image.size,
                image.created_at,
            ),
        )

    def get_quick_reply_image(self, image_id: str) -> QuickReplyImage | None:
        rows = self._run(
            "SELECT id, content_type, data, size, created_at "
            "FROM quick_reply_images WHERE id = %s",
            (image_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return QuickReplyImage(
            id=row[0],
            content_type=row[1],
            data=bytes(row[2]),
            size=int(row[3]),
            created_at=row[4],
        )

    def delete_quick_reply_image(self, image_id: str) -> None:
        self._run(
            "DELETE FROM quick_reply_images WHERE id = %s",
            (image_id,),
        )

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
            "WHERE s.profile_id = p.id AND s.ended_at IS NULL), p.public_id "
            "FROM profiles p JOIN client_credentials c ON c.profile_id = p.id "
            "WHERE p.role = 'cliente' ORDER BY p.username",
            (),
            fetch=True,
        )
        return [
            ClientCredentialRow(
                profile=Profile(
                    id=row[0],
                    username=row[1],
                    role=row[2],
                    telegram_user_id=row[3],
                    public_id=row[8],
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
        self,
        since: datetime,
        until: datetime,
        exclude_channels: frozenset[str] = frozenset(),
    ) -> list[tuple[datetime, datetime | None]]:
        sql = (
            "SELECT l.created_at, (SELECT MIN(m.at) FROM messages m "
            "WHERE m.contact_id = l.contact_id AND m.role = 'advisor' "
            "AND m.at >= l.created_at) FROM case_links l "
        )
        params: list[object] = [since, until]
        if exclude_channels:
            sql += "JOIN contacts c ON c.id = l.contact_id "
        sql += "WHERE l.created_at >= %s AND l.created_at < %s "
        if exclude_channels:
            ordered = sorted(exclude_channels)
            placeholders = ", ".join("%s" for _ in ordered)
            sql += f"AND COALESCE(c.canal_id, c.channel) NOT IN ({placeholders}) "
            params.extend(ordered)
        sql += "ORDER BY l.created_at"
        rows = self._run(sql, tuple(params), fetch=True)
        return [(row[0], row[1]) for row in rows]

    def dashboard_messages(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, str, str, datetime]]:
        rows = self._run(
            "SELECT m.contact_id, COALESCE(c.canal_id, c.channel), m.role, m.at "
            "FROM messages m JOIN contacts c ON c.id = m.contact_id "
            "WHERE m.at >= %s AND m.at < %s ORDER BY m.at",
            (since, until),
            fetch=True,
        )
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    def case_channels(self, since: datetime, until: datetime) -> dict[str, str]:
        rows = self._run(
            "SELECT l.case_id, COALESCE(c.canal_id, c.channel) "
            "FROM case_links l JOIN contacts c ON c.id = l.contact_id "
            "WHERE l.created_at >= %s AND l.created_at < %s",
            (since, until),
            fetch=True,
        )
        return {row[0]: row[1] for row in rows}

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
