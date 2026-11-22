"""R36, R37 (#65): el núcleo del orquestador no decide por nombre de canal."""
from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "orchestrator"
CHANNEL_NAMES = {"telegram", "whatsapp"}
# design.md §4: únicos importadores permitidos de LEGACY_CHANNEL.
LEGACY_IMPORTERS = {
    "legacy.py",
    "main.py",
    "queue.py",
    "domain.py",
    "adapters/repository.py",
    "adapters/outbox.py",
    "adapters/gateway.py",
}


def _modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path.relative_to(PACKAGE).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _channel_literals(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "".join(node.value.split()).lower() in CHANNEL_NAMES
    ]


def _imports_legacy_channel(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "legacy":
            if any(alias.name == "LEGACY_CHANNEL" for alias in node.names):
                return True
    return False


def test_scanner_detects_channel_literals():
    """El detector encuentra literales exactos, también en f-strings y comparaciones."""
    tree = ast.parse('x == "telegram"\ny = f"{a}" + "WhatsApp"\nz = "whatsapp_templates"\n')
    assert _channel_literals(tree) == [1, 2]


def test_channel_name_literals_live_only_in_legacy_module():
    """R36: los literales `telegram`/`whatsapp` solo aparecen en legacy.py."""
    offenders = {
        name: lines
        for name, tree in _modules()
        if name != "legacy.py" and (lines := _channel_literals(tree))
    }
    assert offenders == {}


def test_legacy_channel_is_imported_only_by_the_documented_layer():
    """R37: LEGACY_CHANNEL solo se importa desde la capa legacy documentada."""
    importers = {name for name, tree in _modules() if _imports_legacy_channel(tree)}
    assert importers <= LEGACY_IMPORTERS, importers - LEGACY_IMPORTERS
    assert "domain.py" in importers
