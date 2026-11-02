"""R6: comparación de dos endpoints con el mismo corpus, preguntas y parámetros."""
import json
from datetime import date

import httpx
import pytest

import run_eval

TOKEN = "tok-comparacion"
DAY = date(2026, 5, 6)

RESP = {
    "id": "r1",
    "pregunta": "¿Horario?",
    "tipo": "responde",
    "fragmento_esperado": "de 9 a 18",
}
NO = {"id": "n1", "pregunta": "¿Capital?", "tipo": "no_responde"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", TOKEN)
    monkeypatch.delenv("RAG_TOP_K", raising=False)
    monkeypatch.delenv("RAG_SIMILARITY_THRESHOLD", raising=False)


def qfile(tmp_path, preguntas):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"preguntas": preguntas}), encoding="utf-8")
    return str(path)


def make_client(handler):
    calls = []

    def wrapped(request):
        calls.append((request.url.host, json.loads(request.content)))
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), calls


def comparison_handler(request):
    if request.url.host == "left":
        if json.loads(request.content)["query"] == "¿Horario?":
            return httpx.Response(
                200,
                json=[
                    {
                        "chunk_id": "c",
                        "manual": "m",
                        "text": "Abre de 9 a 18",
                        "score": 0.9,
                    }
                ],
            )
        # Para la pregunta no_responde el endpoint izquierdo devuelve un
        # resultado: el informe debe contar una respuesta inventada.
        return httpx.Response(
            200,
            json=[{"chunk_id": "n", "manual": "m", "text": "Canberra", "score": 0.8}],
        )
    return httpx.Response(200, json=[])


def run(tmp_path, client, extra=()):
    return run_eval.main(
        [
            "--url",
            "http://left/",
            "--comparar-url",
            "http://right/",
            "--preguntas",
            qfile(tmp_path, [RESP, NO]),
            *extra,
        ],
        client=client,
        today=DAY,
        out_dir=tmp_path,
    )


def test_r6_comparison_uses_same_questions_and_parameters(tmp_path):
    """R6: ambos endpoints reciben las mismas preguntas y el mismo top_k."""
    client, calls = make_client(comparison_handler)

    assert run(tmp_path, client, ["--top-k", "7"]) == 0

    assert len(calls) == 4
    assert {host for host, _ in calls} == {"left", "right"}
    assert all(body["top_k"] == 7 for _, body in calls)
    assert [body["query"] for _, body in calls] == [
        "¿Horario?",
        "¿Capital?",
        "¿Horario?",
        "¿Capital?",
    ]


def test_r6_report_contains_comparable_metrics(tmp_path):
    """R6: el informe muestra recuperación, rechazos y resultados no_responde."""
    client, _ = make_client(comparison_handler)

    run(tmp_path, client)

    report = (tmp_path / "comparacion_2026-05-06.md").read_text(encoding="utf-8")
    assert "http://left" in report and "http://right" in report
    assert "Aciertos de recuperación | 1/1 (100%) | 0/1 (0%)" in report
    assert "Rechazos correctos | 0/1 (0%) | 1/1 (100%)" in report
    assert "Resultados en preguntas no_responde | 1 | 0" in report


def test_r6_report_records_the_shared_semantic_threshold(tmp_path, monkeypatch):
    """R6: el mismo umbral semántico queda registrado en la comparación."""
    monkeypatch.setenv("RAG_SIMILARITY_THRESHOLD", "0.42")
    client, _ = make_client(comparison_handler)

    run(tmp_path, client)

    report = (tmp_path / "comparacion_2026-05-06.md").read_text(encoding="utf-8")
    assert "Umbral semántico: 0.42" in report


def test_r6_comparison_is_only_for_rag(tmp_path):
    """R6: la comparación de recuperación exige el modo rag y no hace peticiones."""
    client, calls = make_client(comparison_handler)

    code = run_eval.main(
        [
            "--url",
            "http://left",
            "--comparar-url",
            "http://right",
            "--modo",
            "orquestador",
            "--preguntas",
            qfile(tmp_path, [RESP, NO]),
        ],
        client=client,
        today=DAY,
        out_dir=tmp_path,
    )

    assert code == 2
    assert calls == []


def test_r6_comparison_returns_error_if_an_endpoint_fails(tmp_path):
    """R6: un fallo HTTP de una ejecución se refleja en el código de salida."""
    def handler(request):
        if request.url.host == "right":
            return httpx.Response(500)
        return comparison_handler(request)

    client, _ = make_client(handler)

    assert run(tmp_path, client) != 0
    report = (tmp_path / "comparacion_2026-05-06.md").read_text(encoding="utf-8")
    assert "HTTP 500" in report


def test_r6_token_never_appears_in_the_comparison_report(tmp_path, capsys):
    """R6: el token de servicio no se filtra en el informe ni en la consola."""
    client, _ = make_client(comparison_handler)

    run(tmp_path, client)

    report = (tmp_path / "comparacion_2026-05-06.md").read_text(encoding="utf-8")
    output = capsys.readouterr()
    assert TOKEN not in report
    assert TOKEN not in output.out + output.err
