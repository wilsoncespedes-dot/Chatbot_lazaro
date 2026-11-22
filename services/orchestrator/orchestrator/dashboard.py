"""Gráficos SVG del dashboard (#75): funciones puras, sin IO ni JavaScript."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .administration import median_minutes, percentile_minutes
from .channel_label import NEUTRAL_COLOR, render_channel_label

DASHBOARD_MAX_CHANNELS = 12
DASHBOARD_MESSAGE_ROLES = frozenset({"user", "bot", "advisor"})

CASE_STATUS_ORDER = ("open", "assigned", "timed_out", "closed")
CASE_STATUS_LABELS = {
    "open": "Abierta",
    "assigned": "Asignada",
    "timed_out": "Vencida",
    "closed": "Cerrada",
}
# R33: colores fijos con contraste >= 4.5 sobre blanco.
CASE_STATUS_COLORS = {
    "open": "#1D4ED8",
    "assigned": "#14532D",
    "timed_out": "#6B3F00",
    "closed": "#374151",
}
MEDIAN_COLOR = "#1D4ED8"
P90_COLOR = "#7A1F00"

CHART_WIDTH = 640
CHART_PADDING = 16
ROW_HEIGHT = 30
LABEL_WIDTH = 220
BAR_MAX_WIDTH = 330
BAR_HEIGHT = 18
TEXT_COLOR = "#1B2733"
MUTED_COLOR = "#4A5568"

__all__ = [
    "BarDatum",
    "Cell",
    "DASHBOARD_MAX_CHANNELS",
    "DASHBOARD_MESSAGE_ROLES",
    "CASE_STATUS_COLORS",
    "CASE_STATUS_LABELS",
    "CASE_STATUS_ORDER",
    "MEDIAN_COLOR",
    "P90_COLOR",
    "ResponseSummary",
    "advisor_response_minutes",
    "group_top",
    "render_bar_chart",
    "render_chart_block",
    "render_dashboard_body",
    "render_data_table",
    "response_summary",
]


@dataclass(frozen=True)
class BarDatum:
    label: str
    value: float
    color: str


@dataclass(frozen=True)
class ResponseSummary:
    count: int
    median: float | None
    p90: float | None


@dataclass(frozen=True)
class Cell:
    """Celda HTML ya construida (por ejemplo, la etiqueta de canal de #67)."""

    html: str


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _is_empty(data: Sequence[BarDatum]) -> bool:
    return not data or all(datum.value <= 0 for datum in data)


def _data_description(title: str, data: Sequence[BarDatum], unit: str) -> str:
    if _is_empty(data):
        return f"{title}: sin datos."
    summary = ", ".join(
        f"{datum.label}: {_format_number(datum.value)}{unit}" for datum in data
    )
    return f"{title}. {summary}."


def _svg_open(chart_id: str, title: str, description: str, height: int) -> str:
    title_id = f"{chart_id}-title"
    desc_id = f"{chart_id}-desc"
    return (
        f'<svg id="{_esc(chart_id)}" viewBox="0 0 {CHART_WIDTH} {height}" '
        f'width="{CHART_WIDTH}" height="{height}" role="img" '
        f'aria-labelledby="{_esc(title_id)} {_esc(desc_id)}">'
        f'<title id="{_esc(title_id)}">{_esc(title)}</title>'
        f'<desc id="{_esc(desc_id)}">{_esc(description)}</desc>'
    )


def render_bar_chart(
    chart_id: str,
    title: str,
    desc: str,
    data: Sequence[BarDatum],
    unit: str = "",
) -> str:
    """R27, R29, R32, R33: SVG de barras horizontales generado en el servidor."""
    description = desc or _data_description(title, data, unit)
    if _is_empty(data):
        height = CHART_PADDING * 2 + ROW_HEIGHT
        return (
            _svg_open(chart_id, title, description, height)
            + f'<text x="{CHART_PADDING}" y="{CHART_PADDING + 20}" '
            f'fill="{MUTED_COLOR}" font-size="14">Sin datos</text></svg>'
        )
    max_value = max(datum.value for datum in data)
    height = CHART_PADDING * 2 + ROW_HEIGHT * len(data)
    parts = [_svg_open(chart_id, title, description, height)]
    bar_x = CHART_PADDING + LABEL_WIDTH
    value_x = bar_x + BAR_MAX_WIDTH + 8
    for index, datum in enumerate(data):
        top = CHART_PADDING + index * ROW_HEIGHT
        width = 0.0 if max_value <= 0 else datum.value / max_value * BAR_MAX_WIDTH
        parts.append(
            f'<text x="{CHART_PADDING}" y="{top + 20}" fill="{TEXT_COLOR}" '
            f'font-size="13">{_esc(datum.label)}</text>'
            f'<rect x="{bar_x}" y="{top + 5}" width="{width:.1f}" '
            f'height="{BAR_HEIGHT}" rx="3" fill="{_esc(datum.color)}"></rect>'
            f'<text x="{value_x}" y="{top + 20}" fill="{TEXT_COLOR}" '
            f'font-size="13">{_esc(_format_number(datum.value))}{_esc(unit)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_data_table(
    caption: str, headers: Sequence[str], rows: Sequence[Sequence[object]]
) -> str:
    """R30, R31: tabla accesible con `<caption>`, encabezados y valores escapados."""
    head = "".join(
        f'<th scope="col">{_esc(header)}</th>' for header in headers
    )
    body_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        for index, cell in enumerate(row):
            content = cell.html if isinstance(cell, Cell) else _esc(cell)
            if index == 0:
                cells.append(f'<th scope="row">{content}</th>')
            else:
                cells.append(f"<td>{content}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    if not body_rows:
        body_rows.append(f'<tr><td colspan="{len(headers)}">Sin datos</td></tr>')
    return (
        f"<table><caption>{_esc(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def render_chart_block(
    chart_id: str,
    title: str,
    desc: str,
    data: Sequence[BarDatum],
    unit: str = "",
    headers: Sequence[str] | None = None,
    rows: Sequence[Sequence[object]] | None = None,
) -> str:
    """R29, R30: título visible, SVG y tabla de datos del mismo gráfico."""
    table_headers = tuple(headers) if headers is not None else ("Elemento", "Valor")
    table_rows: Sequence[Sequence[object]] = ()
    if not _is_empty(data):
        if rows is not None:
            table_rows = rows
        else:
            table_rows = [(datum.label, _format_number(datum.value)) for datum in data]
    return (
        f'<section class="dashboard-chart">'
        f"<h3>{_esc(title)}</h3>"
        f"{render_bar_chart(chart_id, title, desc, data, unit)}"
        f"{render_data_table(title, table_headers, table_rows)}"
        "</section>"
    )


def group_top(data: Sequence[BarDatum], max_items: int) -> list[BarDatum]:
    """R13: barras de mayor conteo y el resto agrupado en «Otros»."""
    items = list(data)
    if max_items <= 0:
        return []
    if len(items) <= max_items:
        return items
    ordered = sorted(items, key=lambda datum: (-datum.value, datum.label))
    keep = ordered[: max_items - 1]
    rest = ordered[max_items - 1 :]
    others = sum(datum.value for datum in rest)
    return keep + [BarDatum("Otros", others, NEUTRAL_COLOR)]


def advisor_response_minutes(
    rows: Sequence[tuple[str, str, datetime]]
) -> list[float]:
    """R18, R19: minutos entre cada mensaje de cliente y el siguiente de asesor."""
    by_contact: dict[str, list[tuple[str, datetime]]] = {}
    for contact_id, role, at in sorted(rows, key=lambda row: row[2]):
        by_contact.setdefault(contact_id, []).append((role, at))
    minutes: list[float] = []
    for items in by_contact.values():
        for index, (role, at) in enumerate(items):
            if role != "user":
                continue
            following = next(
                (
                    reply_at
                    for reply_role, reply_at in items[index + 1 :]
                    if reply_role == "advisor" and reply_at > at
                ),
                None,
            )
            if following is None:
                continue
            minutes.append((following - at).total_seconds() / 60)
    return minutes


def response_summary(minutes: Sequence[float]) -> ResponseSummary:
    """R25: reutiliza la mediana existente y añade el p90."""
    values = list(minutes)
    return ResponseSummary(
        count=len(values),
        median=median_minutes(values),
        p90=percentile_minutes(values, 90),
    )


def _filter_form(days: int, include_simulated: bool, action: str) -> str:
    """R6: formulario GET sin JavaScript con los valores actuales seleccionados."""
    include_selected = " selected" if include_simulated else ""
    exclude_selected = "" if include_simulated else " selected"
    return (
        f'<form method="get" action="{_esc(action)}" class="card dashboard-filter">'
        '<label>Rango (días) '
        f'<input type="number" name="dias" min="1" max="90" value="{days}" required>'
        "</label>"
        '<label>Canales simulados '
        '<select name="simulados">'
        f'<option value="incluir"{include_selected}>Incluir</option>'
        f'<option value="excluir"{exclude_selected}>Excluir</option>'
        "</select></label>"
        '<button type="submit">Actualizar dashboard</button>'
        "</form>"
    )


def render_dashboard_body(
    data, days: int, include_simulated: bool, action: str
) -> str:
    """R6, R9-R24, R29-R33: cuerpo HTML completo del dashboard."""
    message_rows = tuple(
        (Cell(render_channel_label(label)), count)
        for label, count in data.message_labels
    )
    parts = [
        _filter_form(days, include_simulated, action),
        f"<p>Intervalo: {_esc(data.since.isoformat())} — "
        f"{_esc(data.until.isoformat())}</p>",
        render_chart_block(
            "dashboard-messages",
            "Mensajes por canal",
            _data_description("Mensajes por canal", data.messages, ""),
            data.messages,
            headers=("Canal", "Mensajes"),
            rows=message_rows,
        ),
    ]
    if data.statuses is None:
        parts.append(
            "<section class=\"dashboard-chart\">"
            "<h3>Conversaciones por estado</h3>"
            '<p class="error" role="alert">'
            "El servicio de casos no está disponible."
            "</p></section>"
        )
    else:
        parts.append(
            render_chart_block(
                "dashboard-statuses",
                "Conversaciones por estado",
                _data_description(
                    "Conversaciones por estado", data.statuses, ""
                ),
                data.statuses,
                headers=("Estado", "Casos"),
                rows=data.status_rows,
            )
        )
    parts.append(
        f"<p>Primera respuesta: casos {_esc(data.first_response.cases)} · "
        f"respondidos {_esc(data.first_response.answered)} · "
        f"sin respuesta {_esc(data.first_response.unanswered)}.</p>"
    )
    parts.append(
        render_chart_block(
            "dashboard-response-times",
            "Tiempos de respuesta",
            _data_description(
                "Tiempos de respuesta", data.response_times, " min"
            ),
            data.response_times,
            unit=" min",
            headers=("Medida", "Cantidad", "Mediana (min)", "p90 (min)"),
            rows=data.response_rows,
        )
    )
    return "".join(parts)
