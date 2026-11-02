"""Persistencia (contactos, historial, eventos, update_id, casos) detrás de un Repository."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

from lazaro_contracts import LastMessage

from ..classifier import Category
from ..domain import Contact, Profile, UsernameTaken


class Repository(Protocol):
    def mark_update_if_new(self, update_id: int) -> bool: ...

    def get_or_create_contact(
        self, telegram_user_id: int, chat_id: int, now: datetime
    ) -> Contact: ...

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None: ...

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]: ...

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None: ...

    def link_case(self, case_id: str, contact_id: str, at: datetime) -> None: ...

    def get_case_contact(self, case_id: str) -> Contact | None: ...

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

    def list_categories(self) -> list[Category]: ...

    def create_category(self, category: Category, now: datetime) -> bool: ...

    def update_category(
        self, category_id: str, name: str, keywords: tuple[str, ...]
    ) -> bool: ...

    def set_category_active(self, category_id: str, active: bool) -> bool: ...

    def get_classifier_threshold(self) -> float | None: ...

    def set_classifier_threshold(self, value: float) -> None: ...

    def has_privacy_consent(self, telegram_user_id: int, notice_version: str) -> bool: ...

    def add_privacy_consent(
        self,
        telegram_user_id: int,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None: ...

    def purge_personal_data(self, cutoff: datetime, ran_at: datetime) -> dict[str, int]: ...


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
class PrivacyConsent:
    telegram_user_id: int
    notice_version: str
    notice_sha256: str
    accepted_at: datetime


class FakeRepository:
    def __init__(self) -> None:
        self.contacts: dict[int, Contact] = {}
        self.messages: list[StoredMessage] = []
        self.events: list[StoredEvent] = []
        self.processed: set[int] = set()
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
        self.fail_db_query_audit = False
        self.contact_created_at: dict[str, datetime] = {}
        self.case_link_created_at: dict[str, datetime] = {}
        self.privacy_consents: list[PrivacyConsent] = []
        self.privacy_purge_runs: list[dict[str, Any]] = []
        self.fail_privacy_consent = False
        self._profiles_lock = threading.Lock()
        self._rag_lock = threading.Lock()

    def mark_update_if_new(self, update_id: int) -> bool:
        if update_id in self.processed:
            return False
        self.processed.add(update_id)
        return True

    def get_or_create_contact(self, telegram_user_id: int, chat_id: int, now: datetime) -> Contact:
        contact = self.contacts.get(telegram_user_id)
        if contact is None:
            contact = Contact(
                id=f"c{len(self.contacts) + 1}", telegram_user_id=telegram_user_id, chat_id=chat_id
            )
            self.contacts[telegram_user_id] = contact
            self.contact_created_at[contact.id] = now
        return contact

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None:
        self.messages.append(StoredMessage(contact_id, role, text, at))

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]:
        own = [m for m in self.messages if m.contact_id == contact_id]
        return [LastMessage(role=m.role, text=m.text, at=m.at) for m in own[-limit:]]  # type: ignore[arg-type]

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None:
        self.events.append(StoredEvent(contact_id, type, reason, at))

    def link_case(self, case_id: str, contact_id: str, at: datetime) -> None:
        self.case_links.setdefault(case_id, contact_id)
        self.case_link_created_at.setdefault(case_id, at)

    def get_case_contact(self, case_id: str) -> Contact | None:
        contact_id = self.case_links.get(case_id)
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
        return any(
            consent.telegram_user_id == telegram_user_id
            and consent.notice_version == notice_version
            for consent in self.privacy_consents
        )

    def add_privacy_consent(
        self,
        telegram_user_id: int,
        notice_version: str,
        notice_sha256: str,
        accepted_at: datetime,
    ) -> None:
        if self.fail_privacy_consent:
            raise RuntimeError("consentimiento no disponible")
        self.privacy_consents.append(
            PrivacyConsent(
                telegram_user_id=telegram_user_id,
                notice_version=notice_version,
                notice_sha256=notice_sha256,
                accepted_at=accepted_at,
            )
        )

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

        counts = {
            "messages": deleted_messages,
            "events": deleted_events,
            "contacts": len(deleted_contacts),
            "case_links": len(deleted_links),
            "auto_handover_outcomes": len(expired_outcomes),
            "auto_handover_streaks": len(expired_streaks),
        }
        self.privacy_purge_runs.append(
            {"ran_at": ran_at, "cutoff": cutoff, "counts": dict(counts)}
        )
        return counts


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS contacts ("
    "id TEXT PRIMARY KEY, telegram_user_id BIGINT UNIQUE NOT NULL, "
    "chat_id BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS messages ("
    "id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, role TEXT NOT NULL, "
    "text TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS events ("
    "id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, type TEXT NOT NULL, "
    "reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS processed_updates (update_id BIGINT PRIMARY KEY)",
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
    "id BIGSERIAL PRIMARY KEY, telegram_user_id BIGINT NOT NULL, "
    "notice_version TEXT NOT NULL, notice_sha256 TEXT NOT NULL, "
    "accepted_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS privacy_purge_runs ("
    "id BIGSERIAL PRIMARY KEY, ran_at TIMESTAMPTZ NOT NULL, "
    "cutoff TIMESTAMPTZ NOT NULL, counts JSONB NOT NULL)",
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS admin_login_attempts_user_at "
    "ON admin_login_attempts (username, at)",
    "CREATE INDEX IF NOT EXISTS admin_login_attempts_ip_at "
    "ON admin_login_attempts (ip, at)",
    "CREATE INDEX IF NOT EXISTS privacy_consents_user_version "
    "ON privacy_consents (telegram_user_id, notice_version)",
)


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


class PostgresRepository:
    """SQL siempre parametrizado (%s); la conexión se abre en el primer uso.

    Un threading.Lock serializa todo el uso de la conexión compartida (#18).
    """

    def __init__(
        self,
        database_url: str,
        connect: Callable[[], Any] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
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
            conn.commit()
            self._conn = conn
        return self._conn

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

    def mark_update_if_new(self, update_id: int) -> bool:
        rows = self._run(
            "INSERT INTO processed_updates (update_id) VALUES (%s) "
            "ON CONFLICT DO NOTHING RETURNING update_id",
            (update_id,),
            fetch=True,
        )
        return bool(rows)

    def get_or_create_contact(self, telegram_user_id: int, chat_id: int, now: datetime) -> Contact:
        self._run(
            "INSERT INTO contacts (id, telegram_user_id, chat_id, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (telegram_user_id) DO NOTHING",
            (self._new_id(), telegram_user_id, chat_id, now),
        )
        rows = self._run(
            "SELECT id, telegram_user_id, chat_id FROM contacts WHERE telegram_user_id = %s",
            (telegram_user_id,),
            fetch=True,
        )
        row = rows[0]
        return Contact(id=row[0], telegram_user_id=row[1], chat_id=row[2])

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

    def link_case(self, case_id: str, contact_id: str, at: datetime) -> None:
        self._run(
            "INSERT INTO case_links (case_id, contact_id, created_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (case_id) DO NOTHING",
            (case_id, contact_id, at),
        )

    def get_case_contact(self, case_id: str) -> Contact | None:
        rows = self._run(
            "SELECT c.id, c.telegram_user_id, c.chat_id FROM case_links l "
            "JOIN contacts c ON c.id = l.contact_id WHERE l.case_id = %s",
            (case_id,),
            fetch=True,
        )
        if not rows:
            return None
        row = rows[0]
        return Contact(id=row[0], telegram_user_id=row[1], chat_id=row[2])

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
        rows = self._run(
            "SELECT 1 FROM privacy_consents "
            "WHERE telegram_user_id = %s AND notice_version = %s LIMIT 1",
            (telegram_user_id, notice_version),
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
        self._run(
            "INSERT INTO privacy_consents "
            "(telegram_user_id, notice_version, notice_sha256, accepted_at) "
            "VALUES (%s, %s, %s, %s)",
            (telegram_user_id, notice_version, notice_sha256, accepted_at),
        )

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
                    "DELETE FROM messages WHERE at < %s RETURNING id", (cutoff,)
                )
                deleted_messages = len(cur.fetchall())
                cur.execute(
                    "DELETE FROM events WHERE at < %s RETURNING id", (cutoff,)
                )
                deleted_events = len(cur.fetchall())

                counts = {
                    "messages": deleted_messages,
                    "events": deleted_events,
                    "contacts": deleted_contacts,
                    "case_links": deleted_links,
                    "auto_handover_outcomes": deleted_outcomes,
                    "auto_handover_streaks": deleted_streaks,
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
