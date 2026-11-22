"""Esquema idempotente del servidor MCP y ofertas de DEMOSTRACIÓN."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

DEMO_LABEL = "DEMOSTRACIÓN"

DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS demo_ofertas (
        id TEXT PRIMARY KEY,
        destino TEXT NOT NULL,
        titulo TEXT NOT NULL,
        precio_cop INTEGER NOT NULL,
        valido_desde DATE NOT NULL,
        valido_hasta DATE NOT NULL,
        es_demo BOOLEAN NOT NULL DEFAULT TRUE CHECK (es_demo),
        etiqueta TEXT NOT NULL DEFAULT 'DEMOSTRACIÓN'
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS mcp_auditoria (
        id BIGSERIAL PRIMARY KEY,
        herramienta TEXT NOT NULL,
        args_sha256 TEXT NOT NULL,
        filas INTEGER NOT NULL,
        estado TEXT NOT NULL,
        cliente_sha256 TEXT NOT NULL,
        creado_en TIMESTAMPTZ NOT NULL
    )
    """.strip(),
)

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
    """Crea las tablas y, solo con `seed`, inserta las ofertas ficticias."""
    connection = connect()
    try:
        cursor = connection.cursor()
        for statement in DDL:
            cursor.execute(statement)
        if seed:
            for statement, params in SEED_STATEMENTS:
                cursor.execute(statement, params)
        connection.commit()
    finally:
        connection.close()
