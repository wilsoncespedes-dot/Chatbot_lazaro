"""Cursor persistente de Gmail History: PostgreSQL y fake en memoria.

La tabla `gmail_history_state` la crea `migrations/0006_gmail_historial.sql`; el
gateway no ejecuta DDL (fase 1).
"""
from __future__ import annotations

import threading
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .channel_repository import (
    IDLE_PROBE_SECONDS,
    _connection_alive,
    _pg_connect,
    is_connection_error,
)


class GmailHistoryRepository(Protocol):
    def get_cursor(self, channel_id: str) -> str | None: ...

    def set_cursor(self, channel_id: str, history_id: str) -> None: ...

    def reset_cursor(self, channel_id: str, history_id: str) -> None: ...


class FakeGmailHistoryRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.cursors: dict[str, str] = {}
        self._lock = threading.Lock()

    def _check(self) -> None:
        if self.fail:
            raise OSError("gmail history unavailable")

    def get_cursor(self, channel_id: str) -> str | None:
        self._check()
        with self._lock:
            return self.cursors.get(channel_id)

    def set_cursor(self, channel_id: str, history_id: str) -> None:
        self._check()
        with self._lock:
            self.cursors[channel_id] = history_id

    def reset_cursor(self, channel_id: str, history_id: str) -> None:
        self.set_cursor(channel_id, history_id)


class PostgresGmailHistoryRepository:
    def __init__(
        self,
        database_url: str,
        connect: Callable[[], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._clock = clock or time.monotonic
        self._conn: Any = None
        self._last_used = 0.0
        self._lock = threading.Lock()

    def _discard(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with suppress(Exception):
                conn.close()

    def _connection(self) -> Any:
        if (
            self._conn is not None
            and self._clock() - self._last_used > IDLE_PROBE_SECONDS
            and not _connection_alive(self._conn)
        ):
            self._discard()
        if self._conn is None:
            self._conn = self._connect()
        self._last_used = self._clock()
        return self._conn

    def _run(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        fetch: bool = False,
    ) -> list[tuple[Any, ...]]:
        with self._lock:
            try:
                conn = self._connection()
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = list(cursor.fetchall()) if fetch else []
                conn.commit()
                self._last_used = self._clock()
                return rows
            except Exception as exc:
                conn = self._conn
                if conn is not None:
                    with suppress(Exception):
                        conn.rollback()
                if is_connection_error(exc):
                    self._discard()
                raise

    def get_cursor(self, channel_id: str) -> str | None:
        rows = self._run(
            "SELECT history_id FROM gmail_history_state WHERE canal_id = %s",
            (channel_id,),
            fetch=True,
        )
        return str(rows[0][0]) if rows else None

    def set_cursor(self, channel_id: str, history_id: str) -> None:
        self._run(
            "INSERT INTO gmail_history_state (canal_id, history_id, actualizado_en) "
            "VALUES (%s, %s, %s) ON CONFLICT (canal_id) DO UPDATE SET "
            "history_id = EXCLUDED.history_id, actualizado_en = EXCLUDED.actualizado_en",
            (channel_id, history_id, datetime.now(timezone.utc)),
        )

    def reset_cursor(self, channel_id: str, history_id: str) -> None:
        self.set_cursor(channel_id, history_id)
