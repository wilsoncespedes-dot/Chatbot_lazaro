"""Tests de perfiles y vinculación de Telegram (feature #20 verificacion_cuentas)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.accounts import (
    hash_password,
    hash_token,
    new_link_token,
    parse_start_token,
    verify_password,
)
from orchestrator.adapters.repository import PostgresRepository

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD = "clave-segura-123"


def _create_profile(
    env, username: str = "admin1", role: str = "admin", password: str = PASSWORD
):
    env.settings.password_hash_iterations = 100000
    return env.client.post(
        "/profiles",
        json={"username": username, "role": role, "password": password},
        headers=HEADERS,
    )


def _issue(env, profile_id: str):
    return env.client.post(f"/profiles/{profile_id}/link-token", headers=HEADERS)


def _setup_link(env, username: str = "admin1") -> tuple[dict, str]:
    profile = _create_profile(env, username=username).json()
    token = _issue(env, profile["id"]).json()["token"]
    return profile, token


# --- R1: creación de perfiles -------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "asesor", "cliente"])
def test_create_profile_returns_201_without_password(env, role):
    """R1, R3: cada rol crea un perfil y la respuesta no incluye la clave ni el hash."""
    response = _create_profile(env, role=role)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "username", "role", "linked"}
    assert (body["username"], body["role"], body["linked"]) == ("admin1", role, False)
    assert PASSWORD not in response.text
    assert PASSWORD not in env.repo.profiles[body["id"]].password_hash


def test_create_profile_normalizes_username_to_lowercase(env):
    """R1: el username se guarda en minúsculas tras cumplir el patrón."""
    response = _create_profile(env, username="Admin.One-1_2")
    assert response.status_code == 201
    assert response.json()["username"] == "admin.one-1_2"


@pytest.mark.parametrize("role", ["root", "ADMIN", "", "administrador"])
def test_invalid_role_returns_422(env, role):
    """R1: un rol fuera de la lista no crea perfil."""
    response = _create_profile(env, role=role)
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert env.repo.profiles == {}


@pytest.mark.parametrize("username", ["ab", "con espacio", "acentué", "a" * 65, ""])
def test_invalid_username_returns_422(env, username):
    """R1: username fuera de 3–64 o del patrón se rechaza."""
    response = _create_profile(env, username=username)
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert env.repo.profiles == {}


def test_short_password_returns_422(env):
    """R1: una contraseña más corta que PROFILE_PASSWORD_MIN_LENGTH no crea perfil."""
    response = env.client.post(
        "/profiles",
        json={"username": "admin1", "role": "admin", "password": "corta"},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert env.repo.profiles == {}


def test_password_min_length_is_configurable(env):
    """R1: el mínimo de contraseña sale de PROFILE_PASSWORD_MIN_LENGTH."""
    env.settings.profile_password_min_length = 4
    env.settings.password_hash_iterations = 100000
    response = env.client.post(
        "/profiles",
        json={"username": "admin1", "role": "admin", "password": "abcd"},
        headers=HEADERS,
    )
    assert response.status_code == 201


# --- R2: unicidad de username ------------------------------------------------------------


def test_duplicate_username_is_case_insensitive_and_returns_409(env):
    """R2: el username duplicado, con otra caja, responde username_taken sin crear otro."""
    assert _create_profile(env, username="Admin1").status_code == 201
    response = _create_profile(env, username="admin1")
    assert response.status_code == 409
    assert response.json()["error"] == "username_taken"
    assert len(env.repo.profiles) == 1


# --- R3: almacenamiento del hash ---------------------------------------------------------


def test_hash_password_format_salt_and_verify():
    """R3: PBKDF2-SHA256 con sal de 16 bytes y comparación de la clave original."""
    stored = hash_password(PASSWORD, 1000)
    scheme, iterations, salt_hex, digest_hex = stored.split("$")
    assert scheme == "pbkdf2_sha256"
    assert iterations == "1000"
    assert len(bytes.fromhex(salt_hex)) == 16
    assert len(bytes.fromhex(digest_hex)) == 32
    assert verify_password(PASSWORD, stored) is True
    assert verify_password(PASSWORD + "x", stored) is False
    assert verify_password(PASSWORD, "basura") is False
    assert hash_password(PASSWORD, 1000) != stored


def test_profile_password_never_appears_in_logs(env, caplog):
    """R3: ni la petición ni la respuesta dejan la clave en el log."""
    caplog.set_level(logging.DEBUG)
    response = _create_profile(env)
    assert response.status_code == 201
    assert PASSWORD not in caplog.text


# --- R4: emisión del token de vínculo ----------------------------------------------------


def test_issue_link_token_stores_only_hash_and_uses_fixed_ttl(env):
    """R4: token aleatorio, SHA-256 en la fila y expiración con el reloj inyectado."""
    profile = _create_profile(env).json()
    env.settings.link_token_ttl_minutes = 30
    env.settings.telegram_bot_username = "LazaroBot"
    response = _issue(env, profile["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["token"] and body["token"] != ""
    assert body["link"] == f"https://t.me/LazaroBot?start={body['token']}"
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert expires_at == FIXED_NOW + timedelta(minutes=30)

    stored = env.repo.link_tokens[hash_token(body["token"])]
    assert stored.profile_id == profile["id"]
    assert stored.expires_at == expires_at
    assert stored.used_at is None
    assert body["token"] not in env.repo.link_tokens


def test_issue_link_token_link_is_null_without_bot_username(env):
    """R4: sin TELEGRAM_BOT_USERNAME no se inventa un enlace."""
    profile = _create_profile(env).json()
    response = _issue(env, profile["id"])
    assert response.status_code == 201
    assert response.json()["link"] is None


# --- R5: perfil inexistente --------------------------------------------------------------


def test_issue_link_token_for_unknown_profile_returns_404(env):
    """R5: perfil inexistente → profile_not_found y ningún token guardado."""
    response = _issue(env, "no-existe")
    assert response.status_code == 404
    assert response.json()["error"] == "profile_not_found"
    assert env.repo.link_tokens == {}


# --- R10: rutas internas autenticadas ----------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "malo"}])
def test_profile_routes_require_service_token(env, headers):
    """R10: sin token válido no se crea perfil ni se emite token."""
    create = env.client.post(
        "/profiles",
        json={"username": "admin1", "role": "admin", "password": PASSWORD},
        headers=headers,
    )
    issue = env.client.post("/profiles/p1/link-token", headers=headers)
    assert create.status_code == 401
    assert issue.status_code == 401
    assert create.json()["error"] == "unauthorized"
    assert issue.json()["error"] == "unauthorized"
    assert env.repo.profiles == {} and env.repo.link_tokens == {}


# --- parse_start_token -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/start abc123", "abc123"),
        ("/start   abc123  ", "abc123"),
        ("/start", None),
        ("/start a b", None),
        ("hola", None),
        ("", None),
    ],
)
def test_parse_start_token(text, expected):
    """R6: solo "/start <token>" produce token; el resto sigue el flujo actual."""
    assert parse_start_token(text) == expected


# --- R6, R7: vínculo por Telegram --------------------------------------------------------


def test_start_token_links_sender_and_consumes_token(env, caplog):
    """R6, R9: vínculo correcto, token consumido, aviso fijo y ningún dato del token guardado."""
    caplog.set_level(logging.DEBUG)
    profile, token = _setup_link(env)
    contact = env.repo.get_or_create_contact(10, 100, FIXED_NOW)
    env.repo.link_case("case-1", contact.id, FIXED_NOW)
    env.handover.client_message_status = "forwarded"
    env.post(text=f"/start {token}", user=10, chat=100)

    stored = env.repo.profiles[profile["id"]]
    assert stored.telegram_user_id == 10
    assert env.repo.link_tokens[hash_token(token)].used_at == FIXED_NOW
    assert env.gateway.sent == [(100, env.settings.link_success_reply)]
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.rag.calls == [] and env.llm.calls == []
    assert env.handover.requests == [] and env.handover.client_messages == []
    assert token not in caplog.text
    assert profile["username"] not in caplog.text


def test_unknown_token_sends_failed_reply_without_consuming(env, caplog):
    """R7, R9: token inexistente → fallo fijo, sin rastro del token ni llamadas externas."""
    caplog.set_level(logging.DEBUG)
    token = new_link_token()
    env.post(text=f"/start {token}", user=10, chat=100)
    assert env.gateway.sent == [(100, env.settings.link_failed_reply)]
    assert env.repo.link_tokens == {}
    assert all(token not in m.text for m in env.repo.messages)
    assert all(token not in e.reason for e in env.repo.events)
    assert token not in caplog.text
    assert env.rag.calls == [] and env.llm.calls == [] and env.handover.requests == []


def test_expired_token_sends_failed_reply_and_stays_unused(env):
    """R7: token expirado → fallo fijo, sin vínculo y sin consumir."""
    profile, token = _setup_link(env)
    env.adapters.clock = lambda: FIXED_NOW + timedelta(minutes=16)
    env.post(text=f"/start {token}", user=10, chat=100)
    assert env.gateway.sent == [(100, env.settings.link_failed_reply)]
    assert env.repo.profiles[profile["id"]].telegram_user_id is None
    assert env.repo.link_tokens[hash_token(token)].used_at is None


def test_reused_token_sends_failed_reply(env):
    """R7: un token ya usado no vuelve a vincular a otra cuenta."""
    profile, token = _setup_link(env)
    env.post(text=f"/start {token}", user=10, chat=100)
    env.gateway.sent.clear()
    env.post(text=f"/start {token}", user=11, chat=101, update_id=2)
    assert env.gateway.sent == [(101, env.settings.link_failed_reply)]
    assert env.repo.profiles[profile["id"]].telegram_user_id == 10


def test_account_already_linked_to_another_profile_sends_failed_reply(env):
    """R7: si el telegram_user_id ya está vinculado, el token nuevo no se consume."""
    _setup_link(env, username="admin1")
    first_token = next(iter(env.repo.link_tokens))
    assert env.repo.consume_link_token(first_token, 10, FIXED_NOW) is True

    second = _create_profile(env, username="admin2").json()
    token = _issue(env, second["id"]).json()["token"]
    env.gateway.sent.clear()
    env.post(text=f"/start {token}", user=10, chat=100)
    assert env.gateway.sent == [(100, env.settings.link_failed_reply)]
    assert env.repo.link_tokens[hash_token(token)].used_at is None
    assert env.repo.profiles[second["id"]].telegram_user_id is None


# --- R8: carrera de consumos -------------------------------------------------------------


def test_two_concurrent_consumptions_only_one_wins(env):
    """R8: dos consumos simultáneos del mismo token → un solo vínculo."""
    profile, token = _setup_link(env)
    token_hash = hash_token(token)
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def worker(telegram_user_id: int) -> None:
        barrier.wait(timeout=5)
        results.append(
            env.repo.consume_link_token(token_hash, telegram_user_id, FIXED_NOW)
        )

    threads = [threading.Thread(target=worker, args=(user,)) for user in (10, 11)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == [False, True]
    assert env.repo.profiles[profile["id"]].telegram_user_id in (10, 11)


def test_postgres_consume_link_token_is_atomic_single_statement():
    """R8: el SQL de Postgres consume el token solo si `used_at IS NULL`."""
    statements: list[str] = []

    class Cursor:
        def execute(self, sql, params=()):
            statements.append(sql)

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    repo = PostgresRepository(
        "postgresql://x", connect=lambda: Conn(), new_id=lambda: "p1"
    )
    assert repo.consume_link_token("hash", 10, FIXED_NOW) is False

    consumed = [sql for sql in statements if "UPDATE link_tokens" in sql]
    assert len(consumed) == 1
    assert "used_at IS NULL" in consumed[0]
    assert "expires_at >" in consumed[0]
    assert "UPDATE profiles SET telegram_user_id" in consumed[0]
