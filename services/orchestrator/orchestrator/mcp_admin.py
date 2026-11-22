"""Vista de solo lectura de las ofertas MCP de DEMOSTRACIÓN (#74)."""
from __future__ import annotations

import html
from typing import Any, Sequence

from . import admin

_COLUMNS = (
    ("destino", "Destino"),
    ("titulo", "Título"),
    ("precio_cop", "Precio (COP)"),
    ("valido_desde", "Desde"),
    ("valido_hasta", "Hasta"),
)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_mcp_page(
    rows: Sequence[dict[str, Any]], available: bool, csrf: str
) -> str:
    if not available:
        body = '<p class="card">Servidor MCP: no disponible.</p>'
        return admin.render_page("MCP de lectura", body, csrf, "/admin/mcp")

    if not rows:
        body = '<p class="card">No hay ofertas de demostración.</p>'
        return admin.render_page("MCP de lectura", body, csrf, "/admin/mcp")

    head = "".join(f"<th>{_esc(title)}</th>" for _, title in _COLUMNS)
    head += "<th>Etiqueta</th>"
    lines: list[str] = []
    for row in rows:
        cells = "".join(f"<td>{_esc(row.get(key, ''))}</td>" for key, _ in _COLUMNS)
        label = row.get("etiqueta") or "DEMOSTRACIÓN"
        cells += f'<td><span class="badge">{_esc(label)}</span></td>'
        lines.append(f"<tr>{cells}</tr>")

    table = (
        "<div class=\"table-wrap\"><table><thead><tr>"
        f"{head}</tr></thead><tbody>{''.join(lines)}</tbody></table></div>"
    )
    notice = (
        '<p class="card">Ofertas de DEMOSTRACIÓN: no son ofertas reales de '
        "Lázaro Software.</p>"
    )
    return admin.render_page(
        "MCP de lectura", f"{notice}{table}", csrf, "/admin/mcp"
    )
