"""Comando local para crear el primer administrador de una instalación vacía."""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone
from typing import Callable, NoReturn, TextIO

from .accounts import USERNAME_PATTERN, hash_password
from .adapters.repository import PostgresRepository, Repository
from .config import Settings
from .domain import UsernameTaken

EXIT_OK, EXIT_ADMIN_EXISTS, EXIT_INVALID = 0, 1, 2

MSG_USAGE = "Uso: python -m orchestrator.bootstrap_admin --username <nombre>"
MSG_ADMIN_EXISTS = "Ya existe al menos un administrador; no se creó ningún perfil."
MSG_INVALID_USERNAME = "El nombre de usuario no es válido."
MSG_PASSWORD_READ_FAILED = "No se pudo leer la contraseña."
MSG_PASSWORD_SHORT = "La contraseña no cumple la longitud mínima."
MSG_PASSWORD_MISMATCH = "Las contraseñas no coinciden."
MSG_USERNAME_TAKEN = "El nombre de usuario ya existe; no se modificó ningún perfil."
MSG_DATABASE_URL_MISSING = "DATABASE_URL no está configurada; no se intentó conectar."
MSG_REPOSITORY_ERROR = "Error al acceder a la base de datos ({name})."


class _BootstrapParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # No se imprime `message`: puede contener el valor de una opción
        # desconocida como `--password` (R5).
        raise SystemExit(EXIT_INVALID)


def _build_parser() -> argparse.ArgumentParser:
    parser = _BootstrapParser(prog="python -m orchestrator.bootstrap_admin")
    parser.add_argument("--username", required=True)
    return parser


def _fail(err: TextIO, message: str) -> int:
    print(message, file=err)
    return EXIT_INVALID


def run(
    argv: list[str],
    *,
    settings: Settings,
    repository: Repository | None = None,
    prompt_password: Callable[[str], str] = getpass.getpass,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_INVALID
        if code == EXIT_INVALID:
            print(MSG_USAGE, file=err)
        return code

    username = args.username.lower()
    if not USERNAME_PATTERN.fullmatch(username):
        return _fail(err, MSG_INVALID_USERNAME)

    if repository is None:
        if not settings.database_url:
            return _fail(err, MSG_DATABASE_URL_MISSING)
        repository = PostgresRepository(settings.database_url)

    try:
        profiles = repository.list_profiles()
    except Exception as exc:
        return _fail(err, MSG_REPOSITORY_ERROR.format(name=type(exc).__name__))

    if any(profile.role == "admin" for profile in profiles):
        print(MSG_ADMIN_EXISTS, file=err)
        return EXIT_ADMIN_EXISTS

    try:
        password = prompt_password("Contraseña: ")
        confirmation = prompt_password("Repite la contraseña: ")
    except (EOFError, KeyboardInterrupt):
        return _fail(err, MSG_PASSWORD_READ_FAILED)
    if len(password) < settings.profile_password_min_length:
        return _fail(err, MSG_PASSWORD_SHORT)
    if password != confirmation:
        return _fail(err, MSG_PASSWORD_MISMATCH)

    password_hash = hash_password(password, settings.password_hash_iterations)
    try:
        profile = repository.create_profile(username, "admin", password_hash, clock())
    except UsernameTaken:
        return _fail(err, MSG_USERNAME_TAKEN)
    except Exception as exc:
        return _fail(err, MSG_REPOSITORY_ERROR.format(name=type(exc).__name__))

    print(f"Administrador creado: id={profile.id} username={profile.username}", file=out)
    return EXIT_OK


def main() -> None:
    sys.exit(run(sys.argv[1:], settings=Settings()))


if __name__ == "__main__":
    main()
