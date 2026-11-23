"""Cola persistente de mensajes entrantes que el orquestador no pudo recibir.

El canal ya entregó el mensaje al gateway; si el orquestador está caído, el
mensaje se guarda aquí antes de responder `ok` al canal y un worker lo reenvía
con espera creciente. La fila se borra en cuanto el orquestador lo acepta (o lo
reconoce como duplicado), así el texto no se conserva más de lo necesario.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from lazaro_contracts import NormalizedMessage

from .channel_repository import (
    IDLE_PROBE_SECONDS,
    _connection_alive,
    _pg_connect,
    is_connection_error,
)

MAX_ERROR_LENGTH = 200


@dataclass(frozen=True)
class PendingInbound:
    id: int
    message: NormalizedMessage
    attempts: int
    created_at: datetime


class InboundRetryStore(Protocol):
    def save(
        self, message: NormalizedMessage, error: str, now: datetime, next_attempt_at: datetime
    ) -> None:
        """Guarda el mensaje (idempotente por canal + id externo) o lanza."""
        ...

    def claim_due(
        self, now: datetime, lease_seconds: float, limit: int
    ) -> list[PendingInbound]:
        """Reclama hasta `limit` mensajes vencidos y suma un intento a cada uno."""
        ...

    def delete(self, row_id: int) -> None: ...

    def reschedule(self, row_id: int, next_attempt_at: datetime, error: str) -> None: ...


def _message_json(message: NormalizedMessage) -> str:
    return message.model_dump_json()


class FakeInboundRetryStore:
    """Misma semántica que Postgres, en memoria; para pruebas y entornos sin base."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.rows: dict[int, dict[str, Any]] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def _check(self) -> None:
        if self.fail:
            raise OSError("cola de reintento no disponible")

    def save(
        self, message: NormalizedMessage, error: str, now: datetime, next_attempt_at: datetime
    ) -> None:
        self._check()
        with self._lock:
            key = (message.channel, message.external_message_id)
            if any((r["channel"], r["external_message_id"]) == key for r in self.rows.values()):
                return
            self._seq += 1
            self.rows[self._seq] = {
                "id": self._seq,
                "channel": message.channel,
                "external_message_id": message.external_message_id,
                "message": _message_json(message),
                "attempts": 0,
                "next_attempt_at": next_attempt_at,
                "locked_until": None,
                "last_error": error[:MAX_ERROR_LENGTH],
                "created_at": now,
            }

    def claim_due(
        self, now: datetime, lease_seconds: float, limit: int
    ) -> list[PendingInbound]:
        self._check()
        with self._lock:
            due = sorted(
                (
                    row
                    for row in self.rows.values()
                    if row["next_attempt_at"] <= now
                    and (row["locked_until"] is None or row["locked_until"] < now)
                ),
                key=lambda row: row["id"],
            )[:limit]
            claimed: list[PendingInbound] = []
            for row in due:
                row["attempts"] += 1
                row["locked_until"] = now + timedelta(seconds=lease_seconds)
                claimed.append(
                    PendingInbound(
                        id=row["id"],
                        message=NormalizedMessage.model_validate_json(row["message"]),
                        attempts=row["attempts"],
                        created_at=row["created_at"],
                    )
                )
            return claimed

    def delete(self, row_id: int) -> None:
        self._check()
        with self._lock:
            self.rows.pop(row_id, None)

    def reschedule(self, row_id: int, next_attempt_at: datetime, error: str) -> None:
        self._check()
        with self._lock:
            row = self.rows.get(row_id)
            if row is not None:
                row["next_attempt_at"] = next_attempt_at
                row["locked_until"] = None
                row["last_error"] = error[:MAX_ERROR_LENGTH]


class PostgresInboundRetryStore:
    """Tabla `gateway_entrantes_pendientes` (migración 0002); SQL parametrizado."""

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
            self._conn = self._connect()
        self._last_used = self._clock()
        return self._conn

    def _run(
        self, sql: str, params: tuple[Any, ...] = (), *, fetch: bool = False
    ) -> list[tuple[Any, ...]]:
        with self._lock:
            try:
                conn = self._connection()
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = list(cursor.fetchall()) if fetch else []
                conn.commit()
                return rows
            except Exception as exc:
                conn = self._conn
                if conn is not None:
                    with suppress(Exception):
                        conn.rollback()
                if is_connection_error(exc):
                    self._discard_connection()
                raise

    def save(
        self, message: NormalizedMessage, error: str, now: datetime, next_attempt_at: datetime
    ) -> None:
        self._run(
            "INSERT INTO gateway_entrantes_pendientes (canal, id_mensaje_externo, "
            "mensaje, intentos, proximo_intento, ultimo_error, creado_en) "
            "VALUES (%s, %s, CAST(%s AS JSONB), 0, %s, %s, %s) "
            "ON CONFLICT (canal, id_mensaje_externo) DO NOTHING",
            (
                message.channel,
                message.external_message_id,
                _message_json(message),
                next_attempt_at,
                error[:MAX_ERROR_LENGTH],
                now,
            ),
        )

    def claim_due(
        self, now: datetime, lease_seconds: float, limit: int
    ) -> list[PendingInbound]:
        rows = self._run(
            "UPDATE gateway_entrantes_pendientes SET intentos = intentos + 1, "
            "bloqueado_hasta = %s WHERE id IN ("
            "SELECT id FROM gateway_entrantes_pendientes "
            "WHERE proximo_intento <= %s "
            "AND (bloqueado_hasta IS NULL OR bloqueado_hasta < %s) "
            "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT %s) "
            "RETURNING id, mensaje, intentos, creado_en",
            (now + timedelta(seconds=lease_seconds), now, now, limit),
            fetch=True,
        )
        claimed: list[PendingInbound] = []
        for row_id, payload, attempts, created_at in sorted(rows, key=lambda r: r[0]):
            data = json.loads(payload) if isinstance(payload, str) else payload
            claimed.append(
                PendingInbound(
                    id=row_id,
                    message=NormalizedMessage.model_validate(data),
                    attempts=attempts,
                    created_at=created_at,
                )
            )
        return claimed

    def delete(self, row_id: int) -> None:
        self._run("DELETE FROM gateway_entrantes_pendientes WHERE id = %s", (row_id,))

    def reschedule(self, row_id: int, next_attempt_at: datetime, error: str) -> None:
        self._run(
            "UPDATE gateway_entrantes_pendientes SET proximo_intento = %s, "
            "bloqueado_hasta = NULL, ultimo_error = %s WHERE id = %s",
            (next_attempt_at, error[:MAX_ERROR_LENGTH], row_id),
        )
