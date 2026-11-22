"""Ajustes de intención de compra en el panel (#70)."""
from __future__ import annotations

import pytest

from orchestrator.domain import operational_settings

CSRF = "csrf-token"


@pytest.fixture()
def env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def _save(env, **changes):
    data = {"csrf_token": CSRF, **changes}
    return env.client.post("/admin/ajustes", data=data, follow_redirects=False)


def test_settings_page_shows_initial_phrases_defaults_and_range(env):
    """R1, R4: las cuatro claves aparecen con valor inicial, por defecto y rango."""
    page = env.client.get("/admin/ajustes")

    assert page.status_code == 200
    text = page.text
    assert "purchase_intent.phrases" in text
    assert "purchase_intent.enabled" in text
    assert "purchase_intent.interval_minutes" in text
    assert "purchase_intent.create_case" in text
    assert "me interesa,quiero reservar,quiero comprar" in text
    assert "1-30 frases separadas por comas" in text
    assert "1..1440" in text


def test_valid_settings_are_saved_and_apply_immediately(env):
    """R1, R4: guardar cambia las frases y los tres ajustes sin reiniciar."""
    response = _save(
        env,
        **{
            "purchase_intent.phrases": "Me interesa, Quiero reservar",
            "purchase_intent.enabled": "false",
            "purchase_intent.interval_minutes": "30",
            "purchase_intent.create_case": "true",
        },
    )

    assert response.status_code == 303
    operational = operational_settings(env.settings, env.adapters)
    assert operational.purchase_intent_phrases == ("me interesa", "quiero reservar")
    assert operational.purchase_intent_enabled is False
    assert operational.purchase_intent_interval_minutes == 30
    assert operational.purchase_intent_create_case is True


@pytest.mark.parametrize(
    "phrases",
    ["", "ab", "x" * 81, ",".join(f"frase {i}" for i in range(31)), "me interesa,\x00"],
)
def test_invalid_phrases_reject_the_form_without_saving(env, phrases):
    """R2: una lista inválida responde 422 y no guarda ningún ajuste."""
    before = env.repo.get_app_settings(("purchase_intent.",))

    response = _save(
        env,
        **{
            "purchase_intent.phrases": phrases,
            "purchase_intent.enabled": "true",
        },
    )

    assert response.status_code == 422
    assert 'data-code="validation_error"' in response.text
    assert env.repo.get_app_settings(("purchase_intent.",)) == before


def test_invalid_stored_phrases_fall_back_to_the_environment(env):
    """R3: un valor guardado inválido se resuelve con PURCHASE_INTENT_PHRASES."""
    env.repo.save_app_settings({"purchase_intent.phrases": "ab"}, ())

    operational = operational_settings(env.settings, env.adapters)

    assert operational.purchase_intent_phrases == env.settings.purchase_intent_phrase_list


def test_settings_escape_html_in_effective_values(env):
    """R24: el panel escapa el texto de las frases antes de pintarlo."""
    response = _save(env, **{"purchase_intent.phrases": "<b>oferta</b>"})
    assert response.status_code == 303

    text = env.client.get("/admin/ajustes").text

    assert "&lt;b&gt;oferta&lt;/b&gt;" in text
    assert "<b>oferta</b>" not in text


def test_advisor_session_cannot_save_purchase_settings(env_factory, panel):
    """R4: solo un administrador con sesión puede guardar los ajustes."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login(env, "asesor")

    response = _save(
        env,
        **{
            "purchase_intent.phrases": "me interesa",
            "purchase_intent.enabled": "false",
        },
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert env.repo.get_app_settings(("purchase_intent.",)) == {}
