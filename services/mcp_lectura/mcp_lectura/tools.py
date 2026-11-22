"""Lógica pura de las herramientas MCP de solo lectura (#74)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable, Mapping

from pydantic import BaseModel

if TYPE_CHECKING:
    from .adapters import AuditSink, DemoOffersStore, RagSearch

READ_ONLY_TOOLS: tuple[str, ...] = ("buscar_manuales", "ofertas_demo")

FORBIDDEN_INPUT_FIELDS = frozenset(
    {"cliente_id", "user_id", "contact_id", "telegram_user_id"}
)

DEMO_LABEL = "DEMOSTRACIÓN"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    read_only_hint: bool = True


TOOL_ANNOTATIONS: Mapping[str, bool] = MappingProxyType({"readOnlyHint": True})

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="buscar_manuales",
        description=(
            "Busca en los manuales de soporte y devuelve los fragmentos relevantes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "minLength": 1, "maxLength": 4096},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["consulta"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="ofertas_demo",
        description=(
            "Consulta ofertas de DEMOSTRACIÓN por destino y rango de fechas. "
            "Nunca son ofertas reales de Lázaro Software."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "destino": {"type": "string", "minLength": 1, "maxLength": 100},
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
            },
            "required": ["destino"],
            "additionalProperties": False,
        },
    ),
)

assert tuple(spec.name for spec in TOOL_SPECS) == READ_ONLY_TOOLS


class ToolResult(BaseModel):
    rows: list[dict[str, Any]]
    demo: bool = False


class AuditRecord(BaseModel):
    herramienta: str
    args_sha256: str
    filas: int
    estado: str
    cliente_sha256: str
    creado_en: datetime


class ToolFailure(Exception):
    """La herramienta no pudo completarse; nunca lleva datos al cliente."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def args_sha256(args: Mapping[str, object]) -> str:
    """Huella canónica de los argumentos; nunca guarda sus valores."""
    canonical = json.dumps(
        dict(args), sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def buscar_manuales(
    consulta: str, rag: "RagSearch", top_k: int
) -> ToolResult:
    """R4: solo delega en la búsqueda del RAG, sin ninguna otra ruta."""
    text = consulta.strip()
    if not text:
        raise ToolFailure("consulta_vacia")
    limit = max(1, min(int(top_k), 20))
    rows = rag.search(text, limit)
    return ToolResult(rows=[dict(row) for row in rows], demo=False)


def ofertas_demo(
    destino: str,
    desde: date | None,
    hasta: date | None,
    store: "DemoOffersStore",
    max_rows: int,
) -> ToolResult:
    """R3, R12: consulta de demostración marcada en cada fila."""
    target = destino.strip()
    if not target:
        raise ToolFailure("destino_vacio")
    start = desde or date.today()
    end = hasta or start
    if end < start:
        raise ToolFailure("rango_invalido")
    limit = max(1, int(max_rows))
    rows = store.buscar(target, start, end, limit)
    marked: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["es_demo"] = True
        item["etiqueta"] = DEMO_LABEL
        marked.append(item)
    return ToolResult(rows=marked, demo=True)


def _audit(
    sink: "AuditSink", record: AuditRecord
) -> None:
    try:
        sink.record(record)
    except Exception:
        raise ToolFailure("audit_failed") from None


def run_audited(
    name: str,
    arguments: Mapping[str, object],
    cliente_id: str,
    sink: "AuditSink",
    action: Callable[[], ToolResult],
    clock: Callable[[], datetime] = _utcnow,
) -> list[dict[str, Any]]:
    """R9-R11: audita siempre y falla cerrado si la auditoría no se puede escribir."""
    digest = args_sha256(arguments)
    cliente_digest = hashlib.sha256(
        (cliente_id or "").encode("utf-8")
    ).hexdigest()
    created_at = clock()
    try:
        result = action()
    except Exception:
        _audit(
            sink,
            AuditRecord(
                herramienta=name,
                args_sha256=digest,
                filas=0,
                estado="error",
                cliente_sha256=cliente_digest,
                creado_en=created_at,
            ),
        )
        raise
    rows = [dict(row) for row in result.rows]
    _audit(
        sink,
        AuditRecord(
            herramienta=name,
            args_sha256=digest,
            filas=len(rows),
            estado="ok",
            cliente_sha256=cliente_digest,
            creado_en=created_at,
        ),
    )
    return rows
