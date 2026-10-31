"""Hace importables `scoring` y `run_eval` (eval/ no es un paquete)."""
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))
