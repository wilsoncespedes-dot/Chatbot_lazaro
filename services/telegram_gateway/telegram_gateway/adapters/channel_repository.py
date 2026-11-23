"""Repositorios de la tabla canales: PostgreSQL y falso en memoria."""
from __future__ import annotations

import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import unquote, urlparse

from ..domain import ChannelRecord, ChannelSeed

IDLE_PROBE_SECONDS = 10.0
# El esquema vive en `migrations/` y lo aplica el runner en el despliegue.
_CHANNEL_COLUMNS = (
    "id, nombre, tipo_adaptador, icono, color, config, activo, creado_en, "
    "(config_secreta IS NOT NULL) AS has_secrets, activo_segun_entorno, "
    "pistas_credenciales"
)


def is_connection_error(exc: BaseException) -> bool:
    return isinstance(exc, OSError) or type(exc).__name__ == "InterfaceError"


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


def _connection_alive(conn: Any) -> bool:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.commit()
        return True
    except Exception:
        return False


def _config_json(config: Mapping[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _json_object(value: Any) -> dict:
    if isinstance(value, (str, bytes)):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def _row_to_record(row: tuple[Any, ...]) -> ChannelRecord:
    config = _json_object(row[5])
    hints = _json_object(row[10]) if len(row) > 10 else {}
    return ChannelRecord(
        id=row[0],
        name=row[1],
        adapter_type=row[2],
        icon=row[3],
        color=row[4],
        config=config,
        active=row[6],
        created_at=row[7],
        has_secrets=row[8],
        active_follows_environment=row[9],
        credential_hints={str(k): str(v) for k, v in hints.items()},
    )


class ChannelRepository(Protocol):
    def health_check(self, timeout_seconds: float) -> None: ...

    def seed(self, rows: Sequence[tuple[ChannelSeed, bool]]) -> None: ...

    def list_channels(self) -> list[ChannelRecord]: ...

    def get(self, channel_id: str) -> ChannelRecord | None: ...

    def get_encrypted_secrets(self, channel_id: str) -> str | None: ...

    def create(self, record: ChannelRecord, encrypted_secrets: str | None) -> bool: ...

    def update(self, channel_id: str, changes: "ChannelChanges") -> ChannelRecord | None: ...

    def set_active(self, channel_id: str, active: bool) -> ChannelRecord | None: ...

    def set_encrypted_secrets(self, channel_id: str, token: str) -> bool: ...


@dataclass(frozen=True)
class ChannelChanges:
    name: str | None = None
    icon: str | None = None
    color: str | None = None
    config: Mapping[str, Any] | None = None
    encrypted_secrets: str | None = None
    credential_hints: Mapping[str, str] | None = None


class FakeChannelRepository:
    def __init__(
        self,
        *,
        fail: bool = False,
        health_ok: bool = True,
        health_error: BaseException | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.fail = fail
        self.health_ok = health_ok
        self.health_error = health_error
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._channels: dict[str, ChannelRecord] = {}
        self._encrypted_secrets: dict[str, str] = {}
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"FakeChannelRepository(channels={len(self._channels)})"

    def _check_available(self) -> None:
        if self.fail:
            raise OSError("channel store unavailable")

    def health_check(self, timeout_seconds: float) -> None:
        if self.health_error is not None:
            raise self.health_error
        if not self.health_ok:
            raise OSError("PostgreSQL no está disponible")

    def seed(self, rows: Sequence[tuple[ChannelSeed, bool]]) -> None:
        self._check_available()
        with self._lock:
            for seed, available in rows:
                current = self._channels.get(seed.id)
                if current is None:
                    self._channels[seed.id] = ChannelRecord(
                        id=seed.id,
                        name=seed.name,
                        adapter_type=seed.adapter_type,
                        icon=seed.icon,
                        color=seed.color,
                        config=dict(seed.config),
                        active=available,
                        created_at=self.clock(),
                        has_secrets=False,
                        active_follows_environment=True,
                    )
                else:
                    # R7/R8: completa las claves sembradas ausentes sin pisar las guardadas.
                    config = {**dict(seed.config), **dict(current.config)}
                    if config != dict(current.config):
                        current = replace(current, config=config)
                    if current.active_follows_environment and current.active != available:
                        current = replace(current, active=available)
                    self._channels[seed.id] = current

    def list_channels(self) -> list[ChannelRecord]:
        self._check_available()
        with self._lock:
            return sorted(
                self._channels.values(), key=lambda row: (row.created_at, row.id)
            )

    def get(self, channel_id: str) -> ChannelRecord | None:
        self._check_available()
        with self._lock:
            return self._channels.get(channel_id)

    def get_encrypted_secrets(self, channel_id: str) -> str | None:
        self._check_available()
        with self._lock:
            return self._encrypted_secrets.get(channel_id)

    def create(self, record: ChannelRecord, encrypted_secrets: str | None) -> bool:
        self._check_available()
        with self._lock:
            if record.id in self._channels:
                return False
            self._channels[record.id] = replace(
                record,
                config=dict(record.config),
                credential_hints=dict(record.credential_hints),
                has_secrets=encrypted_secrets is not None,
            )
            if encrypted_secrets is not None:
                self._encrypted_secrets[record.id] = encrypted_secrets
            return True

    def update(self, channel_id: str, changes: ChannelChanges) -> ChannelRecord | None:
        self._check_available()
        with self._lock:
            current = self._channels.get(channel_id)
            if current is None:
                return None
            updated = replace(
                current,
                name=changes.name if changes.name is not None else current.name,
                icon=changes.icon if changes.icon is not None else current.icon,
                color=changes.color if changes.color is not None else current.color,
                config=(
                    dict(changes.config)
                    if changes.config is not None
                    else dict(current.config)
                ),
                has_secrets=(
                    True if changes.encrypted_secrets is not None else current.has_secrets
                ),
                credential_hints=(
                    dict(changes.credential_hints)
                    if changes.credential_hints is not None
                    else dict(current.credential_hints)
                ),
            )
            self._channels[channel_id] = updated
            if changes.encrypted_secrets is not None:
                self._encrypted_secrets[channel_id] = changes.encrypted_secrets
            return updated

    def set_active(self, channel_id: str, active: bool) -> ChannelRecord | None:
        self._check_available()
        with self._lock:
            current = self._channels.get(channel_id)
            if current is None:
                return None
            updated = replace(
                current, active=active, active_follows_environment=False
            )
            self._channels[channel_id] = updated
            return updated

    def set_encrypted_secrets(self, channel_id: str, token: str) -> bool:
        self._check_available()
        with self._lock:
            if channel_id not in self._channels:
                return False
            self._encrypted_secrets[channel_id] = token
            self._channels[channel_id] = replace(
                self._channels[channel_id], has_secrets=True
            )
            return True


class PostgresChannelRepository:
    """PostgreSQL perezoso con reconexión y SQL parametrizado."""

    def __init__(
        self,
        database_url: str,
        connect: Callable[[], Any] | None = None,
        connect_health: Callable[[float], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._connect_health = connect_health or (
            lambda timeout: _pg_connect(self._database_url, timeout)
        )
        self._clock = clock or time.monotonic
        self._conn: Any = None
        self._last_used = 0.0
        self._lock = threading.Lock()

    def health_check(self, timeout_seconds: float) -> None:
        conn = self._connect_health(timeout_seconds)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            with suppress(Exception):
                conn.close()

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
                    self._discard_connection()
                raise

    def _run_seed(self, rows: Sequence[tuple[ChannelSeed, bool]]) -> None:
        with self._lock:
            try:
                conn = self._connection()
                cursor = conn.cursor()
                for seed, available in rows:
                    cursor.execute(
                        "INSERT INTO canales "
                        "(id, nombre, tipo_adaptador, icono, color, config, activo, "
                        "activo_segun_entorno) "
                        "VALUES (%s, %s, %s, %s, %s, CAST(%s AS JSONB), %s, TRUE) "
                        "ON CONFLICT (id) DO NOTHING",
                        (
                            seed.id,
                            seed.name,
                            seed.adapter_type,
                            seed.icon,
                            seed.color,
                            _config_json(seed.config),
                            available,
                        ),
                    )
                    if seed.config:
                        # R7/R8: la semilla solo rellena claves ausentes (`semilla || config`).
                        seed_config = _config_json(seed.config)
                        cursor.execute(
                            "UPDATE canales SET config = CAST(%s AS JSONB) || config "
                            "WHERE id = %s AND NOT (CAST(%s AS JSONB) <@ config)",
                            (seed_config, seed.id, seed_config),
                        )
                    cursor.execute(
                        "UPDATE canales SET activo = %s WHERE id = %s "
                        "AND activo_segun_entorno AND activo IS DISTINCT FROM %s",
                        (available, seed.id, available),
                    )
                conn.commit()
                self._last_used = self._clock()
            except Exception as exc:
                conn = self._conn
                if conn is not None:
                    with suppress(Exception):
                        conn.rollback()
                if is_connection_error(exc):
                    self._discard_connection()
                raise

    def seed(self, rows: Sequence[tuple[ChannelSeed, bool]]) -> None:
        self._run_seed(rows)

    def list_channels(self) -> list[ChannelRecord]:
        rows = self._run(
            f"SELECT {_CHANNEL_COLUMNS} FROM canales ORDER BY creado_en, id", fetch=True
        )
        return [_row_to_record(row) for row in rows]

    def get(self, channel_id: str) -> ChannelRecord | None:
        rows = self._run(
            f"SELECT {_CHANNEL_COLUMNS} FROM canales WHERE id = %s",
            (channel_id,),
            fetch=True,
        )
        return _row_to_record(rows[0]) if rows else None

    def get_encrypted_secrets(self, channel_id: str) -> str | None:
        rows = self._run(
            "SELECT config_secreta FROM canales WHERE id = %s",
            (channel_id,),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def create(self, record: ChannelRecord, encrypted_secrets: str | None) -> bool:
        rows = self._run(
            "INSERT INTO canales "
            "(id, nombre, tipo_adaptador, icono, color, config, config_secreta, activo, "
            "activo_segun_entorno, creado_en, pistas_credenciales) "
            "VALUES (%s, %s, %s, %s, %s, CAST(%s AS JSONB), %s, %s, %s, %s, "
            "CAST(%s AS JSONB)) "
            "ON CONFLICT (id) DO NOTHING RETURNING id",
            (
                record.id,
                record.name,
                record.adapter_type,
                record.icon,
                record.color,
                _config_json(record.config),
                encrypted_secrets,
                record.active,
                record.active_follows_environment,
                record.created_at,
                _config_json(record.credential_hints),
            ),
            fetch=True,
        )
        return bool(rows)

    def update(self, channel_id: str, changes: ChannelChanges) -> ChannelRecord | None:
        assignments: list[str] = []
        params: list[Any] = []
        for field_name, column in (("name", "nombre"), ("icon", "icono"), ("color", "color")):
            value = getattr(changes, field_name)
            if value is not None:
                assignments.append(f"{column} = %s")
                params.append(value)
        if changes.config is not None:
            assignments.append("config = CAST(%s AS JSONB)")
            params.append(_config_json(changes.config))
        if changes.encrypted_secrets is not None:
            assignments.append("config_secreta = %s")
            params.append(changes.encrypted_secrets)
        if changes.credential_hints is not None:
            assignments.append("pistas_credenciales = CAST(%s AS JSONB)")
            params.append(_config_json(changes.credential_hints))
        if not assignments:
            return self.get(channel_id)
        params.append(channel_id)
        rows = self._run(
            f"UPDATE canales SET {', '.join(assignments)} WHERE id = %s "
            f"RETURNING {_CHANNEL_COLUMNS}",
            tuple(params),
            fetch=True,
        )
        return _row_to_record(rows[0]) if rows else None

    def set_active(self, channel_id: str, active: bool) -> ChannelRecord | None:
        rows = self._run(
            f"UPDATE canales SET activo = %s, activo_segun_entorno = FALSE "
            f"WHERE id = %s RETURNING {_CHANNEL_COLUMNS}",
            (active, channel_id),
            fetch=True,
        )
        return _row_to_record(rows[0]) if rows else None

    def set_encrypted_secrets(self, channel_id: str, token: str) -> bool:
        rows = self._run(
            "UPDATE canales SET config_secreta = %s WHERE id = %s RETURNING id",
            (token, channel_id),
            fetch=True,
        )
        return bool(rows)
