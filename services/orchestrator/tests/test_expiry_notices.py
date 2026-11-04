"""Avisos de vencimiento de credenciales (#42)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from lazaro_contracts import ExpiryNoticeRunResponse

from orchestrator.adapters.repository import WhatsAppTemplate
from orchestrator.domain import ClientSession, send_expiry_notices

NOW = None


@pytest.fixture()
def env(env_factory):
    env = env_factory(admin_cookie_secure=False)
    env.repo.save_conversation_texts(
        replace(
            env.repo.get_conversation_texts(),
            expiry_notice="Tu acceso vence en {dias} días, el {fecha}.",
        ),
        "admin-1",
        env.adapters.clock(),
    )
    return env


def _client(
    env,
    username="cliente1",
    valid_until=None,
    channel="telegram",
    external_user_id="10",
    chat="100",
    with_session=True,
):
    now = env.adapters.clock()
    profile = env.repo.create_client_credential(
        username,
        "hash",
        now - timedelta(days=1),
        valid_until or now + timedelta(days=3),
        now,
    )
    contact = env.repo.get_or_create_channel_contact(
        channel, external_user_id, chat, now
    )
    if with_session:
        env.repo.client_sessions[f"s-{username}"] = ClientSession(
            id=f"s-{username}",
            profile_id=profile.id,
            contact_id=contact.id,
            started_at=now,
            last_activity_at=now,
        )
    return profile, contact


def test_sends_text_with_days_and_local_date(env):
    """R45, R46, R50, R57: candidata, texto con {dias}/{fecha}, evento y auditoría."""
    profile, contact = _client(env, valid_until=env.adapters.clock() + timedelta(days=3))
    response = send_expiry_notices(env.settings, env.adapters)
    assert isinstance(response, ExpiryNoticeRunResponse)
    assert (response.enabled, response.candidates, response.sent_text) == (True, 1, 1)
    assert "3 días" in env.gateway.channel_sent[-1][2]
    assert "04/01/2026" in env.gateway.channel_sent[-1][2]
    assert ("expiry_notice", "text") in env.events()
    assert any(
        audit.action == "expiry_notice" and audit.profile_id == profile.id
        for audit in env.repo.identity_audits
    )


def test_does_not_write_messages_state_or_session_activity(env):
    """R59: el aviso no altera historial, estado ni actividad de la sesión."""
    profile, contact = _client(env)
    before_messages = len(env.repo.messages)
    before_states = dict(env.repo.conversation_states)
    before_activity = env.repo.client_sessions[f"s-cliente1"].last_activity_at
    send_expiry_notices(env.settings, env.adapters)
    assert len(env.repo.messages) == before_messages
    assert env.repo.conversation_states == before_states
    assert env.repo.client_sessions[f"s-cliente1"].last_activity_at == before_activity


def test_candidates_follow_effective_expiry_notice_days(env):
    """R46, R40: cambiar identity.expiry_notice_days en caliente cambia candidatas."""
    _client(env, valid_until=env.adapters.clock() + timedelta(days=3))
    env.repo.save_app_settings({"identity.expiry_notice_days": "1"}, ())
    assert send_expiry_notices(env.settings, env.adapters).candidates == 0
    env.repo.save_app_settings({"identity.expiry_notice_days": "10"}, ())
    assert send_expiry_notices(env.settings, env.adapters).candidates == 1


def test_disabled_sends_nothing_and_writes_nothing(env):
    """R47: desactivado no envía ni escribe en credential_expiry_notices."""
    _client(env)
    env.repo.save_app_settings({"expiry_notice.enabled": "false"}, ())
    send_expiry_notices(env.settings, env.adapters)
    assert env.repo.expiry_notices == {}
    assert env.gateway.channel_sent == []


def test_disabled_reports_enabled_false(env):
    """R47: desactivado responde enabled=false."""
    _client(env)
    env.repo.save_app_settings({"expiry_notice.enabled": "false"}, ())
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.enabled is False


def test_out_of_hours_skips_without_claiming(env):
    """R48: fuera de horario no reclama ni envía avisos."""
    _client(env)
    env.repo.save_app_settings({"business_hours.enabled": "true"}, ())
    send_expiry_notices(env.settings, env.adapters)
    assert env.repo.expiry_notices == {}
    assert env.gateway.channel_sent == []


def test_out_of_hours_counts_candidates(env):
    """R48: fuera de horario cuenta las candidatas en skipped.out_of_hours."""
    _client(env)
    env.repo.save_app_settings({"business_hours.enabled": "true"}, ())
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.skipped["out_of_hours"] == 1


def test_no_chat_is_skipped_without_writing(env):
    """R49: una candidata sin contacto se cuenta en no_chat sin escribir."""
    _client(env, with_session=False)
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.skipped["no_chat"] == 1
    assert env.repo.expiry_notices == {}


def test_whatsapp_closed_window_sends_only_template_with_variables(env):
    """R51: WhatsApp con ventana cerrada envía solo TemplateBlock con variables."""
    _client(env, channel="whatsapp", external_user_id="57300", chat="57300")
    env.repo.create_whatsapp_template(
        WhatsAppTemplate(
            name="aviso_vencimiento",
            purpose="expiry_notice",
            language="es",
            variables=2,
            body="Hola {{1}} {{2}}",
            status="approved",
            approved_by="admin1",
            approved_at=env.adapters.clock(),
            updated_at=env.adapters.clock(),
        )
    )
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.sent_template == 1
    blocks = env.gateway.blocks_sent[-1][2]
    assert len(blocks) == 1
    assert blocks[0].type == "template"
    assert blocks[0].name == "aviso_vencimiento"
    assert blocks[0].variables == ["3", "04/01/2026"]
    assert env.gateway.blocks_sent[-1][1] == "57300"


def test_no_text_and_no_template_are_skipped_without_writing(env):
    """R52: sin texto o sin plantilla efectiva no se envía ni se escribe."""
    _client(env)
    env.repo.save_conversation_texts(
        replace(env.repo.get_conversation_texts(), expiry_notice=""), "admin", env.adapters.clock()
    )
    assert send_expiry_notices(env.settings, env.adapters).skipped["no_text"] == 1
    assert env.repo.expiry_notices == {}

    _client(env, username="cliente2", channel="whatsapp", external_user_id="57301", chat="57301")
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.skipped["no_template"] == 1
    assert env.repo.expiry_notices == {}


def test_success_is_sent_only_once_and_sending_orphan_is_not_retried(env):
    """R53, R55: un periodo se envía exactamente una vez; `sending` no se reintenta."""
    profile, _ = _client(env)
    send_expiry_notices(env.settings, env.adapters)
    send_expiry_notices(env.settings, env.adapters)
    assert len(env.gateway.channel_sent) == 1
    assert send_expiry_notices(env.settings, env.adapters).skipped["already_notified"] == 1

    _client(env, username="cliente2", external_user_id="11", chat="101")
    other = next(p for p in env.repo.profiles.values() if p.username == "cliente2")
    valid_until = env.repo.client_credentials[other.id].valid_until
    env.repo.expiry_notices[(other.id, valid_until)] = {
        "status": "sending", "method": None, "attempts": 1,
        "created_at": env.adapters.clock(), "updated_at": env.adapters.clock(),
    }
    assert send_expiry_notices(env.settings, env.adapters).skipped["already_notified"] >= 1


def test_failure_marks_failed_and_retries_until_max(env):
    """R58, R53: un fallo marca failed, incrementa intentos y reintenta hasta el máximo."""
    env.settings.expiry_notice_max_attempts = 2
    _client(env)
    env.gateway.fail = True
    assert send_expiry_notices(env.settings, env.adapters).failed == 1
    assert send_expiry_notices(env.settings, env.adapters).failed == 1
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.skipped["already_notified"] == 1
    [(row)] = env.repo.expiry_notices.values()
    assert row["status"] == "failed" and row["attempts"] == 2


def test_failure_then_success_retries_once(env):
    """R58: tras un fallo, el siguiente intento puede enviar y marcar sent."""
    _client(env)
    env.gateway.fail = True
    send_expiry_notices(env.settings, env.adapters)
    env.gateway.fail = False
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.sent_text == 1
    [(row)] = env.repo.expiry_notices.values()
    assert row["status"] == "sent"


def test_two_concurrent_passes_send_at_most_one_notice(env):
    """R54: dos pasadas concurrentes no duplican el aviso."""
    _client(env)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: send_expiry_notices(env.settings, env.adapters), range(2)))
    assert len(env.gateway.channel_sent) == 1


def test_renewal_creates_a_new_period_that_can_notify_again(env):
    """R56: el periodo nuevo avisa una vez y no avisa si no vuelve a ser candidato."""
    profile, _ = _client(env, valid_until=env.adapters.clock() + timedelta(days=3))
    send_expiry_notices(env.settings, env.adapters)
    far = env.adapters.clock() + timedelta(days=60)
    env.repo.renew_client_credential(profile.id, far, env.adapters.clock())
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.candidates == 0

    near = env.adapters.clock() + timedelta(days=2)
    env.repo.renew_client_credential(profile.id, near, env.adapters.clock())
    response = send_expiry_notices(env.settings, env.adapters)
    assert response.sent_text == 1
    assert len(env.gateway.channel_sent) == 2
