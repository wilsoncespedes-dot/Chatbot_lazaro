"""Migraciones SQL versionadas de la base compartida (ver `runner.py`)."""
from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent


def schema_sql() -> str:
    """Texto de todas las migraciones en orden; lo usan los tests de esquema."""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
    )


def section(title: str, filename: str = "0001_esquema_inicial.sql") -> tuple[str, ...]:
    """Sentencias (sin `;`) de una sección `-- ── <título>` de una migración.

    Permite que los tests de esquema sigan comprobando cada grupo (tablas,
    índices, migraciones aditivas) igual que cuando vivían en el código.
    """
    lines = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8").splitlines()
    header = f"-- ── {title}"
    try:
        start = next(
            i
            for i, line in enumerate(lines)
            if line.rstrip() == header or line.startswith(header + " ")
        )
    except StopIteration:
        raise KeyError(title) from None
    result: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip() or line.startswith("-- ──"):
            break
        if line.startswith("--"):
            continue  # comentario explicativo dentro de la sección
        result.append(line.rstrip().removesuffix(";"))
    return tuple(result)
