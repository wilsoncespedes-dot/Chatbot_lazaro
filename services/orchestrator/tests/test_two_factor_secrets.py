"""Confidencialidad del secreto, los códigos y la URI del segundo factor (#54)."""
from __future__ import annotations

import base64
import logging
import re
from datetime import timedelta

from orchestrator.accounts import hash_password
from orchestrator.two_factor import (
    encrypt_secret,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    totp_at,
)

PASSWORD = "ClaveSegura123"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
SECRET_RE = re.compile(r"Secreto: <code>([A-Z2-7]+)</code>")
RECOVERY_RE = re.compile(r"<code>([a-z2-7]{4}(?:-[a-z2-7]{4}){3})</code>")


def _env(env_factory):
    return env_factory(
        panel_2fa_encryption_key=KEY,
        panel_2fa_required=False,
        admin_cookie_secure=False,
        password_hash_iterations=100000,
    )


def _profile(env, username: str):
    return env.repo.create_profile(
        username, "admin", hash_password(PASSWORD, 100000), env.adapters.clock()
    )


def _login(env, username: str, code: str = ""):
    return env.client.post(
        "/admin/login",
        data={"username": username, "password": PASSWORD, "code": code},
        follow_redirects=False,
    )


def _csrf(env) -> str:
    response = env.client.get("/admin/2fa")
    assert response.status_code == 200
    match = CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


def _totp(secret_base32: str, env) -> str:
    padding = "=" * ((8 - len(secret_base32) % 8) % 8)
    secret = base64.b32decode(secret_base32 + padding)
    step = int(env.adapters.clock().timestamp()) // 30
    return totp_at(secret, step)


def _sinks(env) -> str:
    return (
        str(env.repo.panel_audit)
        + str(env.repo.panel_events)
        + str(env.repo.two_factor)
    )


def test_enrollment_login_and_reset_never_leak_secrets(env_factory, caplog):
    """R27, R28, R29: el secreto, la URI y los códigos no salen de su respuesta única."""
    env = _env(env_factory)
    actor = _profile(env, "admin1")
    target = _profile(env, "admin2")
    target_secret = generate_secret()
    env.repo.save_pending_two_factor(
        target.id, encrypt_secret(target_secret, KEY), env.adapters.clock()
    )
    env.repo.activate_two_factor(target.id, 1, ["hash-target"], env.adapters.clock())
    caplog.set_level(logging.DEBUG)

    _login(env, "admin1")
    started = env.client.post(
        "/admin/2fa/start",
        data={"csrf_token": _csrf(env)},
        follow_redirects=False,
    )
    secret = SECRET_RE.search(started.text)
    assert secret is not None
    uri = "otpauth://totp/"
    assert uri in started.text
    code = _totp(secret.group(1), env)
    confirmed = env.client.post(
        "/admin/2fa/confirm",
        data={"csrf_token": _csrf(env), "code": code},
        follow_redirects=False,
    )
    recovery = RECOVERY_RE.findall(confirmed.text)
    assert recovery

    later = env.client.get("/admin/2fa").text
    for value in [secret.group(1), uri, *recovery]:
        assert value not in later
        assert value not in caplog.text
        assert value not in _sinks(env)
    assert code not in caplog.text
    assert code not in str(env.repo.panel_audit) + str(env.repo.panel_events)

    stored = env.repo.two_factor[actor.id]
    assert secret.group(1) not in stored.secret_ciphertext
    assert secret.group(1).lower() not in stored.secret_ciphertext.lower()

    reset = env.client.post(
        f"/admin/profiles/{target.id}/2fa/reset",
        data={"csrf_token": _csrf(env)},
        follow_redirects=False,
    )
    assert reset.status_code == 303
    assert target_secret.hex() not in caplog.text
    assert target_secret.hex() not in _sinks(env)


def test_recovery_login_does_not_log_the_code(env_factory, caplog):
    """R29, R32: usar un código de recuperación no lo escribe en logs ni auditoría."""
    env = _env(env_factory)
    profile = _profile(env, "admin1")
    secret = generate_secret()
    env.repo.save_pending_two_factor(
        profile.id, encrypt_secret(secret, KEY), env.adapters.clock()
    )
    codes = generate_recovery_codes(1)
    env.repo.activate_two_factor(
        profile.id,
        0,
        [hash_recovery_code(codes[0])],
        env.adapters.clock(),
    )
    caplog.set_level(logging.DEBUG)
    response = _login(env, "admin1", codes[0])
    assert response.status_code == 303
    assert codes[0] not in caplog.text
    assert codes[0] not in _sinks(env)
    assert any(
        row.action == "two_factor_recovery_used" and row.result == "ok"
        for row in env.repo.panel_audit
    )
