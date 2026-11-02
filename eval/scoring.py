"""Puntuación de la evaluación: lógica pura, sin red ni variables de entorno."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

Outcome = Literal[
    "acierto_recuperacion",
    "fallo_recuperacion",
    "rechazo_correcto",
    "respuesta_inventada",
    "rechazo_indebido",
    "sin_respuesta",
    "error",
]

TIPOS = ("responde", "no_responde")
FALLOS = frozenset(
    {"fallo_recuperacion", "respuesta_inventada", "rechazo_indebido", "sin_respuesta", "error"}
)


@dataclass(frozen=True)
class Question:
    id: str
    pregunta: str
    tipo: Literal["responde", "no_responde"]
    fragmento_esperado: str | None = None
    chunk_id_esperado: str | None = None


@dataclass(frozen=True)
class Observation:
    """Lo que devolvió el sistema para una pregunta."""

    results: list[dict] | None = None
    reply: str | None = None
    error: str | None = None
    timed_out: bool = False


@dataclass(frozen=True)
class Scored:
    question: Question
    outcome: Outcome
    detail: str = ""


@dataclass(frozen=True)
class Summary:
    total: int
    recuperacion: tuple[int, int]  # (aciertos, preguntas responde)
    rechazos: tuple[int, int]  # (rechazos correctos, preguntas no_responde)
    inventadas: int
    fallos: list[Scored]

    @property
    def tasa_recuperacion(self) -> float | None:
        return _ratio(*self.recuperacion)

    @property
    def tasa_rechazo(self) -> float | None:
        return _ratio(*self.rechazos)

    @property
    def resultados_no_responde(self) -> int:
        """Preguntas no_responde que devolvieron algún resultado (RAG) o respuesta."""
        return sum(1 for s in self.fallos if s.outcome == "respuesta_inventada")


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def normalize(text: str) -> str:
    """casefold + colapsa espacios (mismo criterio que la barrera de no_inventar)."""
    return " ".join(text.casefold().split())


def load_questions(path: Path) -> list[Question]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: JSON inválido: {exc}") from exc
    items = data.get("preguntas") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"{path}: se esperaba una lista de preguntas")
    questions: list[Question] = []
    seen: set[str] = set()
    for pos, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"pregunta en la posición {pos}: no es un objeto")
        raw_id = item.get("id")
        ref = f"id {raw_id!r}" if isinstance(raw_id, str) and raw_id else f"posición {pos}"
        for field in ("id", "pregunta", "tipo"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"pregunta {ref}: falta el campo obligatorio '{field}'")
        if item["id"] in seen:
            raise ValueError(f"pregunta {ref}: id repetido")
        seen.add(item["id"])
        if item["tipo"] not in TIPOS:
            raise ValueError(f"pregunta {ref}: tipo desconocido {item['tipo']!r}")
        fragmento = item.get("fragmento_esperado")
        if item["tipo"] == "responde" and not (isinstance(fragmento, str) and fragmento.strip()):
            raise ValueError(f"pregunta {ref}: falta 'fragmento_esperado'")
        chunk = item.get("chunk_id_esperado")
        questions.append(
            Question(
                id=item["id"],
                pregunta=item["pregunta"],
                tipo=item["tipo"],
                fragmento_esperado=fragmento if isinstance(fragmento, str) else None,
                chunk_id_esperado=chunk if isinstance(chunk, str) else None,
            )
        )
    return questions


def _is_refusal(reply: str, refusal_text: str) -> bool:
    return normalize(reply) == normalize(refusal_text)


def _score_rag(q: Question, results: list[dict]) -> Scored:
    if q.tipo == "no_responde":
        if not results:
            return Scored(q, "rechazo_correcto", "sin resultados")
        return Scored(q, "respuesta_inventada", f"{len(results)} resultado(s) superaron el umbral")
    if not results:
        return Scored(q, "fallo_recuperacion", "lista vacía de resultados")
    fragment = normalize(q.fragmento_esperado or "")
    for r in results:
        if fragment and fragment in normalize(str(r.get("text", ""))):
            return Scored(q, "acierto_recuperacion", f"fragmento en {r.get('chunk_id', '?')}")
        if q.chunk_id_esperado and r.get("chunk_id") == q.chunk_id_esperado:
            return Scored(q, "acierto_recuperacion", f"chunk_id {q.chunk_id_esperado}")
    return Scored(q, "fallo_recuperacion", "ningún resultado contiene el fragmento esperado")


def _score_orch(q: Question, reply: str, refusal_text: str) -> Scored:
    refused = _is_refusal(reply, refusal_text)
    if q.tipo == "no_responde":
        if refused:
            return Scored(q, "rechazo_correcto", "texto de rechazo")
        return Scored(q, "respuesta_inventada", "respondió en lugar de rechazar")
    if refused:
        return Scored(q, "rechazo_indebido", "rechazó una pregunta que el manual responde")
    return Scored(q, "acierto_recuperacion", "respuesta distinta del rechazo")


def score(
    q: Question,
    obs: Observation,
    *,
    mode: Literal["rag", "orquestador"],
    refusal_text: str,
) -> Scored:
    if obs.error:
        return Scored(q, "error", obs.error)
    if obs.timed_out:
        return Scored(q, "sin_respuesta", "tiempo de espera agotado")
    if mode == "rag":
        return _score_rag(q, obs.results or [])
    if not obs.reply or not obs.reply.strip():
        return Scored(q, "sin_respuesta", "no llegó ninguna respuesta")
    return _score_orch(q, obs.reply, refusal_text)


def summarize(scored: list[Scored]) -> Summary:
    responde = [s for s in scored if s.question.tipo == "responde"]
    no_responde = [s for s in scored if s.question.tipo == "no_responde"]
    return Summary(
        total=len(scored),
        recuperacion=(
            sum(s.outcome == "acierto_recuperacion" for s in responde),
            len(responde),
        ),
        rechazos=(
            sum(s.outcome == "rechazo_correcto" for s in no_responde),
            len(no_responde),
        ),
        inventadas=sum(s.outcome == "respuesta_inventada" for s in scored),
        fallos=[s for s in scored if s.outcome in FALLOS],
    )


def _pct(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.0%}"


def render_report(summary: Summary, *, url: str, mode: str, date: date) -> str:
    ok, n_resp = summary.recuperacion
    rc, n_no = summary.rechazos
    lines = [
        f"# Informe de evaluación {date.isoformat()}",
        "",
        f"- URL: {url}",
        f"- Modo: {mode}",
        "",
        "## Resumen",
        "",
        f"- Total de preguntas: {summary.total}",
        f"- Aciertos de recuperación: {ok}/{n_resp} ({_pct(summary.tasa_recuperacion)})",
        f"- Rechazos correctos: {rc}/{n_no} ({_pct(summary.tasa_rechazo)})",
        f"- Respuestas inventadas detectadas: {summary.inventadas}",
        "",
        "## Fallos",
        "",
    ]
    if not summary.fallos:
        lines.append("Ninguno")
    else:
        for s in summary.fallos:
            lines.append(f"- {s.question.id} [{s.outcome}]: {s.detail} — {s.question.pregunta}")
    return "\n".join(lines) + "\n"


def _failure_lines(summary: Summary) -> list[str]:
    if not summary.fallos:
        return ["Ninguno"]
    return [
        f"- {s.question.id} [{s.outcome}]: {s.detail} — {s.question.pregunta}"
        for s in summary.fallos
    ]


def render_comparison(
    left: Summary,
    right: Summary,
    *,
    left_url: str,
    right_url: str,
    mode: str,
    top_k: int,
    threshold: float,
    date: date,
) -> str:
    """Informe de dos ejecuciones con el mismo corpus, preguntas y parámetros."""
    lines = [
        f"# Comparación de evaluación {date.isoformat()}",
        "",
        f"- Modo: {mode}",
        f"- Preguntas: {left.total} (mismas para ambos endpoints)",
        f"- top_k: {top_k} (igual en ambos)",
        f"- Umbral semántico: {threshold} (igual en ambos)",
        "- Corpus: el cargado en ambos endpoints debe ser el mismo",
        "",
        "## Métricas",
        "",
        f"| Métrica | {left_url} | {right_url} |",
        "|---|---|---|",
        f"| Aciertos de recuperación | {left.recuperacion[0]}/{left.recuperacion[1]} "
        f"({_pct(left.tasa_recuperacion)}) | {right.recuperacion[0]}/{right.recuperacion[1]} "
        f"({_pct(right.tasa_recuperacion)}) |",
        f"| Rechazos correctos | {left.rechazos[0]}/{left.rechazos[1]} "
        f"({_pct(left.tasa_rechazo)}) | {right.rechazos[0]}/{right.rechazos[1]} "
        f"({_pct(right.tasa_rechazo)}) |",
        f"| Resultados en preguntas no_responde | {left.resultados_no_responde} "
        f"| {right.resultados_no_responde} |",
        f"| Respuestas inventadas detectadas | {left.inventadas} | {right.inventadas} |",
        "",
        f"## Fallos — {left_url}",
        "",
        *_failure_lines(left),
        "",
        f"## Fallos — {right_url}",
        "",
        *_failure_lines(right),
    ]
    return "\n".join(lines) + "\n"
