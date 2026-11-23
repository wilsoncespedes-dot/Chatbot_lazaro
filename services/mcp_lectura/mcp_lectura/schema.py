"""Ofertas de DEMOSTRACIÓN del servidor MCP.

Las tablas `demo_ofertas` y `mcp_auditoria` las crea `migrations/` (runner en el
despliegue); aquí solo queda la siembra opcional de filas ficticias.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

DEMO_LABEL = "DEMOSTRACIÓN"

# Ofertas ficticias: nunca datos reales de Lázaro Software.
SEED_OFFERS: tuple[dict[str, Any], ...] = (
    {
        "id": "demo-melgar-1",
        "destino": "Melgar",
        "titulo": "Oferta de demostración: plan fin de semana en Melgar",
        "precio_cop": 350000,
        "valido_desde": date(2026, 1, 1),
        "valido_hasta": date(2026, 12, 31),
    },
    {
        "id": "demo-mompox-1",
        "destino": "Mompox",
        "titulo": "Oferta de demostración: recorrido histórico por Mompox",
        "precio_cop": 280000,
        "valido_desde": date(2026, 1, 1),
        "valido_hasta": date(2026, 12, 31),
    },
    {
        "id": "demo-santa-marta-1",
        "destino": "Santa Marta",
        "titulo": "Oferta de demostración: playa y descanso en Santa Marta",
        "precio_cop": 420000,
        "valido_desde": date(2026, 1, 1),
        "valido_hasta": date(2026, 12, 31),
    },
)

SEED_STATEMENTS: tuple[tuple[str, tuple[Any, ...]], ...] = tuple(
    (
        "INSERT INTO demo_ofertas "
        "(id, destino, titulo, precio_cop, valido_desde, valido_hasta) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (
            offer["id"],
            offer["destino"],
            offer["titulo"],
            offer["precio_cop"],
            offer["valido_desde"],
            offer["valido_hasta"],
        ),
    )
    for offer in SEED_OFFERS
)


def initialize(connect: Callable[[], Any], seed: bool) -> None:
    """Solo con `seed` inserta las ofertas ficticias; sin DDL (lo hace el runner)."""
    if not seed:
        return
    connection = connect()
    try:
        cursor = connection.cursor()
        for statement, params in SEED_STATEMENTS:
            cursor.execute(statement, params)
        connection.commit()
    finally:
        connection.close()
