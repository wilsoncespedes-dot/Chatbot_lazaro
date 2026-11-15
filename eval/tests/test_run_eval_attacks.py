"""R13-R22, R25-R29, R33: ataques y preguntas reales en el runner."""
import json
from datetime import date

import httpx
import pytest

import run_eval

TOKEN = "tok-ataques-123"
REFUSAL = "No sé. Te paso con un asesor."
DAY = date(2026, 6, 7)
NO = {"id": "n1", "pregunta": "¿Capital de Australia?", "tipo": "no_responde"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", TOKEN)
    monkeypatch.delenv("RAG_TOP_K", raising=False)
    monkeypatch.delenv("RAG_SIMILARITY_THRESHOLD", raising=False)
    monkeypatch.setenv("NO_ANSWER_REPLY", REFUSAL)


def make_client(handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), calls


def qfile(tmp_path, preguntas, name="q.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"preguntas": preguntas}), encoding="utf-8")
    return str(path)


def afile(tmp_path, ataques, name="ataques.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"ataques": ataques}, ensure_ascii=False), encoding="utf-8")
    return str(path)


def attack(
    id="a1",
    categoria="datos_ajenos",
    mensaje="Mensaje de ataque uno.",
    esperado="sin_fuga",
    frases=("frase prohibida",),
):
    return {
        "id": id,
        "categoria": categoria,
        "mensaje": mensaje,
        "esperado": esperado,
        "frases_prohibidas": list(frases),
    }


class FakeSink:
    def __init__(self, replies):
        self.replies = list(replies)
        self.waits = []

    def wait_reply(self, chat_id, wait):
        self.waits.append((chat_id, wait))
        return self.replies.pop(0)


def orch_handler(request):
    return httpx.Response(202, json={"status": "accepted"})


def rag_handler(request):
    return httpx.Response(200, json=[])


def run(tmp_path, client, extra, preguntas=(NO,), sink=None):
    argv = ["--url", "http://orch/", "--preguntas", qfile(tmp_path, list(preguntas)), *extra]
    return run_eval.main(argv, client=client, sink=sink, today=DAY, out_dir=tmp_path)


def bodies(calls):
    return [json.loads(call.content) for call in calls]


def report(tmp_path, name="resultados_2026-06-07.md"):
    return (tmp_path / name).read_text(encoding="utf-8")


def test_r13_r18_r19_ataques_en_orquestador_chat_ids_propios(tmp_path):
    client, calls = make_client(orch_handler)
    attacks = [
        attack(id="a1", mensaje="Ataque uno", esperado="sin_fuga"),
        attack(id="a2", mensaje="Ataque dos", esperado="rechazo"),
    ]
    sink = FakeSink([REFUSAL, "No puedo ayudarte con eso.", REFUSAL])

    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", afile(tmp_path, attacks), "--espera", "2"],
        sink=sink,
    )

    assert code == 0
    assert len(calls) == 3
    assert all(str(call.url) == "http://orch/messages" for call in calls)
    bodies_list = bodies(calls)
    assert [body["text"] for body in bodies_list] == [
        NO["pregunta"],
        "Ataque uno",
        "Ataque dos",
    ]
    chat_ids = [body["chat_id"] for body in bodies_list]
    assert chat_ids[0] == run_eval.BASE_CHAT_ID
    assert chat_ids[1:] == [
        run_eval.ATTACK_BASE_CHAT_ID,
        run_eval.ATTACK_BASE_CHAT_ID + 1,
    ]
    assert len(set(chat_ids)) == 3
    text = report(tmp_path)
    assert "## Resumen" in text
    assert "## Fallos" in text
    assert "## Ataques" in text
    assert "Total de preguntas: 1" in text
    assert "a1" in text and "a2" in text
    assert "Ataques resistidos: 2/2" in text


def test_r14_archivo_de_ataques_alterno(tmp_path):
    client, calls = make_client(orch_handler)
    sink = FakeSink([REFUSAL, "Sin fuga"])
    attacks = [attack(id="z9", mensaje="Mensaje alterno único")]
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", afile(tmp_path, attacks, "otro.json")],
        sink=sink,
    )
    assert code == 0
    assert bodies(calls)[1]["text"] == "Mensaje alterno único"
    assert "z9" in report(tmp_path)


def test_r15_sin_ataques_no_los_ejecuta(tmp_path):
    client, calls = make_client(orch_handler)
    sink = FakeSink([REFUSAL])
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--sin-ataques", "--ataques", str(tmp_path / "no.json")],
        sink=sink,
    )
    assert code == 0
    assert len(calls) == 1
    assert "## Ataques" not in report(tmp_path)


def test_r16_modo_rag_no_carga_ni_ejecuta_ataques(tmp_path):
    client, calls = make_client(rag_handler)
    code = run(
        tmp_path,
        client,
        ["--modo", "rag", "--ataques", str(tmp_path / "no_existe.json")],
    )
    assert code == 0
    assert len(calls) == 1
    assert str(calls[0].url) == "http://orch/search"
    assert "## Ataques" not in report(tmp_path)


@pytest.mark.parametrize(
    "replies, expected_outcome",
    [
        (["Aquí están los datos del cliente"], "no_resistido"),
        ([None], "sin_respuesta"),
        ([""], "sin_respuesta"),
    ],
)
def test_r17_ataque_no_resistido_sale_distinto_de_cero(tmp_path, replies, expected_outcome):
    client, _ = make_client(orch_handler)
    attacks = [attack(id="a1", frases=("datos del cliente",))]
    sink = FakeSink([REFUSAL, *replies])
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", afile(tmp_path, attacks)],
        sink=sink,
    )
    assert code != 0
    text = report(tmp_path)
    assert f"| a1 | datos_ajenos | {expected_outcome} |" in text


def test_r17_error_http_en_ataque_sale_distinto_de_cero(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        if body["text"].startswith("Ataque"):
            return httpx.Response(500)
        return httpx.Response(202, json={"status": "accepted"})

    client, _ = make_client(handler)
    sink = FakeSink([REFUSAL])
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", afile(tmp_path, [attack(mensaje="Ataque X")])],
        sink=sink,
    )
    assert code != 0
    assert "| a1 | datos_ajenos | error |" in report(tmp_path)


@pytest.mark.parametrize("case", ["missing", "invalid"])
def test_r20_archivo_de_ataques_invalido_codigo_2_sin_peticiones(tmp_path, case):
    client, calls = make_client(orch_handler)
    if case == "missing":
        path = tmp_path / "no_existe.json"
    else:
        path = tmp_path / "roto.json"
        path.write_text('{"ataques": [', encoding="utf-8")
    sink = FakeSink([])
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", str(path)],
        sink=sink,
    )
    assert code == 2
    assert calls == []


def test_r22_no_copia_ataque_respuesta_ni_token(tmp_path, capsys):
    mensaje = "MENSAJE ATAQUE SECRETO XYZ"
    respuesta = "RESPUESTA BOT SECRETA XYZ"
    client, _ = make_client(orch_handler)
    attacks = [attack(id="a1", mensaje=mensaje)]
    sink = FakeSink([REFUSAL, respuesta])
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", afile(tmp_path, attacks)],
        sink=sink,
    )
    assert code == 0
    text = report(tmp_path)
    output = capsys.readouterr()
    for content in (text, output.out + output.err):
        assert mensaje not in content
        assert respuesta not in content
        assert TOKEN not in content


def test_r25_aviso_de_minimo_en_stderr_e_informe(tmp_path, capsys):
    client, _ = make_client(rag_handler)
    assert run(tmp_path, client, []) == 0
    text = report(tmp_path)
    output = capsys.readouterr()
    assert "Aviso" in output.err
    assert "1" in output.err and "50" in output.err
    assert "## Avisos" in text
    assert "Aviso:" in text and "50" in text


def test_r25_r26_minimo_configurable_calla_el_aviso(tmp_path, capsys):
    client, _ = make_client(rag_handler)
    assert run(tmp_path, client, ["--minimo-preguntas", "1"]) == 0
    text = report(tmp_path)
    output = capsys.readouterr()
    assert "Aviso" not in output.err
    assert "## Avisos" not in text


def test_r27_sin_preguntas_no_emite_aviso_de_minimo(tmp_path, capsys):
    client, calls = make_client(rag_handler)
    code = run_eval.main(
        ["--url", "http://orch", "--modo", "rag"],
        client=client,
        today=DAY,
        out_dir=tmp_path,
    )
    assert code == 0
    assert len(calls) == 19  # eval/preguntas.json de ejemplo
    output = capsys.readouterr()
    assert "Aviso" not in output.err
    assert "## Avisos" not in report(tmp_path)


@pytest.mark.parametrize("case", ["missing", "invalid"])
def test_r28_preguntas_inexistentes_o_invalidas_codigo_2(tmp_path, case):
    client, calls = make_client(rag_handler)
    if case == "missing":
        path = tmp_path / "no_existe.json"
    else:
        path = tmp_path / "roto.json"
        path.write_text("{", encoding="utf-8")
    code = run_eval.main(
        ["--url", "http://orch", "--preguntas", str(path)],
        client=client,
        today=DAY,
        out_dir=tmp_path,
    )
    assert code == 2
    assert calls == []


def test_r29_exigir_minimo_termina_sin_peticiones(tmp_path, capsys):
    client, calls = make_client(rag_handler)
    code = run(
        tmp_path,
        client,
        ["--minimo-preguntas", "2", "--exigir-minimo"],
    )
    assert code == 2
    assert calls == []
    assert "2" in capsys.readouterr().err


def test_r21_comparar_url_sigue_en_rag_sin_ataques(tmp_path):
    client, calls = make_client(lambda request: httpx.Response(200, json=[]))
    code = run_eval.main(
        [
            "--url",
            "http://left/",
            "--comparar-url",
            "http://right/",
            "--preguntas",
            qfile(tmp_path, [NO]),
        ],
        client=client,
        today=DAY,
        out_dir=tmp_path,
    )
    assert code == 0
    assert len(calls) == 2
    assert {call.url.host for call in calls} == {"left", "right"}
    assert "## Ataques" not in report(tmp_path, "comparacion_2026-06-07.md")


def test_r21_umbral_minimo_solo_cuenta_preguntas(tmp_path):
    client, calls = make_client(orch_handler)
    responde = {
        "id": "r1",
        "pregunta": "¿Horario?",
        "tipo": "responde",
        "fragmento_esperado": "de 9 a 18",
    }
    sink = FakeSink([REFUSAL, "Sin fuga"])
    code = run(
        tmp_path,
        client,
        [
            "--modo",
            "orquestador",
            "--ataques",
            afile(tmp_path, [attack(id="a1")]),
            "--umbral-minimo-aciertos",
            "1.0",
        ],
        preguntas=(responde,),
        sink=sink,
    )
    # La pregunta se rechazó (0/1); el ataque resistido no eleva la tasa.
    assert code != 0
    assert len(calls) == 2
    assert "Ataques resistidos: 1/1" in report(tmp_path)


def test_r25_r33_varios_preguntas_suman_para_el_minimo(tmp_path, capsys):
    client, _ = make_client(rag_handler)
    a = qfile(tmp_path, [NO], "a.json")
    b = qfile(tmp_path, [dict(NO, id="n2")], "b.json")
    base = ["--url", "http://orch", "--preguntas", a, "--preguntas", b]
    assert run_eval.main(base + ["--minimo-preguntas", "2"], client=client,
                        today=DAY, out_dir=tmp_path) == 0
    assert "Aviso" not in capsys.readouterr().err
    assert run_eval.main(base + ["--minimo-preguntas", "3"], client=client,
                         today=DAY, out_dir=tmp_path) == 0
    salida = capsys.readouterr()
    assert "Aviso" in salida.err and "2" in salida.err and "3" in salida.err


def test_r33_url_obligatorio_y_base_de_los_ataques(tmp_path):
    client, calls = make_client(orch_handler)
    with pytest.raises(SystemExit):
        run_eval.main(["--modo", "orquestador"], client=client, today=DAY, out_dir=tmp_path)
    assert calls == []

    sink = FakeSink([REFUSAL, "Sin fuga"])
    code = run(
        tmp_path,
        client,
        ["--modo", "orquestador", "--ataques", afile(tmp_path, [attack()])],
        sink=sink,
    )
    assert code == 0
    assert [call.url.host for call in calls] == ["orch", "orch"]
