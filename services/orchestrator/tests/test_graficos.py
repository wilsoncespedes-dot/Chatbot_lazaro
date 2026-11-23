"""Fase 5: herramienta `graficar` — PNG en el servidor, imagen o enlace firmado.

Criterios de aceptación:
- Barras y líneas; torta solo con 6 categorías o menos.
- PNG dibujado en Python puro (zlib + fuente de mapa de bits), sin dependencias.
- Se envía como `ImageBlock` por el outbox con una frase con la cifra clave.
- Canal sin imágenes → enlace temporal firmado.
- Sin datos → respuesta en texto, nunca un gráfico vacío.
"""
from __future__ import annotations

import json
import struct
import zlib
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from lazaro_contracts import ChannelCapabilities, ImageBlock, LinkBlock, TextBlock

from migrations.testing import database_url_for_tests, migrated_database
from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.adapters.client_data import FakeClientData
from orchestrator.adapters.llm import ScriptedLLM
from orchestrator.charts import (
    BAR,
    BAR_MAX_CATEGORIES,
    LINE,
    PALETTE,
    CHART_SQL_HINT,
    ChartSpec,
    chart_from_result,
    chart_link_valid,
    chart_summary,
    chart_url,
    format_number,
    render_chart_png,
    requested_chart_kind,
)
from orchestrator.config import Settings
from orchestrator.db_query import QueryResult
from orchestrator.domain import ConversationState, ToolContext, execute_tool
from orchestrator.harness import (
    TOOL_MATRIX,
    RouterInvalid,
    build_router_prompt,
    parse_router_answer,
)

from conftest import make_env
from fakes import channel_info, drain_queues

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
KEY = "clave-graficos-" + "g" * 32
BASE = "https://bot.example"
ALLOWLIST = (
    '{"mis_datos.v_mis_casos": ["caso", "estado", "motivo", "creado", "cerrado"]}'
)
CASOS_SQL = (
    "SELECT estado, COUNT(*) AS casos FROM mis_datos.v_mis_casos GROUP BY estado"
)
CASOS = QueryResult(
    columns=["estado", "casos"], rows=[("abierto", 5), ("cerrado", 3)], truncated=False
)


# ── utilidades ─────────────────────────────────────────────────────────────


def _png(data: bytes) -> tuple[int, int, set[bytes]]:
    """Decodifica el PNG (RGB, filtro 0) y devuelve ancho, alto y colores usados."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position = 8
    header = b""
    idat = b""
    tags = []
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        tag = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(">I", data[position + 8 + length : position + 12 + length])
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF
        tags.append(tag)
        if tag == b"IHDR":
            header = body
        elif tag == b"IDAT":
            idat += body
        position += 12 + length
    assert tags[0] == b"IHDR" and tags[-1] == b"IEND"
    width, height, depth, color_type = struct.unpack(">IIBB", header[:10])
    assert (depth, color_type) == (8, 2)
    raw = zlib.decompress(idat)
    stride = width * 3 + 1
    assert len(raw) == stride * height
    colors: set[bytes] = set()
    for y in range(height):
        assert raw[y * stride] == 0
        row = raw[y * stride + 1 : (y + 1) * stride]
        for x in range(0, len(row), 3):
            colors.add(bytes(row[x : x + 3]))
    return width, height, colors


def _image_caps() -> ChannelCapabilities:
    return ChannelCapabilities(
        free_text_allowed=True,
        max_options=3,
        min_list_options=4,
        max_list_options=10,
        supports_links=True,
        requires_template=False,
        supports_images=True,
    )


def _chart_env(**overrides):
    values = {
        "charts_enabled": True,
        "chart_link_signing_key": KEY,
        "client_data_enabled": True,
        "client_data_database_url": "postgresql://bot_lectura:x@db/lazaro",
        "client_data_allowlist": ALLOWLIST,
        "identity_public_base_url": BASE,
        "identity_link_signing_key": "identidad-" + "i" * 32,
    }
    values.update(overrides)
    return make_env(**values)


def _prepare(env, *, user: int = 10, chat: int = 100):
    contact = env.repo.get_or_create_contact(user, chat, NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    profile = env.repo.create_client_credential(
        f"cliente{user}", "hash", NOW - timedelta(days=1), NOW + timedelta(days=30), NOW
    )
    env.repo.add_login_link(
        f"token-{user}", contact.id, "telegram", str(chat), NOW, NOW + timedelta(minutes=15)
    )
    assert env.repo.start_client_session(f"token-{user}", profile.id, f"s-{user}", NOW) == "ok"
    return contact, profile


def _run_chart(env, contact, result: QueryResult, profile, text="grafica mis casos", sql=CASOS_SQL, args=None):
    fake = FakeClientData({profile.id: result} if profile is not None else {})
    env.adapters.client_data = fake
    scripted = ScriptedLLM([json.dumps({"sql": sql})])
    env.adapters.llm = scripted
    outcome = execute_tool(
        "graficar",
        ToolContext(
            contact=contact,
            text=text,
            received_at=NOW,
            update_id=1,
            state=ConversationState.ACTIVE,
            origin="router",
            args=args or {},
        ),
        env.settings,
        env.adapters,
    )
    drain_queues(env.settings, env.adapters)
    return outcome, fake, scripted


def _path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


# ── dibujo puro ────────────────────────────────────────────────────────────


def test_bar_chart_is_a_valid_png_with_bars():
    spec = chart_from_result(CASOS)
    assert spec is not None and spec.kind == "barras"
    width, height, colors = _png(render_chart_png(spec))
    assert width == 720 and height > 100
    assert bytes(BAR) in colors
    assert bytes((0x1B, 0x27, 0x33)) in colors  # texto dibujado con la fuente


def test_dates_default_to_a_sorted_line_chart():
    result = QueryResult(
        columns=["dia", "mensajes"],
        rows=[(date(2026, 1, 3), 7), (date(2026, 1, 1), 2), (date(2026, 1, 2), 4)],
        truncated=False,
    )
    spec = chart_from_result(result)
    assert spec is not None and spec.kind == "lineas"
    assert spec.labels == ("2026-01-01", "2026-01-02", "2026-01-03")
    assert spec.values == (2.0, 4.0, 7.0)
    width, height, colors = _png(render_chart_png(spec))
    assert (width, height) == (720, 420)
    assert bytes(LINE) in colors


def test_pie_only_when_requested_and_with_at_most_six_categories():
    six = QueryResult(
        columns=["canal", "total"],
        rows=[(f"c{i}", i + 1) for i in range(6)],
        truncated=False,
    )
    seven = QueryResult(
        columns=["canal", "total"],
        rows=[(f"c{i}", i + 1) for i in range(7)],
        truncated=False,
    )
    pie = chart_from_result(six, "torta")
    assert pie is not None and pie.kind == "torta"
    _, _, colors = _png(render_chart_png(pie))
    assert {bytes(color) for color in PALETTE} <= colors
    assert chart_from_result(seven, "torta").kind == "barras"
    assert chart_from_result(six).kind == "barras"


def test_many_categories_are_grouped_in_otros():
    result = QueryResult(
        columns=["motivo", "casos"],
        rows=[(f"m{i:02d}", 100 - i) for i in range(15)],
        truncated=False,
    )
    spec = chart_from_result(result)
    assert len(spec.values) == BAR_MAX_CATEGORIES
    assert spec.labels[-1] == "Otros"
    assert spec.values[-1] == sum(100 - i for i in range(BAR_MAX_CATEGORIES - 1, 15))


@pytest.mark.parametrize(
    "result",
    [
        QueryResult(columns=["estado", "casos"], rows=[], truncated=False),
        QueryResult(columns=["estado", "casos"], rows=[("a", 0), ("b", 0)], truncated=False),
        QueryResult(columns=["estado", "motivo"], rows=[("a", "x")], truncated=False),
        QueryResult(columns=["casos"], rows=[(3,)], truncated=False),
        QueryResult(columns=["estado", "casos"], rows=[("a", None)], truncated=False),
    ],
)
def test_nothing_to_draw_returns_none(result):
    """Nunca un gráfico vacío: sin filas, todo en cero o sin columna numérica."""
    assert chart_from_result(result) is None


def test_render_refuses_an_empty_spec():
    with pytest.raises(ValueError):
        render_chart_png(ChartSpec(kind="barras", title="x", labels=(), values=()))


def test_summary_states_the_key_figure():
    bars = chart_summary(chart_from_result(CASOS))
    assert "«abierto»" in bars and "5 de 8" in bars and "62 %" in bars
    line = chart_summary(
        chart_from_result(
            QueryResult(
                columns=["dia", "mensajes"],
                rows=[(date(2026, 1, 1), 2), (date(2026, 1, 2), 9), (date(2026, 1, 3), 7)],
                truncated=False,
            )
        )
    )
    assert "último valor es 7 (2026-01-03)" in line
    assert "máximo fue 9 (2026-01-02)" in line


def test_number_format_and_requested_kind():
    assert format_number(1234) == "1.234"
    assert format_number(1234.5) == "1.234,5"
    assert requested_chart_kind("grafícalo en torta") == "torta"
    assert requested_chart_kind("muéstrame la evolución") == "lineas"
    assert requested_chart_kind("en barras por favor") == "barras"
    assert requested_chart_kind("grafica mis casos") is None
    assert requested_chart_kind("en torta", {"tipo": "lineas"}) == "lineas"


def test_signed_link_rejects_tampering_expiry_and_other_keys():
    chart_id = "a" * 32
    expires = int((NOW + timedelta(hours=1)).timestamp())
    query = parse_qs(urlsplit(chart_url(BASE, chart_id, expires, KEY)).query)
    sig = query["sig"][0]
    assert query["exp"] == [str(expires)]
    assert chart_link_valid(chart_id, str(expires), sig, KEY, NOW)
    assert not chart_link_valid(chart_id, str(expires), "0" * 64, KEY, NOW)
    assert not chart_link_valid(chart_id, str(expires + 1), sig, KEY, NOW)
    assert not chart_link_valid(chart_id, str(expires), sig, "otra" + KEY, NOW)
    assert not chart_link_valid(chart_id, str(expires), sig, KEY, NOW + timedelta(hours=2))
    assert not chart_link_valid("../etc", str(expires), sig, KEY, NOW)
    assert not chart_link_valid(chart_id, str(expires), sig, "", NOW)


# ── matriz, router y configuración ─────────────────────────────────────────


def test_graficar_is_only_allowed_in_active():
    for state, tools in TOOL_MATRIX.items():
        assert ("graficar" in tools) is (state == ConversationState.ACTIVE)


def test_router_accepts_only_the_chart_type_as_argument():
    assert parse_router_answer('{"tool": "graficar", "args": {}}').tool == "graficar"
    decision = parse_router_answer('{"tool": "graficar", "args": {"tipo": "torta"}}')
    assert dict(decision.args) == {"tipo": "torta"}
    for args in ('{"tipo": "3d"}', '{"sql": "DROP TABLE x"}', '{"tipo": "torta", "x": 1}'):
        with pytest.raises(RouterInvalid):
            parse_router_answer(f'{{"tool": "graficar", "args": {args}}}')


def test_router_prompt_hides_graficar_when_charts_are_off():
    system, _ = build_router_prompt(ConversationState.ACTIVE, "hola", charts_enabled=False)
    assert "graficar" not in system
    system, _ = build_router_prompt(ConversationState.ACTIVE, "hola", charts_enabled=True)
    assert "- graficar:" in system


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"client_data_enabled": False}, "CLIENT_DATA_ENABLED"),
        ({"identity_public_base_url": "http://bot.example"}, "IDENTITY_PUBLIC_BASE_URL"),
        ({"chart_link_signing_key": "corta"}, "CHART_LINK_SIGNING_KEY"),
        ({"chart_link_signing_key": "identidad-" + "i" * 32}, "distinta"),
    ],
)
def test_charts_config_is_validated(overrides, message):
    values = {
        "charts_enabled": True,
        "chart_link_signing_key": KEY,
        "client_data_enabled": True,
        "client_data_database_url": "postgresql://bot_lectura:x@db/lazaro",
        "client_data_allowlist": ALLOWLIST,
        "identity_public_base_url": BASE,
        "identity_link_signing_key": "identidad-" + "i" * 32,
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        Settings(**values)


def test_charts_are_off_by_default():
    settings = Settings()
    assert settings.charts_enabled is False
    assert settings.chart_link_ttl_seconds == 3600


# ── flujo completo ─────────────────────────────────────────────────────────


def test_channel_with_images_gets_image_block_through_the_outbox():
    env = _chart_env()
    env.adapters.channels = FakeChannelDirectory(
        [channel_info("telegram", capabilities=_image_caps())]
    )
    contact, profile = _prepare(env)

    outcome, fake, scripted = _run_chart(env, contact, CASOS, profile)

    assert outcome == "ok"
    assert fake.calls[0][1] == profile.id
    assert CHART_SQL_HINT in scripted.calls[0][0]
    _, _, blocks = env.gateway.blocks_sent[-1]
    image = next(block for block in blocks if isinstance(block, ImageBlock))
    text = next(block for block in blocks if isinstance(block, TextBlock))
    assert "«abierto» es el mayor con 5 de 8" in text.text
    assert image.url.startswith(f"{BASE}/media/graficos/")
    assert not any(isinstance(block, LinkBlock) for block in blocks)
    # Pasó por el outbox y quedó en el historial con la frase.
    assert env.repo.outbox == {} or all(
        row.get("status") != "pending" for row in env.repo.outbox.values()
    )
    assert any(message.text == text.text for message in env.repo.messages)

    response = env.client.get(_path_and_query(image.url))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    width, _, colors = _png(response.content)
    assert width == 720 and bytes(BAR) in colors
    detail = env.repo.tool_calls[-1].detail
    assert "kind=barras" in detail and "delivery=image" in detail


def test_channel_without_images_gets_a_signed_temporary_link():
    env = _chart_env()  # Telegram de prueba no informa supports_images
    contact, profile = _prepare(env)

    outcome, _, _ = _run_chart(env, contact, CASOS, profile)

    assert outcome == "ok"
    _, _, blocks = env.gateway.blocks_sent[-1]
    assert not any(isinstance(block, ImageBlock) for block in blocks)
    link = next(block for block in blocks if isinstance(block, LinkBlock))
    assert link.text == env.settings.chart_link_label
    assert "sig=" in link.url and "exp=" in link.url
    assert env.client.get(_path_and_query(link.url)).status_code == 200
    assert "delivery=link" in env.repo.tool_calls[-1].detail


def test_no_data_answers_in_text_and_stores_no_chart():
    env = _chart_env()
    contact, profile = _prepare(env)
    empty = QueryResult(columns=["estado", "casos"], rows=[], truncated=False)

    outcome, _, _ = _run_chart(env, contact, empty, profile)

    assert outcome == "no_data"
    assert env.repo.chart_images == {}
    assert env.gateway.sent[-1] == (100, env.settings.chart_no_data_reply)
    for _, _, blocks in env.gateway.blocks_sent:
        assert not any(isinstance(block, (ImageBlock, LinkBlock)) for block in blocks)


def test_single_figure_is_answered_in_text():
    env = _chart_env()
    contact, profile = _prepare(env)
    single = QueryResult(columns=["casos"], rows=[(3,)], truncated=False)

    outcome, _, _ = _run_chart(
        env, contact, single, profile,
        sql="SELECT COUNT(*) FROM mis_datos.v_mis_casos",
    )

    assert outcome == "text"
    assert env.repo.chart_images == {}
    assert env.gateway.sent[-1] == (100, "casos\n3")


def test_chart_requires_a_session_and_the_flag():
    env = _chart_env()
    contact = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    outcome, fake, _ = _run_chart(env, contact, CASOS, None)
    assert outcome == "no_session" and fake.calls == []

    env = make_env()  # gráficos apagados
    contact, profile = _prepare(env)
    outcome, fake, _ = _run_chart(env, contact, CASOS, profile)
    assert outcome == "disabled" and fake.calls == []
    assert env.gateway.sent[-1] == (100, env.settings.chart_disabled_reply)


def test_media_route_rejects_bad_signature_expiry_and_disabled_charts():
    env = _chart_env()
    contact, profile = _prepare(env)
    _run_chart(env, contact, CASOS, profile)
    link = next(
        block for block in env.gateway.blocks_sent[-1][2] if isinstance(block, LinkBlock)
    )
    good = _path_and_query(link.url)
    assert env.client.get(good).status_code == 200

    tampered = good[:-4] + ("0000" if not good.endswith("0000") else "1111")
    assert env.client.get(tampered).status_code == 404
    assert env.client.get(good.split("?")[0]).status_code == 404

    later = NOW + timedelta(seconds=env.settings.chart_link_ttl_seconds + 1)
    env.adapters.clock = lambda: later
    assert env.client.get(good).status_code == 404

    env.adapters.clock = lambda: NOW
    env.settings.charts_enabled = False
    assert env.client.get(good).status_code == 404


def test_keyword_routes_to_graficar_without_the_router():
    env = _chart_env()
    contact, profile = _prepare(env)
    env.adapters.client_data = FakeClientData({profile.id: CASOS})
    env.adapters.llm = ScriptedLLM([json.dumps({"sql": CASOS_SQL})])

    env.post(text="grafícame mis casos por estado")

    call = env.repo.tool_calls[-1]
    assert (call.tool, call.origin, call.result) == ("graficar", "keyword", "ok")
    assert len(env.repo.chart_images) == 1


def test_keyword_is_ignored_when_charts_are_off():
    env = make_env()
    contact = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    env.post(text="grafícame mis casos por estado")

    assert all(call.tool != "graficar" for call in env.repo.tool_calls)


def test_expired_charts_are_purged_when_a_new_one_is_saved():
    env = _chart_env()
    repo = env.repo
    contact = repo.get_or_create_contact(10, 100, NOW)
    repo.add_chart_image("a" * 32, contact.id, b"png-a", NOW, NOW + timedelta(minutes=1))
    later = NOW + timedelta(minutes=5)
    repo.add_chart_image("b" * 32, contact.id, b"png-b", later, later + timedelta(minutes=1))
    assert set(repo.chart_images) == {"b" * 32}
    assert repo.get_chart_image("b" * 32, later) == b"png-b"
    assert repo.get_chart_image("b" * 32, later + timedelta(minutes=2)) is None


# ── Postgres real (TEST_DATABASE_URL) ──────────────────────────────────────


@pytest.mark.skipif(
    not database_url_for_tests(),
    reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
)
def test_postgres_chart_images_expire_and_follow_the_contact():
    from orchestrator.adapters.repository import PostgresRepository

    with migrated_database() as url:
        repo = PostgresRepository(url)
        ana = repo.get_or_create_channel_contact("whatsapp", "57300", "57300", NOW)
        png = render_chart_png(chart_from_result(CASOS))
        repo.add_chart_image("a" * 32, ana.id, png, NOW, NOW + timedelta(minutes=1))
        assert repo.get_chart_image("a" * 32, NOW) == png
        assert repo.get_chart_image("a" * 32, NOW + timedelta(minutes=2)) is None

        later = NOW + timedelta(minutes=5)
        repo.add_chart_image("b" * 32, ana.id, b"png-b", later, later + timedelta(hours=1))
        assert repo.get_chart_image("a" * 32, NOW) is None  # purgado al guardar otro

        repo.delete_contact_content("whatsapp", "57300")
        assert repo.get_chart_image("b" * 32, later) is None
