"""Dominio puro del panel en tiempo real (#53)."""
from __future__ import annotations

from orchestrator.panel_live import (
    PanelEvent,
    dedupe_new_events,
    event_payload,
    origin_allowed,
)


def test_origin_allowed_exact_match_and_host_fallback():
    """R3, R4, R5: lista exacta o, vacía, comparación con `Host`."""
    allowed = ("https://panel.example", "http://localhost:8000")
    assert origin_allowed("https://panel.example", None, allowed)
    assert origin_allowed("http://localhost:8000", None, allowed)
    assert not origin_allowed("https://evil.example", None, allowed)
    assert not origin_allowed("https://panel.example/", None, allowed)

    assert not origin_allowed(None, "panel.example", ())
    assert origin_allowed("http://panel.example", "panel.example", ())
    assert origin_allowed("http://panel.example:8000", "panel.example:8000", ())
    assert not origin_allowed("http://panel.example:8000", "panel.example", ())
    assert not origin_allowed("http://evil.example", "panel.example", ())


def test_event_payload_has_only_allowed_keys():
    """R13: el aviso solo lleva `type`, `id` y `case_id`."""
    payload = event_payload(PanelEvent(id=7, case_id="case-1", kind="message"))
    assert payload == {"type": "message", "id": 7, "case_id": "case-1"}
    assert set(payload) == {"type", "id", "case_id"}


def test_dedupe_new_events_delivers_each_id_once():
    """R20: un id repetido en la ventana de solape no se entrega dos veces."""
    seen: set[int] = set()
    first = dedupe_new_events(
        [
            PanelEvent(id=1, case_id="a", kind="message"),
            PanelEvent(id=2, case_id="b", kind="case_updated"),
            PanelEvent(id=1, case_id="a", kind="message"),
        ],
        seen,
    )
    assert [event.id for event in first] == [1, 2]
    assert seen == {1, 2}
    second = dedupe_new_events(
        [PanelEvent(id=1, case_id="a", kind="message")], seen
    )
    assert second == []
