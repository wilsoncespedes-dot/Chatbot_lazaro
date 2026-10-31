"""Hace importables los paquetes del monorepo en los tests (services/<servicio>/<servicio>/ y contracts/)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

for path in [ROOT / "contracts", ROOT, *sorted((ROOT / "services").glob("*/"))]:
    if path.is_dir() and str(path) not in sys.path:
        sys.path.insert(0, str(path))
