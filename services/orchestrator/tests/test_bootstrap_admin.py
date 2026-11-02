"""Tests del comando local que crea el primer administrador (feature #23)."""
from __future__ import annotations

import getpass
import inspect
import logging
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO

import pytest

from orchestrator import bootstrap_admin
from orchestrator.accounts import hash_password, verify_password
from orchestrator.adapters.repository import FakeRepository
from orchestrator.bootstrap_admin import (
    EXIT_ADMIN_EXISTS,
    EXIT_INVALID,
    EXIT_OK,
    MSG_ADMIN_EXISTS,
    MSG_INVALID_USERNAME,
    MSG_PASSWORD_MISMATCH,
    MSG_PASSWORD_SHORT,
    MSG_USERNAME_TAKEN,
    run,
)
from orchestrator.config import Settings

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD = "clave-segura-123"
HASH_ITERATIONS = 100_000


class FakePrompt:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql://usuario:clave@localhost/pruebas",
        "password_hash_iterations": HASH_ITERATIONS,
        "profile_password_min_length": 12,
    }
    values.update(overrides)
    return Settings(**values)


def _run(
    repo,
    argv: list[str] | None = None,
    answers: list[str] | None = None,
    settings: Settings | None = None,
):
    out, err = StringIO(), StringIO()
    prompt = FakePrompt([PASSWORD, PASSWORD] if answers is None else answers)
    code = run(
        ["--username", "admin1"] if argv is None else argv,
        settings=settings or _settings(),
        repository=repo,
        prompt_password=prompt,
        out=out,
        err=err,
        clock=lambda: FIXED_NOW,
    )
    return code, out.getvalue(), err.getvalue(), prompt


# --- R1, R2: creación del primer administrador -------------------------------------------


def test_bootstrap_creates_single_admin_with_hashed_password():
    """R1, R2: instalación vacía → un admin con hash PBKDF2 verificable y código 0."""
    repo = FakeRepository()
    code, out, err, prompt = _run(repo, argv=["--username", "Admin.One"])

    assert code == EXIT_OK
    assert len(repo.profiles) == 1
    stored = next(iter(repo.profiles.values()))
    assert stored.username == "admin.one"
    assert stored.role == "admin"
    assert stored.password_hash.startswith(f"pbkdf2_sha256${HASH_ITERATIONS}$")
    assert verify_password(PASSWORD, stored.password_hash) is True
    assert stored.password_hash != PASSWORD
    assert "admin.one" in out and stored.id in out
    assert err == ""
    assert len(prompt.prompts) == 2


# --- R3: lectura de la contraseña sin eco ------------------------------------------------


def test_password_is_read_twice_with_getpass_by_default():
    """R3: se piden dos contraseñas y el prompt por defecto es getpass.getpass."""
    repo = FakeRepository()
    _, _, _, prompt = _run(repo)

    assert prompt.prompts == ["Contraseña: ", "Repite la contraseña: "]
    assert inspect.signature(run).parameters["prompt_password"].default is getpass.getpass


# --- R4: contraseña fuera de la línea de órdenes y del entorno ---------------------------


def test_password_option_is_rejected_without_creating_or_leaking():
    """R4: `--password` → código 2, sin perfiles y sin eco de la clave."""
    repo = FakeRepository()
    secret = "clave-por-argumento-999"
    code, out, err, prompt = _run(repo, argv=["--username", "admin1", "--password", secret])

    assert code == EXIT_INVALID
    assert repo.profiles == {}
    assert prompt.prompts == []
    assert secret not in out + err


def test_environment_variable_is_never_used_as_password(monkeypatch):
    """R4: una variable de entorno con una clave no sustituye lo que se pide por consola."""
    monkeypatch.setenv("ADMIN_PASSWORD", "clave-del-entorno-000")
    repo = FakeRepository()
    prompted = "clave-desde-consola"
    code, _, _, _ = _run(repo, answers=[prompted, prompted])

    assert code == EXIT_OK
    stored = next(iter(repo.profiles.values()))
    assert verify_password(prompted, stored.password_hash) is True
    assert verify_password("clave-del-entorno-000", stored.password_hash) is False


# --- R5: la contraseña nunca se expone ---------------------------------------------------


def test_success_does_not_expose_password_in_out_err_or_logs(caplog):
    """R5: en el camino feliz ni stdout, ni stderr, ni el log contienen la clave."""
    caplog.set_level(logging.DEBUG)
    repo = FakeRepository()
    code, out, err, _ = _run(repo)

    assert code == EXIT_OK
    assert PASSWORD not in out + err + caplog.text


def test_mismatch_and_short_password_do_not_expose_password(caplog):
    """R5: los rechazos de contraseña no la escriben en ningún flujo."""
    caplog.set_level(logging.DEBUG)
    other = "otra-clave-segura-456"
    repo = FakeRepository()
    code, out, err, _ = _run(repo, answers=[PASSWORD, other])
    assert code == EXIT_INVALID
    assert PASSWORD not in out + err + caplog.text

    code, out, err, _ = _run(repo, answers=["corta", "corta"])
    assert code == EXIT_INVALID
    assert "corta" not in out + err + caplog.text


def test_repository_error_does_not_expose_password(caplog):
    """R5: un error del repositorio no filtra la clave aunque venga en su mensaje."""
    caplog.set_level(logging.DEBUG)

    class FailingRepository(FakeRepository):
        def create_profile(self, *args, **kwargs):
            raise RuntimeError(f"fallo con {PASSWORD}")

    repo = FailingRepository()
    code, out, err, _ = _run(repo)

    assert code == EXIT_INVALID
    assert "RuntimeError" in err
    assert PASSWORD not in out + err + caplog.text
    assert repo.profiles == {}


# --- R6: se niega si ya hay un administrador ---------------------------------------------


def test_existing_admin_exits_without_prompting_or_changing_data():
    """R6: con un admin previo → código 1, sin pedir clave y sin tocar el hash."""
    repo = FakeRepository()
    repo.create_profile(
        "root", "admin", hash_password("clave-original-123", HASH_ITERATIONS), FIXED_NOW
    )
    before = deepcopy(repo.profiles)

    code, out, err, prompt = _run(repo)

    assert code == EXIT_ADMIN_EXISTS
    assert prompt.prompts == []
    assert repo.profiles == before
    assert MSG_ADMIN_EXISTS in err
    assert PASSWORD not in out + err


# --- R7: entradas inválidas --------------------------------------------------------------


@pytest.mark.parametrize("username", ["ab", "con espacio", "acentué", "a" * 65, ""])
def test_invalid_username_exits_without_profiles(username):
    """R7: username fuera de patrón → código 2, sin pedir clave ni crear perfil."""
    repo = FakeRepository()
    code, _, err, prompt = _run(repo, argv=["--username", username])

    assert code == EXIT_INVALID
    assert prompt.prompts == []
    assert repo.profiles == {}
    assert MSG_INVALID_USERNAME in err


def test_short_password_exits_without_profiles():
    """R7: clave más corta que PROFILE_PASSWORD_MIN_LENGTH → código 2 sin perfil."""
    repo = FakeRepository()
    code, _, err, _ = _run(repo, answers=["corta", "corta"])

    assert code == EXIT_INVALID
    assert repo.profiles == {}
    assert MSG_PASSWORD_SHORT in err


def test_mismatched_passwords_exit_without_profiles():
    """R7: las dos entradas no coinciden → código 2 sin perfil."""
    repo = FakeRepository()
    code, _, err, _ = _run(repo, answers=[PASSWORD, "otra-clave-segura-456"])

    assert code == EXIT_INVALID
    assert repo.profiles == {}
    assert MSG_PASSWORD_MISMATCH in err


# --- R8: username ya usado ---------------------------------------------------------------


def test_username_taken_leaves_existing_profile_intact():
    """R8: username ya usado por un asesor → código 2 y perfil sin cambios."""
    repo = FakeRepository()
    original_hash = hash_password("clave-asesor-123", HASH_ITERATIONS)
    repo.create_profile("admin1", "asesor", original_hash, FIXED_NOW)
    before = deepcopy(repo.profiles)

    code, _, err, _ = _run(repo, argv=["--username", "Admin1"])

    assert code == EXIT_INVALID
    assert repo.profiles == before
    stored = next(iter(repo.profiles.values()))
    assert stored.role == "asesor"
    assert stored.password_hash == original_hash
    assert MSG_USERNAME_TAKEN in err


# --- R9: DATABASE_URL vacía --------------------------------------------------------------


def test_missing_database_url_exits_without_connecting(monkeypatch):
    """R9: sin DATABASE_URL → código 2 sin construir el repositorio de Postgres."""
    def boom(*args, **kwargs):
        raise AssertionError("no debe construirse PostgresRepository")

    monkeypatch.setattr(bootstrap_admin, "PostgresRepository", boom)
    prompt = FakePrompt([PASSWORD, PASSWORD])
    err = StringIO()

    code = run(
        ["--username", "admin1"],
        settings=_settings(database_url=""),
        repository=None,
        prompt_password=prompt,
        out=StringIO(),
        err=err,
        clock=lambda: FIXED_NOW,
    )

    assert code == EXIT_INVALID
    assert prompt.prompts == []
    assert err.getvalue()


# --- R10: sin endpoints HTTP de bootstrap ------------------------------------------------


def test_app_exposes_no_bootstrap_route(env):
    """R10: `create_app` no registra ninguna ruta cuyo path contenga `bootstrap`."""
    paths = [getattr(route, "path", "") for route in env.client.app.routes]
    assert all("bootstrap" not in path for path in paths)
