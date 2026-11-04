"""Funciones puras de administración (#42)."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from orchestrator.administration import (
    ALLOWED_TRANSITIONS,
    BusinessHours,
    SettingsFormInvalid,
    effective_templates,
    first_response_summary,
    format_local_date,
    median_minutes,
    render_expiry_notice,
    resolve_operational_settings,
    validate_settings_form,
    within_business_hours,
)
from orchestrator.config import Settings

NOW = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)


def _spec(**overrides):
    return SimpleNamespace(
        key="business_hours.enabled",
        kind="bool",
        minimum=None,
        maximum=None,
        default_attr="business_hours_enabled",
    )


def _hours(**changes) -> BusinessHours:
    values = {
        "enabled": True,
        "start": time(6, 0),
        "end": time(21, 0),
        "days": frozenset({1, 2, 3, 4, 5, 6, 7}),
        "utc_offset_minutes": -300,
    }
    values.update(changes)
    return BusinessHours(**values)


def test_valid_override_wins_and_invalid_falls_back_with_warning(caplog):
    """R39: un valor válido gana; uno inválido usa default y avisa sin el valor."""
    settings = Settings()
    with caplog.at_level(logging.WARNING):
        resolved = resolve_operational_settings(
            settings,
            {"identity.validity_days": "10", "business_hours.enabled": "true"},
        )
    assert resolved.identity.validity_days == 10
    assert resolved.hours.enabled is True

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        resolved = resolve_operational_settings(
            settings, {"identity.validity_days": "999"}
        )
    assert resolved.identity.validity_days == settings.credential_validity_days
    assert "identity.validity_days" in caplog.text
    assert "999" not in caplog.text


def test_validate_form_saves_valid_values_and_deletes_empty():
    """R37, R74: los valores válidos se guardan y los vacíos se borran."""
    settings = Settings()
    form = {
        "identity.validity_days": "10",
        "business_hours.enabled": "true",
        "business_hours.days": "1,2,3",
    }
    upserts, deletes = validate_settings_form(form, settings, {})
    assert upserts["identity.validity_days"] == "10"
    assert upserts["business_hours.enabled"] == "true"
    assert upserts["business_hours.days"] == "1,2,3"
    assert "business_hours.end" in deletes


@pytest.mark.parametrize(
    "form",
    [
        {"identity.validity_days": "0"},
        {"identity.validity_days": "abc"},
        {"business_hours.enabled": "sí"},
        {"business_hours.start": "6:00"},
        {"business_hours.end": "24:00"},
        {"business_hours.days": "0,1"},
        {"business_hours.days": "1,1"},
        {"business_hours.utc_offset_minutes": "999"},
        {"suppression.due_soon_business_days": "15"},
    ],
)
def test_validate_form_rejects_invalid_values_without_partial_save(form):
    """R38: cualquier valor fuera de rango invalida el formulario completo."""
    with pytest.raises(SettingsFormInvalid):
        validate_settings_form(form, Settings(), {})


def test_validate_form_rejects_equal_start_and_end():
    """R38: start y end iguales no son un horario válido."""
    with pytest.raises(SettingsFormInvalid):
        validate_settings_form(
            {"business_hours.start": "06:00", "business_hours.end": "06:00"},
            Settings(),
            {},
        )


def test_within_business_hours_boundaries_days_offset_and_midnight():
    """R41: bordes start/end, días, offset y rango que cruza medianoche."""
    hours = _hours(start=time(6, 0), end=time(21, 0), utc_offset_minutes=0)
    assert within_business_hours(datetime(2026, 1, 2, 11, 0, tzinfo=timezone.utc), hours)
    assert not within_business_hours(
        datetime(2026, 1, 2, 2, 0, tzinfo=timezone.utc), hours
    )
    # start es inclusivo y end exclusivo.
    assert within_business_hours(
        datetime(2026, 1, 2, 6, 0, tzinfo=timezone.utc),
        _hours(start=time(6, 0), end=time(21, 0), utc_offset_minutes=0),
    )
    assert not within_business_hours(
        datetime(2026, 1, 2, 21, 0, tzinfo=timezone.utc),
        _hours(start=time(6, 0), end=time(21, 0), utc_offset_minutes=0),
    )
    # 2026-01-03 es sábado.
    assert not within_business_hours(
        datetime(2026, 1, 3, 11, 0, tzinfo=timezone.utc),
        _hours(days=frozenset({1, 2, 3, 4, 5}), utc_offset_minutes=0),
    )
    crossing = _hours(
        start=time(22, 0), end=time(6, 0), utc_offset_minutes=-300
    )
    assert within_business_hours(
        datetime(2026, 1, 2, 3, 0, tzinfo=timezone.utc), crossing
    )
    assert within_business_hours(
        datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc), crossing
    )
    assert not within_business_hours(
        datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc), crossing
    )
    assert within_business_hours(
        datetime(2026, 1, 2, 18, 0, tzinfo=timezone.utc),
        _hours(start=time(6, 0), end=time(21, 0), utc_offset_minutes=120),
    )


def test_render_expiry_notice_does_not_interpret_template_braces():
    """R50: solo se sustituyen {dias} y {fecha}; otros formatos no se interpretan."""
    rendered = render_expiry_notice(
        "Vence en {dias} días, {fecha}. {otro}", 3, "15/01/2026"
    )
    assert rendered == "Vence en 3 días, 15/01/2026. {otro}"


def test_format_local_date_uses_offset():
    """R45: la fecha local se calcula con el offset configurado."""
    at = datetime(2026, 1, 2, 2, 0, tzinfo=timezone.utc)
    assert format_local_date(at, -300) == "01/01/2026"


def test_template_transitions_are_the_approved_set():
    """R29: solo estas transiciones son válidas."""
    assert ("draft", "pending") in ALLOWED_TRANSITIONS
    assert ("pending", "approved") in ALLOWED_TRANSITIONS
    assert ("approved", "paused") in ALLOWED_TRANSITIONS
    assert ("paused", "approved") in ALLOWED_TRANSITIONS
    assert ("rejected", "draft") in ALLOWED_TRANSITIONS
    assert ("approved", "pending") not in ALLOWED_TRANSITIONS


def test_effective_templates_registered_then_approved_only_and_expiry_no_fallback():
    """R32, R33: con registro solo valen las aprobadas; expiry no tiene respaldo."""
    registered = [
        SimpleNamespace(name="b", purpose="advisor_reply", status="draft"),
        SimpleNamespace(name="a", purpose="advisor_reply", status="approved"),
        SimpleNamespace(name="c", purpose="suppression_result", status="approved"),
    ]
    assert effective_templates("advisor_reply", registered, ("env",)) == ("a",)
    assert effective_templates("suppression_result", registered, ("env",)) == ("c",)
    assert effective_templates("expiry_notice", registered, ()) == ()
    assert effective_templates("advisor_reply", [], ("env",)) == ("env",)


def test_median_and_first_response_summary():
    """R63: promedio, mediana y casos sin respuesta."""
    assert median_minutes([10, 20, 30]) == 20
    assert median_minutes([10, 20]) == 15
    assert median_minutes([]) is None
    summary = first_response_summary(
        [
            (NOW, NOW + timedelta(minutes=10)),
            (NOW, NOW + timedelta(minutes=30)),
            (NOW, None),
        ]
    )
    assert (summary.cases, summary.answered, summary.unanswered) == (3, 2, 1)
    assert summary.avg_minutes == 20
    assert summary.median_minutes == 20
