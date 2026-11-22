"""Estrategias intercambiables de asignación automática de casos (#69)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Mapping, Protocol, Sequence, TypeVar


class UnknownStrategy(ValueError):
    """El nombre no corresponde a ninguna estrategia registrada (R5)."""


@dataclass(frozen=True)
class ContextoAsignacion:
    """Datos puros que la estrategia necesita: carga por asesor y último elegido."""

    cargas: Mapping[str, int]
    ultimo: str | None


class EstrategiaAsignacion(Protocol):
    """Regla pura: elige un `advisor_id` entre candidatos ya filtrados y no vacíos."""

    nombre: ClassVar[str]

    def elegir(self, candidatos: Sequence[str], contexto: ContextoAsignacion) -> str: ...


ESTRATEGIAS: dict[str, EstrategiaAsignacion] = {}

_T = TypeVar("_T", bound=type)


def registrar_estrategia(cls: _T) -> _T:
    """Registra la clase por `nombre` y la deja disponible en `ESTRATEGIAS`."""
    ESTRATEGIAS[cls.nombre] = cls()  # type: ignore[attr-defined]
    return cls


def obtener_estrategia(nombre: str) -> EstrategiaAsignacion:
    """Devuelve la estrategia registrada o lanza `UnknownStrategy` (R5)."""
    try:
        return ESTRATEGIAS[nombre]
    except KeyError:
        raise UnknownStrategy(
            f"Estrategia de asignación desconocida: {nombre}"
        ) from None


@registrar_estrategia
class PorCarga:
    """Elige al candidato con menos casos `assigned` y desempata por id (R2)."""

    nombre: ClassVar[str] = "por_carga"

    def elegir(self, candidatos: Sequence[str], contexto: ContextoAsignacion) -> str:
        return min(
            candidatos,
            key=lambda candidate_id: (
                contexto.cargas.get(candidate_id, 0),
                candidate_id,
            ),
        )


@registrar_estrategia
class RoundRobin:
    """Rota en orden lexicográfico y vuelve al inicio (R3)."""

    nombre: ClassVar[str] = "round_robin"

    def elegir(self, candidatos: Sequence[str], contexto: ContextoAsignacion) -> str:
        ordered = sorted(candidatos)
        if contexto.ultimo is not None:
            for candidate_id in ordered:
                if candidate_id > contexto.ultimo:
                    return candidate_id
        return ordered[0]
