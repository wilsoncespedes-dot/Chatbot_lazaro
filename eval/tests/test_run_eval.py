"""R16-R28, R32, R33: capa de red con httpx.MockTransport (sin red real)."""
import json
from datetime import date

import httpx
import pytest

import run_eval

TOKEN = "tok-secreto-123"
REFUSAL = "No sé. Te paso con un asesor."
DAY = date(2026, 3, 4)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", TOKEN)
    monkeypatch.delenv("RAG_TOP_K", raising=False)
    monkeypatch.setenv("NO_ANSWER_REPLY", REFUSAL)


def make_client(handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), calls


def qfile(tmp_path, preguntas, name="q.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"preguntas": preguntas}), encoding="utf-8")
    return str(p)


RESP = {"id": "r1", "pregunta": "¿Horario?", "tipo": "responde", "fragmento_esperado": "de 9 a 18"}
NO = {"id": "n1", "pregunta": "¿Capital?", "tipo": "no_responde"}


def rag_handler(request):
    body = json.loads(request.content)
    if body["query"] == "¿Horario?":
        return httpx.Response(200, json=[{"chunk_id": "c", "manual": "m", "text": "Abre de 9 a 18", "score": 0.9}])
    return httpx.Response(200, json=[])


def run(tmp_path, client, extra, preguntas=(RESP, NO), sink=None):
    argv = ["--url", "http://svc/", "--preguntas", qfile(tmp_path, list(preguntas)), *extra]
    return run_eval.main(argv, client=client, sink=sink, today=DAY, out_dir=tmp_path)


def test_r16_r25_search_cuerpo_y_encabezado_r20_informe(tmp_path, capsys):
    client, calls = make_client(rag_handler)
    assert run(tmp_path, client, ["--top-k", "7"]) == 0
    assert str(calls[0].url) == "http://svc/search"
    assert json.loads(calls[0].content) == {"query": "¿Horario?", "top_k": 7}
    assert calls[0].headers["X-Service-Token"] == TOKEN
    informe = (tmp_path / "resultados_2026-03-04.md").read_text(encoding="utf-8")
    assert "http://svc" in informe and "rag" in informe and "Ninguno" in informe
    # R24
    assert TOKEN not in informe
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err


def test_r16_top_k_por_defecto_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_TOP_K", "3")
    client, calls = make_client(rag_handler)
    run(tmp_path, client, [])
    assert json.loads(calls[0].content)["top_k"] == 3


def test_r16_top_k_por_defecto_5(tmp_path):
    client, calls = make_client(rag_handler)
    run(tmp_path, client, [])
    assert json.loads(calls[0].content)["top_k"] == 5


class FakeSink:
    def __init__(self, replies):
        self.replies = replies
        self.waits = []

    def wait_reply(self, chat_id, wait):
        self.waits.append((chat_id, wait))
        return self.replies.pop(0)


def test_r17_r25_r26_orquestador(tmp_path):
    client, calls = make_client(lambda r: httpx.Response(202, json={"status": "accepted"}))
    sink = FakeSink(["De 9 a 18", REFUSAL])
    code = run(tmp_path, client, ["--modo", "orquestador", "--espera", "2"], sink=sink)
    assert code == 0
    assert str(calls[0].url) == "http://svc/messages"
    assert calls[0].headers["X-Service-Token"] == TOKEN
    body = json.loads(calls[0].content)
    assert body["text"] == "¿Horario?"
    ids = {json.loads(c.content)["chat_id"] for c in calls}
    assert len(ids) == 2  # chat_id único por pregunta
    assert [w[1] for w in sink.waits] == [2.0, 2.0]


def test_r18_r28_sin_respuesta_continua(tmp_path):
    client, calls = make_client(lambda r: httpx.Response(202, json={}))
    sink = FakeSink([None, REFUSAL])
    code = run(tmp_path, client, ["--modo", "orquestador"], sink=sink)
    assert code == 0  # sin_respuesta no es error de red
    assert len(calls) == 2
    informe = (tmp_path / "resultados_2026-03-04.md").read_text(encoding="utf-8")
    assert "sin_respuesta" in informe


@pytest.mark.parametrize("status", [401, 500])
def test_r19_r27_r28_error_http_salida_distinta_de_cero_y_continua(tmp_path, status):
    client, calls = make_client(lambda r: httpx.Response(status))
    assert run(tmp_path, client, []) != 0
    assert len(calls) == 2
    informe = (tmp_path / "resultados_2026-03-04.md").read_text(encoding="utf-8")
    assert f"HTTP {status}" in informe


def test_r19_error_de_conexion(tmp_path):
    def boom(request):
        raise httpx.ConnectError("no")

    client, _ = make_client(boom)
    assert run(tmp_path, client, []) != 0
    assert "ConnectError" in (tmp_path / "resultados_2026-03-04.md").read_text(encoding="utf-8")


def test_r21_preguntas_alternas_repetible(tmp_path):
    client, calls = make_client(rag_handler)
    a = qfile(tmp_path, [RESP], "a.json")
    b = qfile(tmp_path, [NO], "b.json")
    run_eval.main(["--url", "http://svc", "--preguntas", a, "--preguntas", b],
                  client=client, today=DAY, out_dir=tmp_path)
    assert len(calls) == 2


def test_r22_umbral_minimo(tmp_path):
    def vacio(request):
        return httpx.Response(200, json=[])

    client, _ = make_client(vacio)
    assert run(tmp_path, client, ["--umbral-minimo-aciertos", "0.5"]) != 0
    client, _ = make_client(rag_handler)
    assert run(tmp_path, client, ["--umbral-minimo-aciertos", "0.5"]) == 0


def test_r23_sin_token_no_envia_nada(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SERVICE_TOKEN")
    client, calls = make_client(rag_handler)
    assert run(tmp_path, client, []) != 0
    assert calls == []
    assert "SERVICE_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize("k", ["0", "21", "-1"])
def test_r32_top_k_fuera_de_rango(tmp_path, k):
    client, calls = make_client(rag_handler)
    assert run(tmp_path, client, ["--top-k", k]) != 0
    assert calls == []


@pytest.mark.parametrize("u", ["-0.1", "1.5"])
def test_r33_umbral_fuera_de_rango(tmp_path, u):
    client, calls = make_client(rag_handler)
    assert run(tmp_path, client, ["--umbral-minimo-aciertos", u]) != 0
    assert calls == []


def test_reply_sink_real_captura_send():
    sink = run_eval.ReplySink(0)
    port = sink._server.server_address[1]
    sink.start()
    try:
        r = httpx.post(f"http://127.0.0.1:{port}/send", json={"chat_id": 5, "text": "hola"})
        assert r.status_code == 200
        assert sink.wait_reply(5, 1) == "hola"
        assert sink.wait_reply(6, 0.05) is None
    finally:
        sink.stop()
