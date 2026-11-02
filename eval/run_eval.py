"""Evaluación del chatbot: ejecuta preguntas contra RAG u orquestador y puntúa.

Antes de evaluar hay que cargar el manual de ejemplo en RAG, por ejemplo:

    python scripts/cargar_manual.py eval/manual_ejemplo/manual_ejemplo.md

Uso:
    python eval/run_eval.py --url http://localhost:8001 --modo rag
    python eval/run_eval.py --url http://localhost:8000 --modo orquestador
    python eval/run_eval.py --url http://rag-a:8000 --comparar-url http://rag-b:8000

La comparación escribe `eval/comparacion_<fecha>.md` y usa las mismas
preguntas, `top_k` y `RAG_SIMILARITY_THRESHOLD` para ambos endpoints.

En modo orquestador se levanta un receptor local (EVAL_SINK_PORT, 8099 por
defecto) que hace de gateway; el orquestador debe tener TELEGRAM_GATEWAY_URL
apuntando a él. Es una ejecución manual, no de CI.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from scoring import (  # noqa: E402
    Observation,
    Question,
    Scored,
    load_questions,
    render_comparison,
    render_report,
    score,
    summarize,
)

DEFAULT_REFUSAL = "No encontré información sobre eso en los manuales. Te paso con un asesor."
MAX_TOP_K = 20
BASE_CHAT_ID = 900_000_000


def _headers(token: str) -> dict[str, str]:
    return {"X-Service-Token": token}


def query_rag(client, url: str, token: str, question: Question, top_k: int) -> Observation:
    try:
        resp = client.post(
            f"{url}/search",
            json={"query": question.pregunta, "top_k": top_k},
            headers=_headers(token),
        )
    except httpx.HTTPError as exc:
        return Observation(error=f"{type(exc).__name__}")
    if resp.status_code != 200:
        return Observation(error=f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        return Observation(error="respuesta no es JSON")
    if not isinstance(data, list):
        return Observation(error="respuesta inesperada")
    return Observation(results=data)


class ReplySink:
    """Receptor local que hace de gateway: captura POST /send {chat_id, text}."""

    def __init__(self, port: int, host: str = "127.0.0.1") -> None:
        self._queues: dict[int, queue.Queue[str]] = {}
        self._lock = threading.Lock()
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if self.path != "/send":
                        self.send_response(404)
                        self.end_headers()
                        return
                    sink.put(int(body["chat_id"]), str(body["text"]))
                except (ValueError, KeyError, TypeError):
                    self.send_response(400)
                    self.end_headers()
                    return
                payload = b'{"sent": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:  # silencioso
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _queue(self, chat_id: int) -> queue.Queue[str]:
        with self._lock:
            return self._queues.setdefault(chat_id, queue.Queue())

    def put(self, chat_id: int, text: str) -> None:
        self._queue(chat_id).put(text)

    def wait_reply(self, chat_id: int, wait: float) -> str | None:
        try:
            return self._queue(chat_id).get(timeout=wait)
        except queue.Empty:
            return None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def query_orchestrator(
    client, url: str, token: str, question: Question, sink, wait: float, chat_id: int = BASE_CHAT_ID
) -> Observation:
    from lazaro_contracts import MessageRequest

    body = MessageRequest(
        update_id=chat_id,
        telegram_user_id=chat_id,
        chat_id=chat_id,
        text=question.pregunta,
        received_at=datetime.now(timezone.utc),
    )
    try:
        resp = client.post(
            f"{url}/messages",
            content=body.model_dump_json(),
            headers={**_headers(token), "Content-Type": "application/json"},
        )
    except httpx.HTTPError as exc:
        return Observation(error=f"{type(exc).__name__}")
    if resp.status_code >= 300:
        return Observation(error=f"HTTP {resp.status_code}")
    reply = sink.wait_reply(chat_id, wait)
    if reply is None:
        return Observation(timed_out=True)
    return Observation(reply=reply)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Evalúa el chatbot con preguntas de ejemplo. "
        "Carga antes el manual: python scripts/cargar_manual.py eval/manual_ejemplo/manual_ejemplo.md"
    )
    p.add_argument("--url", required=True, help="URL base de RAG o del orquestador")
    p.add_argument(
        "--comparar-url",
        "--url-b",
        dest="comparar_url",
        default=None,
        help="segunda URL de RAG para comparar con el mismo corpus, preguntas y parámetros",
    )
    p.add_argument("--modo", choices=["rag", "orquestador"], default="rag")
    p.add_argument("--top-k", type=int, default=None, help="por defecto RAG_TOP_K o 5 (1 a 20)")
    p.add_argument("--espera", type=float, default=30.0, help="segundos de espera por respuesta")
    p.add_argument("--rechazo", default=None, help="texto de rechazo; por defecto NO_ANSWER_REPLY")
    p.add_argument("--preguntas", action="append", default=None, type=Path,
                   help="archivo de preguntas (repetible); sustituye a eval/preguntas.json")
    p.add_argument("--umbral-minimo-aciertos", type=float, default=None,
                   help="proporción mínima (0 a 1) de aciertos de recuperación")
    return p


def _collect(
    client,
    url: str,
    token: str,
    questions: list[Question],
    *,
    mode: str,
    top_k: int,
    sink,
    wait: float,
    refusal: str,
) -> list[Scored]:
    scored: list[Scored] = []
    for i, q in enumerate(questions):
        if mode == "rag":
            obs = query_rag(client, url, token, q, top_k)
        else:
            obs = query_orchestrator(client, url, token, q, sink, wait, BASE_CHAT_ID + i)
        scored.append(score(q, obs, mode=mode, refusal_text=refusal))
    return scored


def _comparison_threshold() -> float:
    """Umbral semántico compartido que se registra en la comparación."""
    raw = os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.75")
    try:
        threshold = float(raw)
    except ValueError as exc:
        raise ValueError("RAG_SIMILARITY_THRESHOLD no es un número") from exc
    if not -1 <= threshold <= 1:
        raise ValueError("RAG_SIMILARITY_THRESHOLD debe estar entre -1 y 1")
    return threshold


def _below_minimum(summary, umbral: float | None) -> bool:
    if umbral is None:
        return False
    rate = summary.tasa_recuperacion
    return rate is not None and rate < umbral


def main(
    argv: list[str] | None = None,
    *,
    client=None,
    sink=None,
    today: date | None = None,
    out_dir: Path | None = None,
) -> int:
    args = _build_parser().parse_args(argv)

    token = os.environ.get("SERVICE_TOKEN", "")
    if not token:
        print("Error: falta SERVICE_TOKEN en el entorno.", file=sys.stderr)
        return 2

    top_k = args.top_k
    if top_k is None:
        try:
            top_k = int(os.environ.get("RAG_TOP_K", "5"))
        except ValueError:
            top_k = -1
    if not 1 <= top_k <= MAX_TOP_K:
        print(f"Error: top-k debe estar entre 1 y {MAX_TOP_K}.", file=sys.stderr)
        return 2
    umbral = args.umbral_minimo_aciertos
    if umbral is not None and not 0 <= umbral <= 1:
        print("Error: --umbral-minimo-aciertos debe estar entre 0 y 1.", file=sys.stderr)
        return 2

    url = args.url.rstrip("/")
    comparar_url = args.comparar_url.rstrip("/") if args.comparar_url else None
    if comparar_url and args.modo != "rag":
        print("Error: --comparar-url solo se admite con --modo rag.", file=sys.stderr)
        return 2
    threshold: float | None = None
    if comparar_url:
        try:
            threshold = _comparison_threshold()
        except ValueError as exc:
            print(f"Error: {exc}.", file=sys.stderr)
            return 2

    refusal = args.rechazo or os.environ.get("NO_ANSWER_REPLY") or DEFAULT_REFUSAL
    try:
        questions: list[Question] = []
        for path in args.preguntas or [EVAL_DIR / "preguntas.json"]:
            questions.extend(load_questions(path))
    except (ValueError, OSError) as exc:
        print(f"Error en las preguntas: {exc}", file=sys.stderr)
        return 2

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=10.0)
    own_sink = False
    if args.modo == "orquestador" and sink is None:
        sink = ReplySink(int(os.environ.get("EVAL_SINK_PORT", "8099")))
        sink.start()
        own_sink = True

    left_scored: list[Scored] = []
    right_scored: list[Scored] = []
    try:
        left_scored = _collect(
            client, url, token, questions, mode=args.modo, top_k=top_k,
            sink=sink, wait=args.espera, refusal=refusal,
        )
        if comparar_url:
            right_scored = _collect(
                client, comparar_url, token, questions, mode=args.modo, top_k=top_k,
                sink=sink, wait=args.espera, refusal=refusal,
            )
    finally:
        if own_client:
            client.close()
        if own_sink:
            sink.stop()

    day = today or date.today()
    if comparar_url:
        left = summarize(left_scored)
        right = summarize(right_scored)
        report = render_comparison(
            left,
            right,
            left_url=url,
            right_url=comparar_url,
            mode=args.modo,
            top_k=top_k,
            threshold=threshold if threshold is not None else 0.75,
            date=day,
        )
        target = (out_dir or EVAL_DIR) / f"comparacion_{day.isoformat()}.md"
        target.write_text(report, encoding="utf-8")
        print(f"Comparación escrita en {target}")
        print(
            f"{url}: recuperación {left.recuperacion[0]}/{left.recuperacion[1]}, "
            f"rechazos {left.rechazos[0]}/{left.rechazos[1]}, "
            f"inventadas {left.inventadas}; "
            f"{comparar_url}: recuperación {right.recuperacion[0]}/{right.recuperacion[1]}, "
            f"rechazos {right.rechazos[0]}/{right.rechazos[1]}, "
            f"inventadas {right.inventadas}"
        )
        code = 0
        if any(s.outcome == "error" for s in left_scored + right_scored):
            code = 1
        if _below_minimum(left, umbral) or _below_minimum(right, umbral):
            code = 1
        return code

    summary = summarize(left_scored)
    report = render_report(summary, url=url, mode=args.modo, date=day)
    target = (out_dir or EVAL_DIR) / f"resultados_{day.isoformat()}.md"
    target.write_text(report, encoding="utf-8")
    print(f"Informe escrito en {target}")
    print(
        f"Recuperación {summary.recuperacion[0]}/{summary.recuperacion[1]}, "
        f"rechazos {summary.rechazos[0]}/{summary.rechazos[1]}, "
        f"inventadas {summary.inventadas}, fallos {len(summary.fallos)}"
    )

    code = 0
    if any(s.outcome == "error" for s in left_scored):
        code = 1
    if _below_minimum(summary, umbral):
        code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
