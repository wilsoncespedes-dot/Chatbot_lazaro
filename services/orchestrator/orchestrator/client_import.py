"""Importación de clientes desde CSV: parseo, vista previa, ejecución y resumen (#77)."""
from __future__ import annotations

import csv
import io
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable, Literal

from .accounts import USERNAME_PATTERN
from .client_id import PublicIdTaken, generate_public_id, normalize_public_id
from .client_source import FuenteDeClientes

if TYPE_CHECKING:
    from .domain import Profile

CAMPOS = ("id", "usuario", "correo", "telefono")
REQUIRED_CAMPOS = ("usuario",)
STATUSES = (
    "nueva",
    "duplicado_base",
    "duplicado_archivo",
    "conflicto",
    "invalida",
)
INACTIVE_PASSWORD_HASH = "importado$deshabilitado"
EMAIL_MAX_LENGTH = 254
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


class ImportFileError(Exception):
    """Error de estructura del archivo; `code` es el código que ve el panel."""

    def __init__(self, code: str, column: str | None = None) -> None:
        self.code = code
        self.column = column
        message = code if column is None else f"{code}: {column}"
        super().__init__(message)


@dataclass(frozen=True)
class FieldError:
    field: str
    code: str


@dataclass(frozen=True)
class ImportRow:
    number: int
    id: str | None
    usuario: str
    correo: str | None
    telefono: str | None
    errors: tuple[FieldError, ...]
    status: Literal[
        "nueva", "duplicado_base", "duplicado_archivo", "conflicto", "invalida"
    ]
    reason: str | None
    existing_profile_id: str | None


@dataclass(frozen=True)
class ImportPlan:
    rows: tuple[ImportRow, ...]


@dataclass(frozen=True)
class ImportSummary:
    created: int
    updated: int
    skipped: int
    failed: int
    details: tuple[tuple[int, str, str], ...]


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError("archivo_no_utf8") from None


def _header_fields(text: str) -> list[str]:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    separator = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(first_line), delimiter=separator)
    try:
        raw_header = next(reader)
    except StopIteration:
        raise ImportFileError("encabezado_invalido") from None
    return [column.strip().lower() for column in raw_header]


def _validate_header(header: list[str]) -> None:
    if not header or any(not column for column in header):
        raise ImportFileError("encabezado_invalido")
    unknown = [column for column in header if column not in CAMPOS]
    if unknown:
        raise ImportFileError("encabezado_invalido", unknown[0])
    for required in REQUIRED_CAMPOS:
        if required not in header:
            raise ImportFileError("encabezado_invalido", required)
    if len(set(header)) != len(header):
        duplicate = next(column for column in header if header.count(column) > 1)
        raise ImportFileError("encabezado_invalido", duplicate)


def parse_csv(data: bytes, *, max_bytes: int, max_rows: int) -> list[dict[str, str]]:
    """R4-R9, R11: lee el CSV completo en memoria, sin guardarlo en ningún sitio."""
    if len(data) > max_bytes:
        raise ImportFileError("archivo_demasiado_grande")
    text = _decode(data)
    header = _header_fields(text)
    _validate_header(header)
    first_line = text.splitlines()[0] if text.splitlines() else ""
    separator = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=separator)
    next(reader, None)
    rows: list[dict[str, str]] = []
    for raw in reader:
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(rows) >= max_rows:
            raise ImportFileError("demasiadas_filas")
        rows.append({field: raw[index] for index, field in enumerate(header)
                     if index < len(raw)})
    return rows


_XLSX_MAGIC = b"PK"
_XLSX_MAX_UNCOMPRESSED = 20 * 1024 * 1024


def _xlsx_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_xlsx(data: bytes, *, max_bytes: int, max_rows: int) -> list[dict[str, str]]:
    """Lee la primera hoja de un .xlsx (solo valores, sin macros ni fórmulas)."""
    import zipfile

    from openpyxl import load_workbook

    if len(data) > max_bytes:
        raise ImportFileError("archivo_demasiado_grande")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > _XLSX_MAX_UNCOMPRESSED:
                raise ImportFileError("archivo_demasiado_grande")
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except ImportFileError:
        raise
    except Exception:
        raise ImportFileError("xlsx_invalido") from None
    try:
        sheet = workbook.worksheets[0]
        iterator = sheet.iter_rows(values_only=True)
        first = next(iterator, None)
        if first is None:
            raise ImportFileError("encabezado_invalido")
        header = [_xlsx_cell(cell).lower() for cell in first]
        while header and not header[-1]:
            header.pop()
        _validate_header(header)
        rows: list[dict[str, str]] = []
        for raw in iterator:
            cells = [_xlsx_cell(cell) for cell in raw[: len(header)]]
            if not any(cells):
                continue
            if len(rows) >= max_rows:
                raise ImportFileError("demasiadas_filas")
            rows.append({field: cells[i] for i, field in enumerate(header) if i < len(cells)})
        return rows
    finally:
        workbook.close()


def parse_upload(data: bytes, *, max_bytes: int, max_rows: int) -> list[dict[str, str]]:
    """Elige el lector por el contenido: .xlsx (zip) o CSV UTF-8."""
    if data.startswith(_XLSX_MAGIC):
        return parse_xlsx(data, max_bytes=max_bytes, max_rows=max_rows)
    return parse_csv(data, max_bytes=max_bytes, max_rows=max_rows)


def _control(value: str) -> bool:
    return bool(_CONTROL_RE.search(value))


def _validate_row(raw: dict[str, str]) -> tuple[
    str | None, str, str | None, str | None, tuple[FieldError, ...]
]:
    errors: list[FieldError] = []
    raw_id = (raw.get("id") or "").strip()
    raw_usuario = (raw.get("usuario") or "").strip()
    raw_correo = (raw.get("correo") or "").strip()
    raw_telefono = (raw.get("telefono") or "").strip()

    usuario = raw_usuario.lower()
    if not usuario or not USERNAME_PATTERN.fullmatch(usuario) or _control(usuario):
        errors.append(FieldError("usuario", "usuario_invalido"))

    normal_id: str | None = None
    if raw_id:
        normal_id = normalize_public_id(raw_id) if not _control(raw_id) else None
        if normal_id is None:
            errors.append(FieldError("id", "id_invalido"))
            normal_id = raw_id

    correo: str | None = None
    if raw_correo:
        correo = raw_correo.lower()
        if (
            _control(correo)
            or len(correo) > EMAIL_MAX_LENGTH
            or not _EMAIL_RE.fullmatch(correo)
        ):
            errors.append(FieldError("correo", "correo_invalido"))

    telefono: str | None = None
    if raw_telefono:
        cleaned = re.sub(r"[ \-()]", "", raw_telefono)
        if not _control(cleaned) and _PHONE_RE.fullmatch(cleaned):
            telefono = cleaned
        else:
            errors.append(FieldError("telefono", "telefono_invalido"))
            telefono = raw_telefono

    return normal_id, usuario, correo, telefono, tuple(errors)


def _keys(
    id_value: str | None, correo: str | None, telefono: str | None, usuario: str
) -> tuple[tuple[str, str], ...]:
    keys: list[tuple[str, str]] = []
    if id_value:
        keys.append(("id", id_value))
    if correo:
        keys.append(("correo", correo))
    if telefono:
        keys.append(("telefono", telefono))
    if usuario:
        keys.append(("usuario", usuario))
    return tuple(keys)


def build_plan(
    rows: list[dict[str, str]], source: FuenteDeClientes
) -> ImportPlan:
    """R12-R23: valida, normaliza y cruza duplicados sin escribir nada."""
    existing_usernames = {
        row.profile.username.lower(): row.profile.id for row in source.listar()
    }
    seen: dict[tuple[str, str], int] = {}
    plan_rows: list[ImportRow] = []
    for number, raw in enumerate(rows, start=1):
        id_value, usuario, correo, telefono, errors = _validate_row(raw)
        status: str = "invalida" if errors else "nueva"
        reason: str | None = (
            ",".join(error.code for error in errors) if errors else None
        )
        existing_profile_id: str | None = None

        if not errors:
            file_match = next(
                (
                    (key, origin)
                    for key in _keys(id_value, correo, telefono, usuario)
                    if (origin := seen.get(key)) is not None
                ),
                None,
            )
            if file_match is not None:
                key, origin_number = file_match
                status = "duplicado_archivo"
                reason = f"{key[0]} (fila {origin_number})"
            else:
                matches: list[tuple[str, str]] = []
                id_match = source.buscar_por_id(id_value) if id_value else None
                if id_match is not None:
                    matches.append(("id", id_match.profile.id))
                email_match = source.buscar_por_correo(correo) if correo else None
                if email_match is not None:
                    matches.append(("correo", email_match))
                phone_match = source.buscar_por_telefono(telefono) if telefono else None
                if phone_match is not None:
                    matches.append(("telefono", phone_match))
                distinct = {profile_id for _, profile_id in matches}
                if len(distinct) > 1:
                    status = "conflicto"
                    reason = "conflicto_multiple"
                elif matches:
                    status = "duplicado_base"
                    reason = matches[0][0]
                    existing_profile_id = matches[0][1]
                elif usuario in existing_usernames:
                    status = "invalida"
                    reason = "usuario_tomado"
                    errors = (FieldError("usuario", "usuario_tomado"),)

            if status in ("nueva", "duplicado_base", "conflicto"):
                for key in _keys(id_value, correo, telefono, usuario):
                    seen.setdefault(key, number)

        plan_rows.append(
            ImportRow(
                number=number,
                id=id_value,
                usuario=usuario,
                correo=correo,
                telefono=telefono,
                errors=errors,
                status=status,  # type: ignore[arg-type]
                reason=reason,
                existing_profile_id=existing_profile_id,
            )
        )
    return ImportPlan(rows=tuple(plan_rows))


def _create_imported(
    row: ImportRow,
    source: FuenteDeClientes,
    now: datetime,
) -> Profile:
    valid_from = now - timedelta(days=1)
    attempts = 1 if row.id else 5
    for _ in range(attempts):
        public_id = row.id or generate_public_id()
        try:
            return source.crear(
                row.usuario,
                INACTIVE_PASSWORD_HASH,
                valid_from,
                now,
                now,
                public_id,
                correo=row.correo,
                telefono=row.telefono,
            )
        except PublicIdTaken:
            if row.id:
                raise
    raise PublicIdTaken("El ID de cliente ya existe.")


def run_import(
    plan: ImportPlan,
    policy: Literal["actualizar", "saltar"],
    source: FuenteDeClientes,
    now: datetime,
) -> ImportSummary:
    """R25-R31, R37, R38: ejecuta el plan y resume cada fila sin datos personales."""
    created = updated = skipped = failed = 0
    details: list[tuple[int, str, str]] = []
    for row in plan.rows:
        if row.status == "invalida":
            failed += 1
            details.append((row.number, "fallido", row.reason or "invalida"))
            continue
        if row.status == "duplicado_archivo":
            skipped += 1
            details.append((row.number, "saltado", row.reason or "duplicado_archivo"))
            continue
        if row.status == "conflicto":
            failed += 1
            details.append((row.number, "fallido", "conflicto_multiple"))
            continue
        if row.status == "duplicado_base":
            if policy == "saltar" or row.existing_profile_id is None:
                skipped += 1
                details.append((row.number, "saltado", row.reason or "duplicado_base"))
                continue
            try:
                changed = source.actualizar_contacto(
                    row.existing_profile_id,
                    now,
                    correo=row.correo,
                    telefono=row.telefono,
                )
            except Exception:
                failed += 1
                details.append((row.number, "fallido", "error_escritura"))
                continue
            if changed:
                updated += 1
                details.append((row.number, "actualizado", ""))
            else:
                failed += 1
                details.append((row.number, "fallido", "no_encontrado"))
            continue
        try:
            _create_imported(row, source, now)
        except Exception as error:
            failed += 1
            if getattr(error, "code", None) == "username_taken":
                code = "usuario_tomado"
            elif isinstance(error, PublicIdTaken):
                code = "id_tomado"
            else:
                code = "error_escritura"
            details.append((row.number, "fallido", code))
            continue
        created += 1
        details.append((row.number, "creado", ""))
    return ImportSummary(
        created=created,
        updated=updated,
        skipped=skipped,
        failed=failed,
        details=tuple(details),
    )


def csv_safe(cell: str) -> str:
    """R34: neutraliza fórmulas al exportar el resumen."""
    text = str(cell)
    if text.startswith(_CSV_DANGEROUS):
        return f"'{text}"
    return text


def summary_to_csv(summary: ImportSummary) -> str:
    """R34, R35: CSV del resumen, con celdas protegidas y sin correo ni teléfono."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["fila", "estado", "motivo"])
    for number, state, reason in summary.details:
        writer.writerow(
            [csv_safe(str(number)), csv_safe(state), csv_safe(reason)]
        )
    return buffer.getvalue()


class ImportStaging:
    """R10, R33: vista previa y resumen en memoria, con TTL y ligados a la sesión."""

    def __init__(
        self, ttl_seconds: int, clock: Callable[[], datetime]
    ) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._plans: dict[str, tuple[str, ImportPlan, datetime]] = {}
        self._summaries: dict[str, tuple[str, ImportSummary, datetime]] = {}

    def _cleanup(self, store: dict) -> None:
        now = self._clock()
        for token in [
            token for token, (_, _, expires_at) in store.items()
            if expires_at <= now
        ]:
            store.pop(token, None)

    def put(self, session_id: str, plan: ImportPlan) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._cleanup(self._plans)
            self._plans[token] = (session_id, plan, self._clock() + self._ttl)
        return token

    def pop(self, session_id: str, token: str) -> ImportPlan | None:
        with self._lock:
            item = self._plans.pop(token, None)
            if item is None:
                return None
            owner, plan, expires_at = item
            if owner != session_id or expires_at <= self._clock():
                return None
            return plan

    def put_summary(self, session_id: str, summary: ImportSummary) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._cleanup(self._summaries)
            self._summaries[token] = (
                session_id,
                summary,
                self._clock() + self._ttl,
            )
        return token

    def get_summary(self, session_id: str, token: str) -> ImportSummary | None:
        with self._lock:
            self._cleanup(self._summaries)
            item = self._summaries.get(token)
            if item is None:
                return None
            owner, summary, expires_at = item
            if owner != session_id or expires_at <= self._clock():
                self._summaries.pop(token, None)
                return None
            return summary


def preview_audit_result(plan: ImportPlan) -> str:
    """R42: totales por estado para auditoría, sin nombres ni contactos."""
    counts = {status: 0 for status in STATUSES}
    for row in plan.rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return (
        f"filas={len(plan.rows)};nuevas={counts['nueva']};"
        f"duplicadas={counts['duplicado_base'] + counts['duplicado_archivo']};"
        f"conflictos={counts['conflicto']};invalidas={counts['invalida']}"
    )


def summary_audit_result(summary: ImportSummary) -> str:
    """R42: totales del resultado, sin datos personales."""
    return (
        f"creados={summary.created};actualizados={summary.updated};"
        f"saltados={summary.skipped};fallidos={summary.failed}"
    )
