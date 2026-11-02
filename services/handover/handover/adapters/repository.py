"""Persistencia de casos y notificaciones detrás de un CaseRepository."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

from lazaro_contracts import LastMessage

from ..domain import Case, Denial, HandoverRequestRecord, Notification, RequestResult


class CaseRepository(Protocol):
    def find_active_case(self, contact_id: str) -> Case | None: ...

    def create_case(self, case: Case) -> None: ...

    def update_case(self, case: Case) -> None: ...

    def claim_timeout(self, case_id: str, now: datetime, stale_before: datetime) -> bool: ...

    def release_timeout_claim(self, case_id: str) -> None: ...

    def mark_timed_out(self, case_id: str) -> bool: ...

    def update_last_messages(self, case_id: str, last_messages: list[LastMessage]) -> None: ...

    def get_case(self, case_id: str) -> Case | None: ...

    def list_open_cases(self) -> list[Case]: ...

    def list_cases_for_advisor(
        self, advisor_id: str, registered_ids: list[str], limit: int
    ) -> list[Case]: ...

    def add_notification(
        self, case_id: str, advisor_id: str, reason: str, at: datetime, delivered: bool
    ) -> None: ...

    def add_denial(self, denial: Denial) -> None: ...

    def assign_if_unassigned(self, case_id: str, advisor_id: str, at: datetime) -> bool: ...

    def close_if_still_allowed(
        self, case_id: str, advisor_id: str, allowed_assignee: str | None, at: datetime
    ) -> bool: ...

    def count_assigned_by_advisor(self) -> dict[str | None, int]: ...

    def add_request(self, record: HandoverRequestRecord) -> int: ...

    def complete_request(
        self,
        request_id: int,
        case_id: str | None,
        result: RequestResult,
        notices_delivered: int,
    ) -> None: ...

    def purge_personal_data(
        self, cutoff: datetime, active_cutoff: datetime, ran_at: datetime
    ) -> tuple[dict[str, int], int]: ...


ACTIVE_STATUSES = ("open", "assigned")
PURGE_ACTIVE_STATUSES = ("open", "assigned", "timed_out")


class FakeCaseRepository:
    """En memoria; guarda y devuelve copias para que las escrituras no compartan estado."""

    def __init__(self) -> None:
        self.cases: dict[str, Case] = {}
        self.notifications: list[Notification] = []
        self.denials: list[Denial] = []
        self.requests: list[HandoverRequestRecord] = []
        self.timeout_claims: dict[str, datetime] = {}
        self.privacy_purge_runs: list[dict[str, Any]] = []

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

    def claim_timeout(self, case_id: str, now: datetime, stale_before: datetime) -> bool:
        case = self.cases.get(case_id)
        if case is None or case.status != "open":
            return False
        claimed_at = self.timeout_claims.get(case_id)
        if claimed_at is not None and claimed_at > stale_before:
            return False
        self.timeout_claims[case_id] = now
        return True

    def release_timeout_claim(self, case_id: str) -> None:
        case = self.cases.get(case_id)
        if case is not None and case.status == "open":
            self.timeout_claims.pop(case_id, None)

    def mark_timed_out(self, case_id: str) -> bool:
        case = self.cases.get(case_id)
        if case is None or case.status != "open":
            return False
        self.cases[case_id] = case.model_copy(update={"status": "timed_out"})
        self.timeout_claims.pop(case_id, None)
        return True

    def update_last_messages(self, case_id: str, last_messages: list[LastMessage]) -> None:
        case = self.cases.get(case_id)
        if case is None:
            return
        self.cases[case_id] = case.model_copy(
            update={"last_messages": [message.model_copy(deep=True) for message in last_messages]}
        )

    def get_case(self, case_id: str) -> Case | None:
        case = self.cases.get(case_id)
        return case.model_copy(deep=True) if case is not None else None

    def list_open_cases(self) -> list[Case]:
        return [c.model_copy(deep=True) for c in self.cases.values() if c.status == "open"]

    def list_cases_for_advisor(
        self, advisor_id: str, registered_ids: list[str], limit: int
    ) -> list[Case]:
        visible = [
            case
            for case in self.cases.values()
            if case.status in ("open", "timed_out")
            or (case.status == "assigned" and case.advisor_id == advisor_id)
            or (
                case.status == "assigned"
                and (case.advisor_id is None or case.advisor_id not in registered_ids)
            )
        ]
        visible.sort(key=lambda case: (case.created_at, case.case_id))
        return [case.model_copy(deep=True) for case in visible[:limit]]

    def add_notification(
        self, case_id: str, advisor_id: str, reason: str, at: datetime, delivered: bool
    ) -> None:
        self.notifications.append(
            Notification(
                case_id=case_id, advisor_id=advisor_id, reason=reason, at=at, delivered=delivered
            )
        )

    def add_denial(self, denial: Denial) -> None:
        self.denials.append(denial.model_copy(deep=True))

    def assign_if_unassigned(self, case_id: str, advisor_id: str, at: datetime) -> bool:
        case = self.cases.get(case_id)
        if case is None or case.status not in ("open", "timed_out"):
            return False
        self.cases[case_id] = case.model_copy(
            update={"status": "assigned", "advisor_id": advisor_id, "assigned_at": at}
        )
        return True

    def close_if_still_allowed(
        self, case_id: str, advisor_id: str, allowed_assignee: str | None, at: datetime
    ) -> bool:
        case = self.cases.get(case_id)
        if case is None:
            return False
        allowed = case.status in ("open", "timed_out") or (
            case.status == "assigned" and case.advisor_id == allowed_assignee
        )
        if not allowed:
            return False
        self.cases[case_id] = case.model_copy(
            update={"status": "closed", "closed_by": advisor_id, "closed_at": at}
        )
        return True

    def count_assigned_by_advisor(self) -> dict[str | None, int]:
        counts: dict[str | None, int] = {}
        for case in self.cases.values():
            if case.status == "assigned":
                counts[case.advisor_id] = counts.get(case.advisor_id, 0) + 1
        return counts

    def add_request(self, record: HandoverRequestRecord) -> int:
        request_id = len(self.requests) + 1
        self.requests.append(
            record.model_copy(update={"request_id": request_id}, deep=True)
        )
        return request_id

    def complete_request(
        self,
        request_id: int,
        case_id: str | None,
        result: RequestResult,
        notices_delivered: int,
    ) -> None:
        for index, record in enumerate(self.requests):
            if record.request_id == request_id:
                self.requests[index] = record.model_copy(
                    update={
                        "case_id": case_id,
                        "result": result,
                        "notices_delivered": notices_delivered,
                    },
                    deep=True,
                )
                return

    def purge_personal_data(
        self, cutoff: datetime, active_cutoff: datetime, ran_at: datetime
    ) -> tuple[dict[str, int], int]:
        expired_cases = {
            case.case_id
            for case in self.cases.values()
            if case.status in PURGE_ACTIVE_STATUSES and case.created_at < active_cutoff
        }
        requests = [
            record
            for record in self.requests
            if record.case_id in expired_cases or record.requested_case_id in expired_cases
        ]
        self.requests = [
            record
            for record in self.requests
            if record.case_id not in expired_cases
            and record.requested_case_id not in expired_cases
        ]
        deleted_requests = len(requests)
        closed_active_cases = len(expired_cases)
        for case_id in expired_cases:
            self.cases.pop(case_id, None)
            self.timeout_claims.pop(case_id, None)

        old_closed = [
            case_id
            for case_id, case in self.cases.items()
            if case.status == "closed"
            and case.closed_at is not None
            and case.closed_at < cutoff
        ]
        for case_id in old_closed:
            self.cases.pop(case_id, None)

        old_requests = [
            record for record in self.requests if record.received_at < cutoff
        ]
        self.requests = [
            record for record in self.requests if record.received_at >= cutoff
        ]
        deleted_requests += len(old_requests)

        counts = {
            "handover_cases": len(old_closed),
            "handover_requests": deleted_requests,
        }
        self.privacy_purge_runs.append(
            {
                "ran_at": ran_at,
                "cutoff": cutoff,
                "counts": dict(counts),
                "closed_active_cases": closed_active_cases,
            }
        )
        return counts, closed_active_cases


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS handover_cases ("
    "case_id TEXT PRIMARY KEY, contact_id TEXT NOT NULL, chat_id BIGINT NOT NULL, "
    "reason TEXT NOT NULL, status TEXT NOT NULL, advisor_id TEXT NULL, "
    "last_messages JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL, "
    "assigned_at TIMESTAMPTZ NULL, closed_at TIMESTAMPTZ NULL, closed_by TEXT NULL)",
    "CREATE TABLE IF NOT EXISTS handover_notifications ("
    "id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, advisor_id TEXT NOT NULL, "
    "reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL, delivered BOOLEAN NOT NULL)",
    "CREATE TABLE IF NOT EXISTS handover_denials ("
    "id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, advisor_id TEXT NOT NULL, "
    "action TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS handover_requests ("
    "id BIGSERIAL PRIMARY KEY, requested_case_id TEXT NOT NULL, case_id TEXT NULL, "
    "contact_id TEXT NOT NULL, reason TEXT NOT NULL, received_at TIMESTAMPTZ NOT NULL, "
    "result TEXT NOT NULL, advisors_configured INTEGER NOT NULL, "
    "notices_delivered INTEGER NOT NULL, messages_count INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS privacy_purge_runs ("
    "id BIGSERIAL PRIMARY KEY, ran_at TIMESTAMPTZ NOT NULL, "
    "cutoff TIMESTAMPTZ NOT NULL, counts JSONB NOT NULL)",
    "ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS "
    "timeout_claimed_at TIMESTAMPTZ NULL",
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
        self._lock = threading.Lock()

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

    def claim_timeout(self, case_id: str, now: datetime, stale_before: datetime) -> bool:
        rows = self._run(
            "UPDATE handover_cases SET timeout_claimed_at = %s "
            "WHERE case_id = %s AND status = %s "
            "AND (timeout_claimed_at IS NULL OR timeout_claimed_at <= %s) "
            "RETURNING case_id",
            (now, case_id, "open", stale_before),
            fetch=True,
        )
        return bool(rows)

    def release_timeout_claim(self, case_id: str) -> None:
        self._run(
            "UPDATE handover_cases SET timeout_claimed_at = NULL "
            "WHERE case_id = %s AND status = %s",
            (case_id, "open"),
        )

    def mark_timed_out(self, case_id: str) -> bool:
        rows = self._run(
            "UPDATE handover_cases SET status = %s, timeout_claimed_at = NULL "
            "WHERE case_id = %s AND status = %s RETURNING case_id",
            ("timed_out", case_id, "open"),
            fetch=True,
        )
        return bool(rows)

    def update_last_messages(self, case_id: str, last_messages: list[LastMessage]) -> None:
        self._run(
            "UPDATE handover_cases SET last_messages = CAST(%s AS JSONB) WHERE case_id = %s",
            (_dump_messages(last_messages), case_id),
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

    def list_cases_for_advisor(
        self, advisor_id: str, registered_ids: list[str], limit: int
    ) -> list[Case]:
        rows = self._run(
            f"SELECT {_CASE_COLUMNS} FROM handover_cases "
            "WHERE status IN (%s, %s) "
            "OR (status = %s AND advisor_id = %s) "
            "OR (status = %s AND (advisor_id IS NULL OR NOT (advisor_id = ANY(%s)))) "
            "ORDER BY created_at ASC, case_id ASC LIMIT %s",
            (
                "open",
                "timed_out",
                "assigned",
                advisor_id,
                "assigned",
                registered_ids,
                limit,
            ),
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

    def add_denial(self, denial: Denial) -> None:
        self._run(
            "INSERT INTO handover_denials (case_id, advisor_id, action, at) "
            "VALUES (%s, %s, %s, %s)",
            (denial.case_id, denial.advisor_id, denial.action, denial.at),
        )

    def assign_if_unassigned(self, case_id: str, advisor_id: str, at: datetime) -> bool:
        rows = self._run(
            "UPDATE handover_cases SET status = %s, advisor_id = %s, assigned_at = %s "
            "WHERE case_id = %s AND status IN (%s, %s) RETURNING case_id",
            ("assigned", advisor_id, at, case_id, "open", "timed_out"),
            fetch=True,
        )
        return bool(rows)

    def close_if_still_allowed(
        self, case_id: str, advisor_id: str, allowed_assignee: str | None, at: datetime
    ) -> bool:
        if allowed_assignee is None:
            sql = (
                "UPDATE handover_cases SET status = %s, closed_by = %s, closed_at = %s "
                "WHERE case_id = %s AND (status IN (%s, %s) OR "
                "(status = %s AND advisor_id IS NULL)) RETURNING case_id"
            )
            params = ("closed", advisor_id, at, case_id, "open", "timed_out", "assigned")
        else:
            sql = (
                "UPDATE handover_cases SET status = %s, closed_by = %s, closed_at = %s "
                "WHERE case_id = %s AND (status IN (%s, %s) OR "
                "(status = %s AND advisor_id = %s)) RETURNING case_id"
            )
            params = (
                "closed",
                advisor_id,
                at,
                case_id,
                "open",
                "timed_out",
                "assigned",
                allowed_assignee,
            )
        rows = self._run(sql, params, fetch=True)
        return bool(rows)

    def count_assigned_by_advisor(self) -> dict[str | None, int]:
        rows = self._run(
            "SELECT advisor_id, COUNT(*) FROM handover_cases "
            "WHERE status = %s GROUP BY advisor_id",
            ("assigned",),
            fetch=True,
        )
        return {row[0]: int(row[1]) for row in rows}

    def add_request(self, record: HandoverRequestRecord) -> int:
        rows = self._run(
            "INSERT INTO handover_requests (requested_case_id, case_id, contact_id, reason, "
            "received_at, result, advisors_configured, notices_delivered, messages_count) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                record.requested_case_id,
                record.case_id,
                record.contact_id,
                record.reason,
                record.received_at,
                record.result,
                record.advisors_configured,
                record.notices_delivered,
                record.messages_count,
            ),
            fetch=True,
        )
        return int(rows[0][0])

    def complete_request(
        self,
        request_id: int,
        case_id: str | None,
        result: RequestResult,
        notices_delivered: int,
    ) -> None:
        self._run(
            "UPDATE handover_requests SET case_id = %s, result = %s, notices_delivered = %s "
            "WHERE id = %s",
            (case_id, result, notices_delivered, request_id),
        )

    def purge_personal_data(
        self, cutoff: datetime, active_cutoff: datetime, ran_at: datetime
    ) -> tuple[dict[str, int], int]:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT case_id FROM handover_cases "
                    "WHERE status IN (%s, %s, %s) AND created_at < %s FOR UPDATE",
                    (*PURGE_ACTIVE_STATUSES, active_cutoff),
                )
                expired_cases = [row[0] for row in cur.fetchall()]

                deleted_requests = 0
                closed_active_cases = 0
                if expired_cases:
                    cur.execute(
                        "DELETE FROM handover_requests "
                        "WHERE case_id = ANY(%s) OR requested_case_id = ANY(%s) "
                        "RETURNING id",
                        (expired_cases, expired_cases),
                    )
                    deleted_requests = len(cur.fetchall())
                    cur.execute(
                        "DELETE FROM handover_cases WHERE case_id = ANY(%s) "
                        "RETURNING case_id",
                        (expired_cases,),
                    )
                    closed_active_cases = len(cur.fetchall())

                cur.execute(
                    "DELETE FROM handover_cases WHERE status = %s AND closed_at < %s "
                    "RETURNING case_id",
                    ("closed", cutoff),
                )
                deleted_cases = len(cur.fetchall())

                cur.execute(
                    "DELETE FROM handover_requests WHERE received_at < %s RETURNING id",
                    (cutoff,),
                )
                deleted_requests += len(cur.fetchall())

                counts = {
                    "handover_cases": deleted_cases,
                    "handover_requests": deleted_requests,
                }
                run_counts = dict(counts)
                run_counts["closed_active_cases"] = closed_active_cases
                cur.execute(
                    "INSERT INTO privacy_purge_runs (ran_at, cutoff, counts) "
                    "VALUES (%s, %s, CAST(%s AS JSONB))",
                    (ran_at, cutoff, json.dumps(run_counts)),
                )
                conn.commit()
                return counts, closed_active_cases
            except Exception:
                conn.rollback()
                raise
