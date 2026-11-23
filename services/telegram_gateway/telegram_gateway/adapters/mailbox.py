"""Buzón del canal SIMULADO: repositorio PostgreSQL y versión falsa en memoria."""
from __future__ import annotations

import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from lazaro_contracts import MailboxEntry

from .channel_repository import (
    IDLE_PROBE_SECONDS,
    _connection_alive,
    _pg_connect,
    is_connection_error,
)

# El esquema vive en `migrations/` y lo aplica el runner en el despliegue.
_COLUMNS = "id, canal_id, destino, tipo, texto, creado_en"


class MailboxRepository(Protocol):
    def append(
        self,
        channel_id: str,
        destination: str,
        kind: str,
        text: str,
        now: datetime,
    ) -> int:
        """Guarda una entrada y devuelve su id creciente."""
        ...

    def list(
        self,
        channel_id: str,
        destination: str | None,
        after_id: int,
        limit: int,
        now: datetime,
    ) -> list[MailboxEntry]:
        """Entradas vivas del canal con id > after_id, en orden ascendente."""
        ...


@dataclass
class _StoredEntry:
    id: int
    destination: str
    kind: str
    text: str
    created_at: datetime


class FakeMailboxRepository:
    """Mismo comportamiento que Postgres, sin red; usado en las pruebas."""

    def __init__(
        self,
        retention_seconds: int = 3600,
        max_entries: int = 500,
        *,
        fail: bool = False,
    ) -> None:
        self._retention = timedelta(seconds=retention_seconds)
        self._max_entries = max_entries
        self.fail = fail
        self._entries: dict[str, list[_StoredEntry]] = {}
        self._next_id = 0
        self._lock = threading.Lock()

    def _check_available(self) -> None:
        if self.fail:
            raise OSError("mailbox unavailable")

    def _purge(self, channel_id: str, now: datetime) -> None:
        cutoff = now - self._retention
        stored = [
            entry for entry in self._entries.get(channel_id, [])
            if entry.created_at >= cutoff
        ]
        if len(stored) > self._max_entries:
            stored = stored[-self._max_entries :]
        self._entries[channel_id] = stored

    def append(
        self,
        channel_id: str,
        destination: str,
        kind: str,
        text: str,
        now: datetime,
    ) -> int:
        self._check_available()
        with self._lock:
            self._next_id += 1
            entry = _StoredEntry(
                id=self._next_id,
                destination=destination,
                kind=kind,
                text=text,
                created_at=now,
            )
            self._entries.setdefault(channel_id, []).append(entry)
            self._purge(channel_id, now)
            return entry.id

    def list(
        self,
        channel_id: str,
        destination: str | None,
        after_id: int,
        limit: int,
        now: datetime,
    ) -> list[MailboxEntry]:
        self._check_available()
        cutoff = now - self._retention
        with self._lock:
            stored = [
                entry
                for entry in self._entries.get(channel_id, [])
                if entry.id > after_id
                and entry.created_at >= cutoff
                and (destination is None or entry.destination == destination)
            ]
            return [
                MailboxEntry(
                    id=entry.id,
                    channel=channel_id,
                    destination=entry.destination,
                    kind=entry.kind,  # type: ignore[arg-type]
                    text=entry.text,
                    created_at=entry.created_at,
                )
                for entry in stored[:limit]
            ]


def _row_to_entry(row: tuple[Any, ...]) -> MailboxEntry:
    return MailboxEntry(
        id=row[0],
        channel=row[1],
        destination=row[2],
        kind=row[3],
        text=row[4],
        created_at=row[5],
    )


class PostgresMailboxRepository:
    """PostgreSQL perezoso con reconexión y SQL parametrizado."""

    def __init__(
        self,
        database_url: str,
        retention_seconds: int = 3600,
        max_entries: int = 500,
        connect: Callable[[], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._database_url = database_url
        self._retention_seconds = retention_seconds
        self._max_entries = max_entries
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._clock = clock or time.monotonic
        self._conn: Any = None
        self._last_used = 0.0
        self._lock = threading.Lock()

    def _discard_connection(self) -> None:
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
            self._discard_connection()
        if self._conn is None:
            # Sin DDL al conectar: el esquema lo crea `migrations/runner.py`.
            self._conn = self._connect()
        self._last_used = self._clock()
        return self._conn

    def _handle_error(self, exc: Exception) -> None:
        conn = self._conn
        if conn is not None:
            with suppress(Exception):
                conn.rollback()
        if is_connection_error(exc):
            self._discard_connection()

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
                self._handle_error(exc)
                raise

    def append(
        self,
        channel_id: str,
        destination: str,
        kind: str,
        text: str,
        now: datetime,
    ) -> int:
        cutoff = now - timedelta(seconds=self._retention_seconds)
        with self._lock:
            try:
                conn = self._connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO buzon_simulado "
                    "(canal_id, destino, tipo, texto, creado_en) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (channel_id, destination, kind, text, now),
                )
                row = cursor.fetchone()
                entry_id = int(row[0])
                cursor.execute(
                    "DELETE FROM buzon_simulado "
                    "WHERE canal_id = %s AND creado_en < %s",
                    (channel_id, cutoff),
                )
                cursor.execute(
                    "DELETE FROM buzon_simulado WHERE canal_id = %s AND id <= ("
                    "SELECT id FROM buzon_simulado WHERE canal_id = %s "
                    "ORDER BY id DESC OFFSET %s LIMIT 1)",
                    (channel_id, channel_id, self._max_entries),
                )
                conn.commit()
                self._last_used = self._clock()
                return entry_id
            except Exception as exc:
                self._handle_error(exc)
                raise

    def list(
        self,
        channel_id: str,
        destination: str | None,
        after_id: int,
        limit: int,
        now: datetime,
    ) -> list[MailboxEntry]:
        cutoff = now - timedelta(seconds=self._retention_seconds)
        sql = (
            f"SELECT {_COLUMNS} FROM buzon_simulado "
            "WHERE canal_id = %s AND id > %s AND creado_en >= %s"
        )
        params: list[Any] = [channel_id, after_id, cutoff]
        if destination is not None:
            sql += " AND destino = %s"
            params.append(destination)
        sql += " ORDER BY id ASC LIMIT %s"
        params.append(limit)
        rows = self._run(sql, tuple(params), fetch=True)
        return [_row_to_entry(row) for row in rows]
