"""Persistencia (contactos, historial, eventos, update_id) detrás de un Repository."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

from lazaro_contracts import LastMessage

from ..domain import Contact


class Repository(Protocol):
    def mark_update_if_new(self, update_id: int) -> bool: ...

    def get_or_create_contact(
        self, telegram_user_id: int, chat_id: int, now: datetime
    ) -> Contact: ...

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None: ...

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]: ...

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None: ...


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


class FakeRepository:
    def __init__(self) -> None:
        self.contacts: dict[int, Contact] = {}
        self.messages: list[StoredMessage] = []
        self.events: list[StoredEvent] = []
        self.processed: set[int] = set()

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
        return contact

    def add_message(self, contact_id: str, role: str, text: str, at: datetime) -> None:
        self.messages.append(StoredMessage(contact_id, role, text, at))

    def last_messages(self, contact_id: str, limit: int) -> list[LastMessage]:
        own = [m for m in self.messages if m.contact_id == contact_id]
        return [LastMessage(role=m.role, text=m.text, at=m.at) for m in own[-limit:]]  # type: ignore[arg-type]

    def add_event(self, contact_id: str, type: str, reason: str, at: datetime) -> None:
        self.events.append(StoredEvent(contact_id, type, reason, at))


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
    """SQL siempre parametrizado (%s); la conexión se abre en el primer uso."""

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

    def _connection(self) -> Any:
        if self._conn is None:
            conn = self._connect()
            cur = conn.cursor()
            for statement in _SCHEMA:
                cur.execute(statement)
            conn.commit()
            self._conn = conn
        return self._conn

    def _run(self, sql: str, params: tuple, fetch: bool = False) -> list:
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
