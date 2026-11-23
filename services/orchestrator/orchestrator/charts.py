"""Fase 5: gráficos PNG generados en el servidor con Python puro.

Sin dependencias pesadas: un lienzo RGB en memoria, una fuente de mapa de bits
de 5x7 y `zlib` para codificar el PNG. Lógica pura, sin IO: resultado de una
consulta → `ChartSpec` → PNG + frase con la cifra clave. La firma de los enlaces
temporales también vive aquí para que la ruta y el dominio usen la misma.
"""
from __future__ import annotations

import bisect
import hashlib
import hmac
import math
import re
import struct
import unicodedata
import zlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Mapping

from .db_query import QueryResult

ChartKind = Literal["barras", "lineas", "torta"]
CHART_KINDS: tuple[str, ...] = ("barras", "lineas", "torta")
PIE_MAX_CATEGORIES = 6
BAR_MAX_CATEGORIES = 12
LINE_MAX_POINTS = 60
CHART_ID_RE = re.compile(r"[0-9a-f]{32}")
CHART_MEDIA_PREFIX = "/media/graficos/"

CHART_SQL_HINT = (
    "La respuesta se usará para dibujar un gráfico: devuelve exactamente dos "
    "columnas, primero una etiqueta o una fecha y después un valor numérico "
    "agregado (por ejemplo COUNT(*) con GROUP BY), ordenadas de forma útil."
)

__all__ = [
    "BAR_MAX_CATEGORIES",
    "CHART_KINDS",
    "CHART_MEDIA_PREFIX",
    "CHART_SQL_HINT",
    "ChartKind",
    "ChartSpec",
    "LINE_MAX_POINTS",
    "PIE_MAX_CATEGORIES",
    "chart_from_result",
    "chart_link_valid",
    "chart_summary",
    "chart_url",
    "encode_png",
    "format_number",
    "render_chart_png",
    "requested_chart_kind",
    "sign_chart",
]

Color = tuple[int, int, int]
WHITE: Color = (255, 255, 255)
TEXT: Color = (0x1B, 0x27, 0x33)
MUTED: Color = (0x4A, 0x55, 0x68)
GRID: Color = (0xCB, 0xD5, 0xE1)
BAR: Color = (0x1D, 0x4E, 0xD8)
LINE: Color = (0x1D, 0x4E, 0xD8)
# Mismos tonos con contraste >= 4.5 sobre blanco que usa el dashboard (#75).
PALETTE: tuple[Color, ...] = (
    (0x1D, 0x4E, 0xD8),
    (0xB4, 0x53, 0x09),
    (0x04, 0x78, 0x57),
    (0x7C, 0x3A, 0xED),
    (0xBE, 0x12, 0x3C),
    (0x0F, 0x76, 0x6E),
)

# Fuente 5x7: cada fila es un entero de 5 bits (bit 4 = columna izquierda).
_FONT: Mapping[str, tuple[int, ...]] = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    ".": (0, 0, 0, 0, 0, 0x0C, 0x0C),
    ",": (0, 0, 0, 0, 0x0C, 0x04, 0x08),
    ":": (0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0),
    ";": (0, 0x0C, 0x0C, 0, 0x0C, 0x04, 0x08),
    "-": (0, 0, 0, 0x1F, 0, 0, 0),
    "_": (0, 0, 0, 0, 0, 0, 0x1F),
    "+": (0, 0x04, 0x04, 0x1F, 0x04, 0x04, 0),
    "=": (0, 0, 0x1F, 0, 0x1F, 0, 0),
    "/": (0, 0x01, 0x02, 0x04, 0x08, 0x10, 0),
    "%": (0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03),
    "(": (0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02),
    ")": (0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08),
    "<": (0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02),
    ">": (0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08),
    "?": (0x0E, 0x11, 0x01, 0x02, 0x04, 0, 0x04),
    "!": (0x04, 0x04, 0x04, 0x04, 0x04, 0, 0x04),
    "'": (0x0C, 0x04, 0x08, 0, 0, 0, 0),
    '"': (0x0A, 0x0A, 0x0A, 0, 0, 0, 0),
    "#": (0x0A, 0x0A, 0x1F, 0x0A, 0x1F, 0x0A, 0x0A),
    "$": (0x04, 0x0F, 0x14, 0x0E, 0x05, 0x1E, 0x04),
    "&": (0x0C, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0D),
    "*": (0, 0x04, 0x15, 0x0E, 0x15, 0x04, 0),
    "@": (0x0E, 0x11, 0x01, 0x0D, 0x15, 0x15, 0x0E),
}
_GLYPH_W = 5
_GLYPH_H = 7
_REPLACEMENTS = {"«": '"', "»": '"', "“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"}


@dataclass(frozen=True)
class ChartSpec:
    kind: ChartKind
    title: str
    labels: tuple[str, ...]
    values: tuple[float, ...]


# ── texto ──────────────────────────────────────────────────────────────────


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _glyph_text(text: str) -> str:
    """Mayúsculas ASCII que la fuente sabe dibujar; lo demás se vuelve `?`."""
    replaced = "".join(_REPLACEMENTS.get(ch, ch) for ch in text)
    upper = _strip_accents(replaced).upper()
    return "".join(ch if ch in _FONT else "?" for ch in upper)


def _text_width(text: str, scale: int) -> int:
    count = len(_glyph_text(text))
    return 0 if count == 0 else count * (_GLYPH_W + 1) * scale - scale


def _fit(text: str, max_px: int, scale: int) -> str:
    """Recorta con `..` para que el texto quepa en `max_px` píxeles."""
    if _text_width(text, scale) <= max_px:
        return text
    limit = max(1, (max_px + scale) // ((_GLYPH_W + 1) * scale))
    if limit <= 2:
        return text[:limit]
    return text[: limit - 2] + ".."


def format_number(value: float) -> str:
    """Formato es-CO: miles con punto y un decimal con coma (1.234,5)."""
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    text = f"{value:,.1f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _humanize(name: str) -> str:
    text = name.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Valor"


# ── lienzo y PNG ───────────────────────────────────────────────────────────


class _Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(WHITE) * (width * height))

    def fill_rect(self, x: float, y: float, w: float, h: float, color: Color) -> None:
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, int(x + w))
        y1 = min(self.height, int(y + h))
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            start = (yy * self.width + x0) * 3
            self.pixels[start : start + len(row)] = row

    def text(self, x: int, y: int, text: str, color: Color, scale: int = 2) -> None:
        cursor = x
        for ch in _glyph_text(text):
            for row_index, bits in enumerate(_FONT[ch]):
                for col in range(_GLYPH_W):
                    if bits & (1 << (_GLYPH_W - 1 - col)):
                        self.fill_rect(
                            cursor + col * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor += (_GLYPH_W + 1) * scale

    def line(
        self, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int = 3
    ) -> None:
        """Bresenham con un pincel cuadrado de `thickness` píxeles."""
        half = thickness // 2
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.fill_rect(x0 - half, y0 - half, thickness, thickness, color)
            if x0 == x1 and y0 == y1:
                return
            doubled = 2 * err
            if doubled >= dy:
                err += dy
                x0 += sx
            if doubled <= dx:
                err += dx
                y0 += sy

    def png(self) -> bytes:
        return encode_png(self.width, self.height, bytes(self.pixels))


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """PNG RGB de 8 bits sin filtros, comprimido con zlib."""
    if len(rgb) != width * height * 3:
        raise ValueError("el tamaño del lienzo no coincide")
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride : (y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


# ── datos → especificación ─────────────────────────────────────────────────


def _is_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    return math.isfinite(float(value))


def _label_text(value: object) -> str:
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == 0:
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    text = "" if value is None else str(value).strip()
    return text or "(sin dato)"


def requested_chart_kind(
    text: str, args: Mapping[str, str] | None = None
) -> ChartKind | None:
    """Tipo pedido por el router (`args.tipo`) o por palabras del mensaje."""
    if args:
        tipo = args.get("tipo")
        if tipo in CHART_KINDS:
            return tipo  # type: ignore[return-value]
    words = set(re.findall(r"[a-z]+", _strip_accents(text).lower()))
    if words & {"torta", "pastel", "circular", "pie", "dona"}:
        return "torta"
    if words & {"linea", "lineas", "evolucion", "tendencia", "historico"}:
        return "lineas"
    if words & {"barra", "barras"}:
        return "barras"
    return None


def chart_from_result(
    result: QueryResult, requested: ChartKind | None = None
) -> ChartSpec | None:
    """Etiqueta + valor numérico → gráfico; None si no hay nada que dibujar.

    Nunca produce un gráfico vacío: sin filas, sin columna numérica, sin
    columna de etiqueta o con todos los valores en cero devuelve None.
    """
    columns = list(result.columns)
    rows = [tuple(row) for row in result.rows]
    if not rows or not columns:
        return None
    value_index: int | None = None
    for index in reversed(range(len(columns))):
        present = [row[index] for row in rows if index < len(row) and row[index] is not None]
        if present and all(_is_number(value) for value in present):
            value_index = index
            break
    if value_index is None:
        return None
    label_index = next(
        (index for index in range(len(columns)) if index != value_index), None
    )
    if label_index is None:
        return None

    points = [
        (row[label_index], float(row[value_index]))
        for row in rows
        if len(row) > max(label_index, value_index) and row[value_index] is not None
    ]
    if not points or all(value == 0 for _, value in points):
        return None
    temporal = all(isinstance(label, (date, datetime)) for label, _ in points)
    if temporal:
        points.sort(key=lambda point: point[0].isoformat())

    if requested == "torta":
        fits = len(points) <= PIE_MAX_CATEGORIES and all(v > 0 for _, v in points)
        kind: ChartKind = "torta" if fits else "barras"
    elif requested == "lineas":
        kind = "lineas" if len(points) >= 2 else "barras"
    elif requested == "barras":
        kind = "barras"
    else:
        kind = "lineas" if temporal and len(points) >= 2 else "barras"

    labelled = [(_label_text(label), value) for label, value in points]
    if kind == "barras" and len(labelled) > BAR_MAX_CATEGORIES:
        if temporal:
            labelled = labelled[-BAR_MAX_CATEGORIES:]
        else:
            ordered = sorted(labelled, key=lambda item: (-item[1], item[0]))
            keep = ordered[: BAR_MAX_CATEGORIES - 1]
            others = sum(value for _, value in ordered[BAR_MAX_CATEGORIES - 1 :])
            labelled = keep + [("Otros", others)]
    if kind == "lineas" and len(labelled) > LINE_MAX_POINTS:
        labelled = labelled[-LINE_MAX_POINTS:]

    title = f"{_humanize(columns[value_index])} por {_humanize(columns[label_index]).lower()}"
    return ChartSpec(
        kind=kind,
        title=title,
        labels=tuple(label for label, _ in labelled),
        values=tuple(value for _, value in labelled),
    )


def chart_summary(spec: ChartSpec) -> str:
    """Una frase con la cifra clave del gráfico."""
    values = spec.values
    labels = spec.labels
    if spec.kind == "lineas":
        top = max(range(len(values)), key=lambda index: values[index])
        return (
            f"{spec.title}: el último valor es {format_number(values[-1])} "
            f"({labels[-1]}), frente a {format_number(values[0])} ({labels[0]}); "
            f"el máximo fue {format_number(values[top])} ({labels[top]})."
        )
    top = max(range(len(values)), key=lambda index: values[index])
    if len(values) == 1:
        return f"{spec.title}: «{labels[0]}» con {format_number(values[0])}."
    total = sum(values)
    share = f" ({values[top] / total * 100:.0f} %)" if total > 0 else ""
    return (
        f"{spec.title}: «{labels[top]}» es el mayor con "
        f"{format_number(values[top])} de {format_number(total)} en total{share}."
    )


# ── dibujo ─────────────────────────────────────────────────────────────────

_SCALE = 2
_PAD = 24
_WIDTH = 720
_TEXT_H = _GLYPH_H * _SCALE


def _render_bars(spec: ChartSpec) -> bytes:
    label_w = 220
    value_w = 112
    row_h = 34
    bar_max = _WIDTH - _PAD * 2 - label_w - value_w
    top = _PAD + _TEXT_H + 18
    height = top + row_h * len(spec.values) + _PAD
    canvas = _Canvas(_WIDTH, height)
    canvas.text(_PAD, _PAD, _fit(spec.title, _WIDTH - 2 * _PAD, _SCALE), TEXT)
    max_value = max(max(spec.values), 0.0) or 1.0
    axis_x = _PAD + label_w
    canvas.fill_rect(axis_x - 2, top - 4, 2, row_h * len(spec.values) + 4, GRID)
    for index, (label, value) in enumerate(zip(spec.labels, spec.values)):
        y = top + index * row_h
        text_y = y + (row_h - _TEXT_H) // 2
        canvas.text(_PAD, text_y, _fit(label, label_w - 14, _SCALE), TEXT)
        width = int(round(max(value, 0.0) / max_value * bar_max))
        if value > 0:
            width = max(width, 2)
        canvas.fill_rect(axis_x, y + 6, width, row_h - 12, BAR)
        canvas.text(axis_x + width + 8, text_y, format_number(value), TEXT)
    return canvas.png()


def _render_line(spec: ChartSpec) -> bytes:
    height = 420
    left = _PAD + 112
    right = _PAD
    top = _PAD + _TEXT_H + 26
    bottom = 58
    plot_w = _WIDTH - left - right
    plot_h = height - top - bottom
    canvas = _Canvas(_WIDTH, height)
    canvas.text(_PAD, _PAD, _fit(spec.title, _WIDTH - 2 * _PAD, _SCALE), TEXT)

    low = min(0.0, min(spec.values))
    high = max(spec.values)
    if high == low:
        high = low + 1.0

    def y_of(value: float) -> int:
        return int(round(top + plot_h - (value - low) / (high - low) * plot_h))

    count = len(spec.values)

    def x_of(index: int) -> int:
        if count == 1:
            return left + plot_w // 2
        return int(round(left + index * plot_w / (count - 1)))

    for tick in (low, (low + high) / 2, high):
        y = y_of(tick)
        canvas.fill_rect(left, y, plot_w, 1, GRID)
        label = _fit(format_number(tick), left - _PAD - 10, _SCALE)
        canvas.text(left - 10 - _text_width(label, _SCALE), y - _TEXT_H // 2, label, MUTED)
    canvas.fill_rect(left, top, 2, plot_h + 1, MUTED)
    canvas.fill_rect(left, top + plot_h, plot_w, 2, MUTED)

    points = [(x_of(index), y_of(value)) for index, value in enumerate(spec.values)]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        canvas.line(x0, y0, x1, y1, LINE, thickness=3)
    for x, y in points:
        canvas.fill_rect(x - 4, y - 4, 8, 8, LINE)

    marks = {0, count - 1}
    if count >= 5:
        marks.add(count // 2)
    for index in sorted(marks):
        label = _fit(spec.labels[index], 150, _SCALE)
        width = _text_width(label, _SCALE)
        x = min(max(x_of(index) - width // 2, _PAD), _WIDTH - _PAD - width)
        canvas.text(x, top + plot_h + 14, label, TEXT)
    return canvas.png()


def _render_pie(spec: ChartSpec) -> bytes:
    radius = 140
    cx = _PAD + radius + 6
    cy = _PAD + _TEXT_H + 30 + radius
    height = cy + radius + _PAD
    canvas = _Canvas(_WIDTH, height)
    canvas.text(_PAD, _PAD, _fit(spec.title, _WIDTH - 2 * _PAD, _SCALE), TEXT)

    total = sum(spec.values)
    bounds: list[float] = []
    running = 0.0
    for value in spec.values:
        running += value / total
        bounds.append(running)
    bounds[-1] = 1.0
    colors = [bytes(PALETTE[index % len(PALETTE)]) for index in range(len(spec.values))]
    two_pi = 2 * math.pi
    r2 = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        dy = y - cy
        for x in range(cx - radius, cx + radius + 1):
            dx = x - cx
            if dx * dx + dy * dy > r2:
                continue
            # 0 arriba y en sentido horario.
            fraction = (math.atan2(dx, -dy) % two_pi) / two_pi
            slot = min(bisect.bisect_right(bounds, fraction), len(colors) - 1)
            offset = (y * canvas.width + x) * 3
            canvas.pixels[offset : offset + 3] = colors[slot]

    legend_x = cx + radius + 40
    legend_top = cy - radius + 10
    for index, (label, value) in enumerate(zip(spec.labels, spec.values)):
        y = legend_top + index * 40
        canvas.fill_rect(legend_x, y, 20, 20, PALETTE[index % len(PALETTE)])
        share = f" {value / total * 100:.0f}%"
        room = _WIDTH - _PAD - (legend_x + 32) - _text_width(share, _SCALE)
        canvas.text(legend_x + 32, y + 3, _fit(label, room, _SCALE) + share, TEXT)
    return canvas.png()


def render_chart_png(spec: ChartSpec) -> bytes:
    if not spec.values:
        raise ValueError("no se dibujan gráficos vacíos")
    if spec.kind == "lineas":
        return _render_line(spec)
    if spec.kind == "torta":
        return _render_pie(spec)
    return _render_bars(spec)


# ── enlaces temporales firmados ────────────────────────────────────────────


def sign_chart(chart_id: str, expires: int, key: str) -> str:
    message = f"grafico:{chart_id}:{int(expires)}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def chart_url(base_url: str, chart_id: str, expires: int, key: str) -> str:
    signature = sign_chart(chart_id, expires, key)
    return (
        f"{base_url.rstrip('/')}{CHART_MEDIA_PREFIX}{chart_id}.png"
        f"?exp={int(expires)}&sig={signature}"
    )


def chart_link_valid(
    chart_id: str, expires_raw: str, signature: str, key: str, now: datetime
) -> bool:
    """Firma correcta, id bien formado y enlace sin vencer."""
    if not key or not CHART_ID_RE.fullmatch(chart_id):
        return False
    if not expires_raw.isdigit() or len(expires_raw) > 12:
        return False
    expires = int(expires_raw)
    if expires < now.timestamp():
        return False
    return hmac.compare_digest(sign_chart(chart_id, expires, key), signature)
