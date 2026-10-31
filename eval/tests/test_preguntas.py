"""R1-R6: preguntas y manual de ejemplo."""
import json
from pathlib import Path

import pytest

from scoring import load_questions, normalize

EVAL_DIR = Path(__file__).resolve().parent.parent
PREGUNTAS = EVAL_DIR / "preguntas.json"
MANUAL_DIR = EVAL_DIR / "manual_ejemplo"


def test_r1_r2_r3_conteos_e_ids_unicos():
    qs = load_questions(PREGUNTAS)
    assert len(qs) >= 15
    assert len({q.id for q in qs}) == len(qs)
    assert sum(q.tipo == "responde" for q in qs) >= 10
    assert sum(q.tipo == "no_responde" for q in qs) >= 5
    assert all(q.fragmento_esperado for q in qs if q.tipo == "responde")


def test_r4_manual_existe_y_es_texto():
    files = [p for p in MANUAL_DIR.iterdir() if p.suffix in {".md", ".txt"}]
    assert files
    assert all(p.read_text(encoding="utf-8").strip() for p in files)


def test_r5_fragmento_esperado_en_manual():
    manual = normalize(
        " ".join(p.read_text(encoding="utf-8") for p in MANUAL_DIR.iterdir() if p.suffix in {".md", ".txt"})
    )
    for q in load_questions(PREGUNTAS):
        if q.tipo == "responde":
            assert normalize(q.fragmento_esperado) in manual, q.id


def _write(tmp_path, preguntas):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"preguntas": preguntas}), encoding="utf-8")
    return p


def test_r6_campo_ausente(tmp_path):
    p = _write(tmp_path, [{"id": "a", "tipo": "no_responde"}])
    with pytest.raises(ValueError, match="'a'"):
        load_questions(p)


def test_r6_campo_ausente_sin_id_indica_posicion(tmp_path):
    p = _write(tmp_path, [{"pregunta": "x", "tipo": "no_responde"}])
    with pytest.raises(ValueError, match="posición 0"):
        load_questions(p)


def test_r6_id_repetido(tmp_path):
    q = {"id": "a", "pregunta": "x", "tipo": "no_responde"}
    with pytest.raises(ValueError, match="repetido"):
        load_questions(_write(tmp_path, [q, q]))


def test_r6_tipo_desconocido(tmp_path):
    q = {"id": "a", "pregunta": "x", "tipo": "otro"}
    with pytest.raises(ValueError, match="tipo desconocido"):
        load_questions(_write(tmp_path, [q]))


def test_r6_responde_sin_fragmento(tmp_path):
    q = {"id": "a", "pregunta": "x", "tipo": "responde"}
    with pytest.raises(ValueError, match="fragmento_esperado"):
        load_questions(_write(tmp_path, [q]))
