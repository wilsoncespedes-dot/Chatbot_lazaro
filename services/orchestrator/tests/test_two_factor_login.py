"""Login con segundo factor en el orquestador (#54)."""
from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from orchestrator.accounts import hash_password, hash_token
from orchestrator.domain import (
    LoginThrottled,
    TwoFactorCodeInvalid,
    TwoFactorCodeRequired,
    TwoFactorUnavailable,
    authenticate_profile,
)
from orchestrator.two_factor import (
    encrypt_secret,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    totp_at,
)

PASSWORD = "ClaveSegura123"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
STEP = int(NOW.timestamp()) // 30
IP = "10.0.0.1"


@pytest.fixture()
def env(env_factory):
    return env_factory(
        panel_2fa_encryption_key=KEY,
        panel_2fa_required=False,
        admin_cookie_secure=False,
        password_hash_iterations=100000,
        admin_login_max_attempts=5,
    )


def _profile(env, username="admin1", role="admin"):
    return env.repo.create_profile(
        username, role, hash_password(PASSWORD, 100000), NOW
    )


def _enable(env, profile, *, last_step=STEP - 5, recovery=()):
    secret = generate_secret()
    env.repo.save_pending_two_factor(
        profile.id, encrypt_secret(secret, KEY), NOW
    )
    env.repo.activate_two_factor(
        profile.id,
        last_step,
        [hash_recovery_code(code) for code in recovery],
        NOW,
    )
    return secret


def _login(env, code="", username="admin1", password=PASSWORD):
    return authenticate_profile(
        username, password, IP, "admin", env.settings, env.adapters, code
    )


def _session(env, token):
    assert token is not None
    return env.repo.get_session(hash_token(token), NOW)


def test_login_without_factor_only_needs_password(env):
    """R26: sin obligatoriedad ni factor activo, la contraseña basta."""
    profile = _profile(env)
    token = _login(env)
    assert _session(env, token) is not None
    assert env.repo.get_two_factor(profile.id) is None


def test_login_with_active_factor_requires_valid_code(env):
    """R10, R14: el código válido crea la sesión y limpia los fallos."""
    profile = _profile(env)
    secret = _enable(env, profile)
    env.repo.record_login_failure("admin1", IP, NOW, NOW)
    token = _login(env, totp_at(secret, STEP))
    assert _session(env, token) is not None
    assert env.repo.login_failures == []


def test_missing_code_does_not_count_as_failure(env):
    """R11: sin código responde two_factor_required y no cuenta el intento."""
    profile = _profile(env)
    _enable(env, profile)
    with pytest.raises(TwoFactorCodeRequired):
        _login(env)
    assert env.repo.login_failures == []


def test_wrong_code_counts_as_failure_and_creates_no_session(env):
    """R12: un código incorrecto cuenta igual que una contraseña errónea."""
    profile = _profile(env)
    _enable(env, profile)
    before = len(env.repo.sessions)
    with pytest.raises(TwoFactorCodeInvalid):
        _login(env, "000000")
    assert len(env.repo.sessions) == before
    assert len(env.repo.login_failures) == 1


def test_throttle_wins_even_with_correct_code(env_factory):
    """R13: al alcanzar el límite, un código correcto también responde 429."""
    env = env_factory(
        panel_2fa_encryption_key=KEY,
        panel_2fa_required=False,
        password_hash_iterations=100000,
        admin_login_max_attempts=2,
    )
    profile = _profile(env)
    secret = _enable(env, profile)
    env.repo.record_login_failure("admin1", IP, NOW, NOW)
    env.repo.record_login_failure("admin1", IP, NOW, NOW)
    with pytest.raises(LoginThrottled):
        _login(env, totp_at(secret, STEP))


def test_repeated_and_previous_steps_are_rejected(env):
    """R17, R18: el mismo paso o uno anterior no se aceptan dos veces."""
    profile = _profile(env)
    secret = _enable(env, profile)
    code = totp_at(secret, STEP)
    assert _session(env, _login(env, code)) is not None
    with pytest.raises(TwoFactorCodeInvalid):
        _login(env, code)
    with pytest.raises(TwoFactorCodeInvalid):
        _login(env, totp_at(secret, STEP - 1))


def test_confirmation_step_cannot_be_reused_at_login(env):
    """R20: el paso del código de confirmación queda consumido desde el registro."""
    profile = _profile(env)
    secret = generate_secret()
    env.repo.save_pending_two_factor(profile.id, encrypt_secret(secret, KEY), NOW)
    assert env.repo.activate_two_factor(profile.id, STEP, [], NOW) is True
    with pytest.raises(TwoFactorCodeInvalid):
        _login(env, totp_at(secret, STEP))


def test_window_allows_only_configured_offset(env):
    """R2, R3: el paso siguiente se acepta con ventana 1 y el +2 no."""
    profile = _profile(env)
    secret = _enable(env, profile)
    assert _session(env, _login(env, totp_at(secret, STEP + 1))) is not None
    with pytest.raises(TwoFactorCodeInvalid):
        _login(env, totp_at(secret, STEP + 2))


def test_recovery_code_is_single_use_and_audited(env):
    """R32, R33, R34: un código de recuperación se consume y deja auditoría."""
    profile = _profile(env)
    codes = generate_recovery_codes(1)
    _enable(env, profile, recovery=codes)
    varied = f" {codes[0].upper()} "
    assert _session(env, _login(env, varied)) is not None
    assert any(
        row.action == "two_factor_recovery_used" and row.result == "ok"
        for row in env.repo.panel_audit
    )
    with pytest.raises(TwoFactorCodeInvalid):
        _login(env, codes[0])
    assert len(env.repo.login_failures) == 1


def test_invalid_key_fails_closed(env_factory):
    """R16: si la clave no descifra, el login se deniega sin crear sesión."""
    env = env_factory(
        panel_2fa_encryption_key="clave-invalida",
        panel_2fa_required=False,
        password_hash_iterations=100000,
    )
    profile = _profile(env)
    _enable(env, profile)
    before = len(env.repo.sessions)
    with pytest.raises(TwoFactorUnavailable):
        _login(env, "123456")
    assert len(env.repo.sessions) == before


def test_unknown_user_and_wrong_password_share_result(env):
    """R15: usuario inexistente y contraseña incorrecta dan el mismo None."""
    _profile(env)
    assert _login(env, username="nadie", password="otra") is None
    assert _login(env, password="otra") is None


def test_required_without_factor_creates_restricted_session(env_factory):
    """R23: con el factor obligatorio y sin activar, la sesión solo registra."""
    env = env_factory(
        panel_2fa_encryption_key=KEY,
        panel_2fa_required=True,
        password_hash_iterations=100000,
    )
    _profile(env)
    token = _login(env)
    assert token is not None
    session = env.repo.get_session_any(hash_token(token), NOW)
    assert session is not None and session.enroll_only is True


def test_client_role_cannot_use_staff_login(env):
    """R45: el rol cliente no obtiene sesión de personal."""
    _profile(env, role="cliente")
    assert _login(env) is None
