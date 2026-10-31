"""R7-R15, R18, R19, R29-R31: puntuación pura."""
import ast
from datetime import date
from pathlib import Path

from scoring import Observation, Question, render_report, score, summarize

REFUSAL = "No sé. Te paso con un asesor."
RESP = Question("r", "¿Horario?", "responde", "de 9:00 a 18:00", "c1")
NO = Question("n", "¿Capital?", "no_responde")


def sc(q, obs, mode="rag"):
    return score(q, obs, mode=mode, refusal_text=REFUSAL)


def res(text, cid="x"):
    return {"chunk_id": cid, "text": text, "manual": "m", "score": 0.9}


def test_r8_acierto_por_fragmento_normalizado():
    obs = Observation(results=[res("Atiende  DE 9:00\na 18:00 h")])
    assert sc(RESP, obs).outcome == "acierto_recuperacion"


def test_r8_acierto_por_chunk_id():
    obs = Observation(results=[res("otra cosa", "c1")])
    assert sc(RESP, obs).outcome == "acierto_recuperacion"


def test_r9_fallo_lista_vacia_y_sin_fragmento():
    assert sc(RESP, Observation(results=[])).outcome == "fallo_recuperacion"
    assert sc(RESP, Observation(results=[res("nada")])).outcome == "fallo_recuperacion"


def test_r10_rechazo_correcto_rag_y_orquestador():
    assert sc(NO, Observation(results=[])).outcome == "rechazo_correcto"
    assert sc(NO, Observation(reply=REFUSAL), "orquestador").outcome == "rechazo_correcto"


def test_r11_respuesta_inventada():
    assert sc(NO, Observation(results=[res("algo")])).outcome == "respuesta_inventada"
    assert sc(NO, Observation(reply="Canberra"), "orquestador").outcome == "respuesta_inventada"


def test_r12_rechazo_indebido():
    assert sc(RESP, Observation(reply=REFUSAL), "orquestador").outcome == "rechazo_indebido"


def test_r29_orquestador_responde_no_rechazo_es_acierto():
    assert sc(RESP, Observation(reply="De 9 a 18"), "orquestador").outcome == "acierto_recuperacion"


def test_r18_sin_respuesta():
    assert sc(RESP, Observation(timed_out=True), "orquestador").outcome == "sin_respuesta"
    assert sc(NO, Observation(timed_out=True), "orquestador").outcome == "sin_respuesta"


def test_r19_error():
    s = sc(RESP, Observation(error="HTTP 401"))
    assert (s.outcome, s.detail) == ("error", "HTTP 401")


def _mix():
    return [
        sc(RESP, Observation(results=[res("de 9:00 a 18:00")])),
        sc(RESP, Observation(error="HTTP 500")),
        sc(RESP, Observation(reply=REFUSAL), "orquestador"),
        sc(NO, Observation(results=[])),
        sc(NO, Observation(results=[res("x")])),
        sc(NO, Observation(timed_out=True)),
    ]


def test_r13_r30_r31_resumen():
    s = summarize(_mix())
    assert s.total == 6
    assert s.recuperacion == (1, 3)  # denominador incluye error y rechazo_indebido
    assert s.rechazos == (1, 3)
    assert s.inventadas == 1
    assert {f.outcome for f in s.fallos} == {
        "error", "rechazo_indebido", "respuesta_inventada", "sin_respuesta"
    }
    assert s.tasa_recuperacion == 1 / 3


def test_r14_proporcion_none_sin_preguntas_de_un_tipo():
    s = summarize([sc(NO, Observation(results=[]))])
    assert s.tasa_recuperacion is None
    assert s.tasa_rechazo == 1.0
    assert summarize([]).tasa_rechazo is None


def test_r15_informe_con_fallos_y_ninguno():
    texto = render_report(summarize(_mix()), url="http://x", mode="rag", date=date(2026, 1, 2))
    for frag in ("Total de preguntas: 6", "Aciertos de recuperación: 1/3", "Rechazos correctos: 1/3",
                 "Respuestas inventadas detectadas: 1", "## Fallos", "http://x", "rag", "2026-01-02"):
        assert frag in texto
    assert "[error]" in texto
    ok = render_report(summarize([sc(NO, Observation(results=[]))]), url="u", mode="rag", date=date(2026, 1, 2))
    assert "Ninguno" in ok


def test_r7_scoring_sin_red_ni_entorno():
    src = (Path(__file__).resolve().parent.parent / "scoring.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    prohibidos = {"httpx", "requests", "urllib", "socket", "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & prohibidos
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in prohibidos
    assert "environ" not in src and "getenv" not in src
