"""Gráficos SVG del dashboard (#75): funciones puras."""
from __future__ import annotations

from orchestrator.dashboard import (
    CASE_STATUS_COLORS,
    DASHBOARD_MAX_CHANNELS,
    MEDIAN_COLOR,
    P90_COLOR,
    BarDatum,
    Cell,
    group_top,
    render_bar_chart,
    render_chart_block,
    render_data_table,
)

COLOR = "#1D4ED8"


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]

    def linear(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(value) for value in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_on_white(hex_color: str) -> float:
    return 1.05 / (_luminance(hex_color) + 0.05)


def test_bar_chart_escapes_labels_in_svg_title_and_desc():
    """R31: los nombres de canal se escapan en SVG, título y descripción."""
    data = [BarDatum("<b>Telegram & Cía</b>", 5, COLOR)]

    svg = render_bar_chart("canales", "<Título>", "", data)

    assert "&lt;b&gt;Telegram &amp; Cía&lt;/b&gt;" in svg
    assert "<b>Telegram" not in svg
    assert "<Título>" not in svg
    assert "&lt;Título&gt;" in svg


def test_data_table_escapes_caption_and_cells():
    """R31: la tabla escapa caption, encabezados y valores."""
    table = render_data_table(
        "<caption>", ["<col>", "Total"], [["<nombre>", "<script>"]]
    )

    assert "&lt;caption&gt;" in table
    assert "&lt;col&gt;" in table
    assert "&lt;nombre&gt;" in table
    assert "<script>" not in table


def test_empty_and_zero_data_render_sin_datos_without_division_by_zero():
    """R32: sin datos o todo en cero -> SVG válido y tabla con «Sin datos»."""
    for data in ([], [BarDatum("Canal", 0, COLOR)]):
        svg = render_bar_chart("vacio", "Mensajes", "", data)
        block = render_chart_block(
            "vacio", "Mensajes", "", data, headers=("Canal", "Mensajes")
        )

        assert 'role="img"' in svg
        assert "Sin datos" in svg
        assert "Sin datos" in block
        assert "<table><caption>Mensajes</caption>" in block


def test_many_channels_group_bars_but_table_can_list_all():
    """R13: el gráfico agrupa «Otros»; la tabla de datos conserva todos los canales."""
    data = [BarDatum(f"canal-{index}", index + 1, COLOR) for index in range(20)]

    grouped = group_top(data, DASHBOARD_MAX_CHANNELS)

    assert len(grouped) == DASHBOARD_MAX_CHANNELS
    assert grouped[-1].label == "Otros"
    assert grouped[-1].value == sum(range(1, 10))
    block = render_chart_block(
        "muchos",
        "Mensajes por canal",
        "",
        grouped,
        headers=("Canal", "Mensajes"),
        rows=[(datum.label, int(datum.value)) for datum in data],
    )
    for datum in data:
        assert datum.label in block


def test_chart_has_accessibility_attributes():
    """R29: cada gráfico tiene role, título, descripción y aria-labelledby."""
    svg = render_bar_chart(
        "accesible",
        "Título visible",
        "Resumen de los datos",
        [BarDatum("Canal", 3, COLOR)],
    )

    assert 'role="img"' in svg
    assert 'aria-labelledby="accesible-title accesible-desc"' in svg
    assert '<title id="accesible-title">Título visible</title>' in svg
    assert '<desc id="accesible-desc">Resumen de los datos</desc>' in svg


def test_chart_block_has_visible_heading_and_data_table():
    """R29, R30: título visible, SVG y tabla con caption y encabezados."""
    block = render_chart_block(
        "bloque",
        "Conversaciones por estado",
        "",
        [BarDatum("Abierta", 2, COLOR)],
        headers=("Estado", "Casos"),
        rows=[("Abierta", 2)],
    )

    assert "<h3>Conversaciones por estado</h3>" in block
    assert '<th scope="col">Estado</th>' in block
    assert '<th scope="col">Casos</th>' in block
    assert '<th scope="row">Abierta</th>' in block


def test_data_table_accepts_prebuilt_channel_label_html():
    """R10: la tabla puede incluir la etiqueta de canal de #67 ya construida."""
    table = render_data_table(
        "Canales", ["Canal", "Mensajes"], [[Cell("<svg>etiqueta</svg>"), 4]]
    )

    assert "<svg>etiqueta</svg>" in table
    assert "&lt;svg&gt;" not in table


def test_svg_has_no_style_script_or_external_resources():
    """R27: SVG sin estilos, scripts, imágenes externas ni atributos style."""
    svg = render_bar_chart(
        "limpio",
        "Mensajes",
        "",
        [BarDatum("Canal", 1, COLOR)],
    )

    for forbidden in ("style=", "<style", "<script", "<image", "href="):
        assert forbidden not in svg


def test_bars_scale_proportionally_to_max_value():
    """R33: la barra mayor ocupa el ancho máximo y la mitad la mitad."""
    svg = render_bar_chart(
        "escala",
        "Mensajes",
        "",
        [BarDatum("Grande", 10, COLOR), BarDatum("Pequeña", 5, COLOR)],
    )

    assert 'width="330.0"' in svg
    assert 'width="165.0"' in svg


def test_state_and_time_colors_have_enough_contrast():
    """R33: colores fijos de estados y tiempos con contraste >= 4.5."""
    colors = list(CASE_STATUS_COLORS.values()) + [MEDIAN_COLOR, P90_COLOR]
    for color in colors:
        assert _contrast_on_white(color) >= 4.5, color
