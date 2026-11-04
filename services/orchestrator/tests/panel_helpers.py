"""Helpers del panel multicanal (#41) movidos a `conftest.py`.

Se exponen mediante la fixture `panel` para que los tests no dependan de
importar módulos hermanos de `tests/` (pytest usa `--import-mode=importlib`).
"""
