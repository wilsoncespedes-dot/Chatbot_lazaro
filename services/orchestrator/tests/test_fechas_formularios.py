"""Pruebas de fechas legibles y formularios simétricos del panel (#61)."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytest

from orchestrator import admin
from orchestrator.panel_live_js import PANEL_LIVE_JS


@pytest.fixture(autouse=True)
def _colombia():
    admin.set_display_utc_offset(-300)
    yield
    admin.set_display_utc_offset(-300)


# --- R1–R4: fechas -----------------------------------------------------------------


def test_datetime_is_shown_in_business_zone_with_12h_clock():
    """R1: "17 nov 2026, 2:33 p. m." en la zona del negocio, sin segundos."""
    at = datetime(2026, 11, 17, 19, 33, 31, 650964, tzinfo=timezone.utc)
    assert admin.human_datetime(at) == "17 nov 2026, 2:33 p. m."
    morning = datetime(2026, 1, 2, 5, 4, tzinfo=timezone.utc)
    assert admin.human_datetime(morning) == "2 ene 2026, 12:04 a. m."


def test_naive_datetime_is_utc_and_date_has_no_time():
    """R1: sin zona se asume UTC; un `date` se muestra solo como fecha."""
    assert admin.human_datetime(datetime(2026, 3, 9, 15, 0)) == "9 mar 2026, 10:00 a. m."
    assert admin.human_datetime(date(2026, 5, 31)) == "31 may 2026"
    assert admin.human_datetime(None) == "—"


def test_time_html_keeps_exact_iso_and_offset_hint():
    """R2: `<time datetime>` conserva el valor exacto y el título indica la zona."""
    at = datetime(2026, 11, 17, 19, 33, 31, tzinfo=timezone.utc)
    html = admin.time_html(at)
    assert html == (
        '<time datetime="2026-11-17T19:33:31+00:00" title="Hora local (UTC−5)">'
        "17 nov 2026, 2:33 p. m.</time>"
    )
    assert admin.time_html(None) == "—"


def test_offset_comes_from_settings(env_factory):
    """R3: la zona sale de BUSINESS_HOURS_UTC_OFFSET_MINUTES al crear la app."""
    env_factory(business_hours_utc_offset_minutes=60)
    at = datetime(2026, 11, 17, 19, 33, tzinfo=timezone.utc)
    assert admin.human_datetime(at) == "17 nov 2026, 8:33 p. m."
    assert 'title="Hora local (UTC+1)"' in admin.time_html(at)


def test_events_page_shows_readable_dates(env_factory, panel):
    """R4: Eventos recientes ya no muestra ISO con microsegundos en el texto."""
    env = env_factory()
    panel.login_admin(env)
    html = env.client.get("/admin/events").text
    visible = re.sub(r"<[^>]+>", "", html)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", visible)


def test_live_script_uses_same_readable_format():
    """R4: el panel en vivo reescribe las horas con el mismo formato."""
    assert '"ene", "feb", "mar"' in PANEL_LIVE_JS
    assert '"a. m." : "p. m."' in PANEL_LIVE_JS
    assert 'raw.indexOf("T") < 0' in PANEL_LIVE_JS


# --- R5, R6: formularios y acciones ----------------------------------------------


@pytest.mark.parametrize(
    "path, action",
    [
        ("/admin/plantillas", "/admin/plantillas"),
        ("/admin/respuestas", "/admin/respuestas"),
        ("/admin/categories", "/admin/categories"),
        ("/admin/etiquetas", "/admin/etiquetas"),
        ("/admin/clientes", "/admin/clientes"),
    ],
)
def test_create_forms_use_aligned_grid(env_factory, panel, path, action):
    """R5: los formularios de alta usan la cuadrícula alineada."""
    env = env_factory()
    panel.login_admin(env)
    html = env.client.get(path).text
    assert f'action="{action}" class="card create-form"' in html


def test_create_form_css_aligns_fields_and_widens_textareas():
    """R5: campos arriba alineados, área de texto a todo el ancho, botón debajo."""
    css = admin.ADMIN_CSS
    assert "form.create-form { display: grid;" in css
    assert "align-items: start;" in css
    assert ".create-form label:has(textarea)" in css
    assert ".create-form > button { grid-column: 1 / -1; justify-self: start; }" in css


def test_client_actions_are_equal_width(env_factory, panel):
    """R6: Renovar, Revocar y Cerrar sesión en una fila con el mismo ancho."""
    env = env_factory()
    panel.login_admin(env)
    env.client.post(
        "/admin/clientes",
        data={"csrf_token": panel.CSRF, "username": "cliente9", "password": "clave-segura-123"},
    )
    html = env.client.get("/admin/clientes").text
    cell = re.search(r'<div class="row-actions">(.*?)</div>', html, re.S)
    assert cell is not None
    assert [b for b in re.findall(r">([^<>]+)</button>", cell.group(1))] == [
        "Renovar", "Revocar", "Cerrar sesión",
    ]
    assert ".row-actions { display: grid; grid-template-columns: repeat(3, 6.75rem);" in admin.ADMIN_CSS
    assert ".row-actions button { width: 100%;" in admin.ADMIN_CSS


def test_validity_dates_show_local_date_only():
    """R1: las fechas de vigencia de Clientes se muestran sin hora y en fecha local."""
    late = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    assert admin.human_datetime(late, with_time=False) == "1 ene 2026"
    assert ">1 ene 2026</time>" in admin.time_html(late, with_time=False)
