"""Errores de dominio del servicio rag (sin IO)."""
from __future__ import annotations


class DomainError(Exception):
    """Base de los errores de negocio; cada subclase fija su código y su HTTP status."""

    code = "domain_error"
    status_code = 400
