"""Métricas del dashboard SVG (#75)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fakes import channel_info

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.administration import (
    first_response_summary,
    median_minutes,
    percentile_minutes,
)
from orchestrator.channel_label import UNKNOWN_NAME
from orchestrator.dashboard import advisor_response_minutes, response_summary
from orchestrator.domain import channel_dashboard

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _set_channels(env, *infos) -> None:
    env.adapters.channels = FakeChannelDirectory(infos)


def _telegram(**changes):
    return channel_info("telegram", name="Telegram", icon="telegram", **changes)


def _simulado(**changes):
    return channel_info(
        "simulado",
        name="Simulado",
        adapter_type="simulado",
        icon="chat",
        **changes,
    )


def _contact(env, channel: str, user: str, now):
    return env.repo.get_or_create_channel_contact(
        channel, user, f"{user}00", now - timedelta(days=1)
    )


def _dashboard(env, profile, include_simulated: bool = True):
    return channel_dashboard(
        profile, 7, include_simulated, env.settings, env.adapters
    )


def _labels(data):
    return {label.name: count for label, count in data.message_labels}


def test_percentile_minutes_uses_nearest_rank():
    """R17: percentil 90 por rango más cercano y `None` sin datos."""
    assert percentile_minutes([], 90) is None
    assert percentile_minutes([3], 90) == 3
    values = [float(value) for value in range(1, 11)]
    assert percentile_minutes(values, 90) == 9
    assert percentile_minutes(values, 50) == 5


def test_first_response_summary_adds_p90_without_changing_columns():
    """R16, R17, R25: p90 nuevo; promedio y mediana conservan su valor."""
    start = START
    rows = [
        (start, None),
        (start, start + timedelta(minutes=10)),
        (start, start + timedelta(minutes=20)),
    ]

    summary = first_response_summary(
        [(created, reply) for created, reply in rows]
    )

    assert summary.cases == 3
    assert summary.answered == 2
    assert summary.unanswered == 1
    assert summary.avg_minutes == 15
    assert summary.median_minutes == 15
    assert summary.p90_minutes == 20


def test_advisor_response_pairs_each_client_message_with_next_advisor():
    """R18: minutos entre mensaje de cliente y el siguiente de asesor."""
    start = START
    rows = [
        ("c1", "user", start),
        ("c1", "bot", start + timedelta(minutes=1)),
        ("c1", "advisor", start + timedelta(minutes=5)),
        ("c1", "user", start + timedelta(minutes=10)),
        ("c1", "advisor", start + timedelta(minutes=18)),
    ]

    assert advisor_response_minutes(rows) == [5, 8]


def test_advisor_response_ignores_missing_or_earlier_replies():
    """R19: sin asesor posterior o con asesor anterior no se cuenta."""
    start = START
    rows = [
        ("c1", "advisor", start),
        ("c1", "user", start + timedelta(minutes=5)),
        ("c2", "user", start),
        ("c2", "user", start + timedelta(minutes=10)),
    ]

    assert advisor_response_minutes(rows) == []


def test_response_summary_empty_and_with_values():
    """R20, R25: sin datos devuelve None; reutiliza mediana y p90."""
    empty = response_summary([])
    assert empty.count == 0
    assert empty.median is None and empty.p90 is None

    summary = response_summary([2, 4, 6, 8, 10])
    assert summary.count == 5
    assert summary.median == median_minutes([2, 4, 6, 8, 10])
    assert summary.p90 == 10


def test_response_rows_show_dash_when_there_are_no_times(env_factory, panel):
    """R20: sin datos, mediana y p90 se muestran como «—»."""
    env = env_factory()
    _set_channels(env, _telegram())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    contact = _contact(env, "telegram", "20", now)
    env.repo.add_message(contact.id, "user", "hola", now - timedelta(hours=1))

    data = _dashboard(env, profile)
    rows = {row[0]: (row[1], row[2], row[3]) for row in data.response_rows}

    assert rows["Primera respuesta"] == (0, "—", "—")
    assert rows["Respuesta de asesor"] == (0, "—", "—")
    assert data.response_times == ()


def test_response_times_chart_has_median_and_p90_for_both_measures(
    env_factory, panel
):
    """R21: barras agrupadas de mediana y p90 por medida."""
    env = env_factory()
    _set_channels(env, _telegram())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    contact = _contact(env, "telegram", "21", now)
    env.repo.link_case("case-1", contact.id, now - timedelta(hours=3))
    env.repo.add_message(contact.id, "user", "hola", now - timedelta(hours=2))
    env.repo.add_message(
        contact.id, "advisor", "respuesta", now - timedelta(hours=1)
    )

    data = _dashboard(env, profile)
    labels = [datum.label for datum in data.response_times]

    assert labels == [
        "Primera respuesta · mediana",
        "Primera respuesta · p90",
        "Respuesta de asesor · mediana",
        "Respuesta de asesor · p90",
    ]
    values = {datum.label: datum.value for datum in data.response_times}
    assert values["Primera respuesta · mediana"] == 120
    assert values["Primera respuesta · p90"] == 120
    assert values["Respuesta de asesor · mediana"] == 60
    assert values["Respuesta de asesor · p90"] == 60


def test_messages_per_channel_use_existing_label_and_roles(env_factory, panel):
    """R9, R10: cuenta user/bot/advisor por canal y usa la etiqueta de #67."""
    env = env_factory()
    _set_channels(env, _telegram(), _simulado())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    telegram = _contact(env, "telegram", "1", now)
    simulado = _contact(env, "simulado", "2", now)
    env.repo.add_message(telegram.id, "user", "hola", now - timedelta(hours=3))
    env.repo.add_message(telegram.id, "bot", "respuesta", now - timedelta(hours=2))
    env.repo.add_message(telegram.id, "system", "ignorado", now - timedelta(hours=2))
    env.repo.add_message(simulado.id, "advisor", "respuesta", now - timedelta(hours=1))

    data = _dashboard(env, profile)
    labels = _labels(data)

    assert labels["Telegram"] == 2
    assert labels["Simulado [SIMULADO]"] == 1
    telegram_label = next(
        label for label, _ in data.message_labels if label.name == "Telegram"
    )
    assert telegram_label.color == "#1B6FA8"


def test_unknown_channel_is_grouped_with_unknown_label(env_factory, panel):
    """R11: un canal que no está en el directorio usa «Canal desconocido»."""
    env = env_factory()
    _set_channels(env, _telegram())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    unknown_one = _contact(env, "viejo-a", "3", now)
    unknown_two = _contact(env, "viejo-b", "4", now)
    env.repo.add_message(unknown_one.id, "user", "uno", now - timedelta(hours=2))
    env.repo.add_message(unknown_two.id, "user", "dos", now - timedelta(hours=1))

    data = _dashboard(env, profile)

    assert _labels(data) == {UNKNOWN_NAME: 2}


def test_directory_unavailable_labels_everything_unknown_and_no_simulated(
    env_factory, panel
):
    """R12: sin directorio todo es «Canal desconocido» y nada se marca SIMULADO."""
    env = env_factory()
    env.adapters.channels = FakeChannelDirectory(fail=True)
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    contact = _contact(env, "telegram", "5", now)
    env.repo.add_message(contact.id, "user", "hola", now - timedelta(hours=1))

    data = _dashboard(env, profile)

    assert _labels(data) == {UNKNOWN_NAME: 1}
    assert all("[SIMULADO]" not in label.name for label, _ in data.message_labels)


def test_simulated_channel_can_be_excluded_from_messages_cases_and_times(
    env_factory, panel
):
    """R23: excluir simulados quita mensajes, casos y tiempos; R22 los marca."""
    env = env_factory()
    _set_channels(env, _telegram(), _simulado())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    telegram = _contact(env, "telegram", "6", now)
    simulado = _contact(env, "simulado", "7", now)
    env.repo.link_case("case-tg", telegram.id, now - timedelta(hours=3))
    env.repo.link_case("case-sim", simulado.id, now - timedelta(hours=3))
    env.repo.add_message(telegram.id, "user", "hola", now - timedelta(hours=2))
    env.repo.add_message(
        telegram.id, "advisor", "respuesta", now - timedelta(hours=1)
    )
    env.repo.add_message(simulado.id, "user", "simulado", now - timedelta(hours=2))
    env.repo.add_message(
        simulado.id, "advisor", "respuesta", now - timedelta(hours=1)
    )
    env.handover.case_list = [
        panel.case_item("case-tg", status="open", created_at=now - timedelta(hours=3)),
        panel.case_item(
            "case-sim", status="open", created_at=now - timedelta(hours=3)
        ),
    ]

    included = _dashboard(env, profile, include_simulated=True)
    excluded = _dashboard(env, profile, include_simulated=False)

    assert _labels(included)["Simulado [SIMULADO]"] == 2
    assert set(_labels(excluded)) == {"Telegram"}
    assert included.first_response.cases == 2
    assert excluded.first_response.cases == 1
    assert dict(excluded.status_rows)["Abierta"] == 1
    assert included.advisor_response.count == 2
    assert excluded.advisor_response.count == 1


def test_more_channels_than_limit_are_grouped_in_otros(env_factory, panel):
    """R13: con más canales que el tope, el gráfico conserva los mayores y «Otros»."""
    env = env_factory()
    infos = [
        channel_info(f"canal-{index}", name=f"Canal {index}")
        for index in range(15)
    ]
    _set_channels(env, *infos)
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    for index in range(15):
        contact = _contact(env, f"canal-{index}", str(100 + index), now)
        for minute in range(index + 1):
            env.repo.add_message(
                contact.id, "user", "hola", now - timedelta(minutes=minute + 1)
            )

    data = _dashboard(env, profile)

    assert len(data.messages) == 12
    assert data.messages[-1].label == "Otros"
    assert len(data.message_labels) == 15


def test_cases_by_status_include_zero_states_and_filter_simulated(
    env_factory, panel
):
    """R14, R23: estados fijos con ceros y exclusión de casos simulados."""
    env = env_factory()
    _set_channels(env, _telegram(), _simulado())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    telegram = _contact(env, "telegram", "8", now)
    simulado = _contact(env, "simulado", "9", now)
    env.repo.link_case("case-open", telegram.id, now - timedelta(hours=4))
    env.repo.link_case("case-sim", simulado.id, now - timedelta(hours=4))
    env.handover.case_list = [
        panel.case_item("case-open", status="open", created_at=now - timedelta(hours=4)),
        panel.case_item("case-sim", status="closed", created_at=now - timedelta(hours=4)),
    ]

    data = _dashboard(env, profile, include_simulated=False)

    assert data.statuses is not None
    assert [datum.label for datum in data.statuses] == [
        "Abierta",
        "Asignada",
        "Vencida",
        "Cerrada",
    ]
    assert dict(data.status_rows) == {
        "Abierta": 1,
        "Asignada": 0,
        "Vencida": 0,
        "Cerrada": 0,
    }


def test_handover_unavailable_keeps_other_charts(env_factory, panel):
    """R15: si handover cae, los estados se muestran como no disponibles."""
    env = env_factory()
    _set_channels(env, _telegram())
    profile = panel.login_admin(env)
    now = env.adapters.clock()
    contact = _contact(env, "telegram", "10", now)
    env.repo.link_case("case-1", contact.id, now - timedelta(hours=3))
    env.repo.add_message(contact.id, "user", "hola", now - timedelta(hours=2))
    env.repo.add_message(
        contact.id, "advisor", "respuesta", now - timedelta(hours=1)
    )
    env.handover.fail_list_cases = True

    data = _dashboard(env, profile)

    assert data.statuses is None
    assert _labels(data) == {"Telegram": 2}
    assert data.first_response.cases == 1
    assert data.advisor_response.count == 1


def test_case_first_responses_can_exclude_channels(env_factory, panel):
    """R23, R26: el parámetro opcional excluye canales sin cambiar el caso base."""
    env = env_factory()
    _set_channels(env, _telegram(), _simulado())
    panel.login_admin(env)
    now = env.adapters.clock()
    telegram = _contact(env, "telegram", "11", now)
    simulado = _contact(env, "simulado", "12", now)
    env.repo.link_case("case-tg", telegram.id, now - timedelta(hours=3))
    env.repo.link_case("case-sim", simulado.id, now - timedelta(hours=3))

    all_rows = env.repo.case_first_responses(
        now - timedelta(days=7), now
    )
    without_simulated = env.repo.case_first_responses(
        now - timedelta(days=7), now, frozenset({"simulado"})
    )

    assert len(all_rows) == 2
    assert len(without_simulated) == 1


def test_admin_metrics_view_does_not_show_p90(env_factory, panel):
    """R26: /admin/metricas conserva lo que muestra; p90 solo aparece en dashboard."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    now = env.adapters.clock()
    contact = _contact(env, "telegram", "13", now)
    env.repo.link_case("case-1", contact.id, now - timedelta(hours=3))
    env.repo.add_message(contact.id, "user", "hola", now - timedelta(hours=2))
    env.repo.add_message(
        contact.id, "advisor", "respuesta", now - timedelta(hours=1)
    )

    response = env.client.get("/admin/metricas?dias=7")

    assert response.status_code == 200
    assert "p90" not in response.text.lower()
