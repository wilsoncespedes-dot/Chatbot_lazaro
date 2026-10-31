"""Persistencia de casos y notificaciones detrás de un CaseRepository."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

from lazaro_contracts import LastMessage

from ..domain import Case, Notification


class CaseRepository(Protocol):
    def find_active_case(self, contact_id: str) -> Case | None: ...

    def create_case(self, case: Case) -> None: ...

    def update_case(self, case: Case) -> None: ...

    def get_case(self, case_id: str) -> Case | None: ...

    def list_open_cases(self) -> list[Case]: ...

    def add_notification(
        self, case_id: str, advisor_id: str, reason: str, at: datetime, delivered: bool
    ) -> None: ...


ACTIVE_STATUSES = ("open", "assigned")


class FakeCaseRepository:
    """En memoria; guarda y devuelve copias para que solo update_case cambie un caso."""

    def __init__(self) -> None:
        self.cases: dict[str, Case] = {}
        self.notifications: list[Notification] = []

    def find_active_case(self, contact_id: str) -> Case | None:
        active = [
            c
            for c in self.cases.values()
            if c.contact_id == contact_id and c.status in ACTIVE_STATUSES
        ]
        if not active:
            return None
        return max(active, key=lambda c: c.created_at).model_copy(deep=True)

    def create_case(self, case: Case) -> None:
        self.cases[case.case_id] = case.model_copy(deep=True)

    def update_case(self, case: Case) -> None:
        self.cases[case.case_id] = case.model_copy(deep=True)

    def get_case(self, case_id: str) -> Case | None:
        case = self.cases.get(case_id)
        return case.model_copy(deep=True) if case is not None else None

    def list_open_cases(self) -> list[Case]:
        return [c.model_copy(deep=True) for c in self.cases.values() if c.status == "open"]

    def add_notification(
        self, case_id: str, advisor_id: str, reason: str, at: datetime, delivered: bool
    ) -> None:
        self.notifications.append(
            Notification(
                case_id=case_id, advisor_id=advisor_id, reason=reason, at=at, delivered=delivered
            )
        )


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS handover_cases ("
    "case_id TEXT PRIMARY KEY, contact_id TEXT NOT NULL, chat_id BIGINT NOT NULL, "
    "reason TEXT NOT NULL, status TEXT NOT NULL, advisor_id TEXT NULL, "
    "last_messages JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "assigned_at TIMESTAMPTZ NULL, closed_at TIMESTAMPTZ NULL, closed_by TEXT NULL)",
    "CREATE TABLE IF NOT EXISTS handover_notifications ("
    "id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, advisor_id TEXT NOT NULL, "
    "reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL, delivered BOOLEAN NOT NULL)",
)

_CASE_COLUMNS = (
    "case_id, contact_id, chat_id, reason, status, advisor_id, last_messages, "
    "created_at, assigned_at, closed_at, closed_by"
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


def _dump_messages(messages: list[LastMessage]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in messages], ensure_ascii=False)


def _row_to_case(row: tuple) -> Case:
    raw_messages = row[6]
    if isinstance(raw_messages, (str, bytes)):
        raw_messages = json.loads(raw_messages)
    return Case(
        case_id=row[0],
        contact_id=row[1],
        chat_id=row[2],
        reason=row[3],
        status=row[4],
        advisor_id=row[5],
        last_messages=[LastMessage.model_validate(m) for m in raw_messages or []],
        created_at=row[7],
        assigned_at=row[8],
        closed_at=row[9],
        closed_by=row[10],
    )


class PostgresCaseRepository:
    """SQL siempre parametrizado (%s); la conexión se abre en el primer uso."""

    def __init__(self, database_url: str, connect: Callable[[], Any] | None = None) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: _pg_connect(self._database_url))
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

    def find_active_case(self, contact_id: str) -> Case | None:
        rows = self._run(
            f"SELECT {_CASE_COLUMNS} FROM handover_cases "
            "WHERE contact_id = %s AND status IN (%s, %s) ORDER BY created_at DESC LIMIT 1",
            (contact_id, *ACTIVE_STATUSES),
            fetch=True,
        )
        return _row_to_case(rows[0]) if rows else None

    def create_case(self, case: Case) -> None:
        self._run(
            f"INSERT INTO handover_cases ({_CASE_COLUMNS}) "
            "VALUES (%s, %s, %s, %s, %s, %s, CAST(%s AS JSONB), %s, %s, %s, %s)",
            (
                case.case_id,
                case.contact_id,
                case.chat_id,
                case.reason,
                case.status,
                case.advisor_id,
                _dump_messages(case.last_messages),
                case.created_at,
                case.assigned_at,
                case.closed_at,
                case.closed_by,
            ),
        )

    def update_case(self, case: Case) -> None:
        self._run(
            "UPDATE handover_cases SET status = %s, advisor_id = %s, "
            "last_messages = CAST(%s AS JSONB), assigned_at = %s, closed_at = %s, "
            "closed_by = %s WHERE case_id = %s",
            (
                case.status,
                case.advisor_id,
                _dump_messages(case.last_messages),
                case.assigned_at,
                case.closed_at,
                case.closed_by,
                case.case_id,
            ),
        )

    def get_case(self, case_id: str) -> Case | None:
        rows = self._run(
            f"SELECT {_CASE_COLUMNS} FROM handover_cases WHERE case_id = %s",
            (case_id,),
            fetch=True,
        )
        return _row_to_case(rows[0]) if rows else None

    def list_open_cases(self) -> list[Case]:
        rows = self._run(
            f"SELECT {_CASE_COLUMNS} FROM handover_cases WHERE status = %s ORDER BY created_at",
            ("open",),
            fetch=True,
        )
        return [_row_to_case(row) for row in rows]

    def add_notification(
        self, case_id: str, advisor_id: str, reason: str, at: datetime, delivered: bool
    ) -> None:
        self._run(
            "INSERT INTO handover_notifications (case_id, advisor_id, reason, at, delivered) "
            "VALUES (%s, %s, %s, %s, %s)",
            (case_id, advisor_id, reason, at, delivered),
        )
