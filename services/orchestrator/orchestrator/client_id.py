"""ID público de cliente: generación y normalización sin datos personales (#73)."""
from __future__ import annotations

import re
import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_LENGTH = 8
ID_PATTERN = re.compile(r"^[23456789ABCDEFGHJKMNPQRSTVWXYZ]{4}-?[23456789ABCDEFGHJKMNPQRSTVWXYZ]{4}$")


class PublicIdGenerationError(RuntimeError):
    """No se pudo asignar un ID único tras agotar los reintentos."""


class PublicIdTaken(Exception):
    """El ID generado ya existe; el llamador debe reintentar con otro."""


def generate_public_id() -> str:
    """R1, R2: ocho caracteres del alfabeto sin ambigüedad, en formato `XXXX-XXXX`."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(ID_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_public_id(raw: str) -> str | None:
    """R21, R22: mayúsculas sin espacios ni guiones; None si el formato no es válido."""
    compact = "".join((raw or "").split()).replace("-", "").upper()
    if len(compact) != ID_LENGTH or any(char not in ALPHABET for char in compact):
        return None
    return f"{compact[:4]}-{compact[4:]}"
