"""Sube un manual (PDF o DOCX) al servicio rag: POST {RAG_URL}/manuals.

Uso: python scripts/cargar_manual.py <ruta> --nombre <nombre>
Requiere `httpx` y las variables de entorno RAG_URL y SERVICE_TOKEN.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sube un manual al servicio rag.")
    parser.add_argument("ruta")
    parser.add_argument("--nombre", required=True)
    args = parser.parse_args(argv)

    path = Path(args.ruta)
    rag_url = os.environ.get("RAG_URL", "")
    token = os.environ.get("SERVICE_TOKEN", "")
    if not path.is_file():
        print(f"No existe el archivo: {path}", file=sys.stderr)
        return 1
    if not rag_url or not token:
        print("Faltan las variables de entorno RAG_URL y/o SERVICE_TOKEN.", file=sys.stderr)
        return 1

    url = rag_url.rstrip("/") + "/manuals"
    owns_client = client is None
    http = client or httpx.Client(timeout=120)
    try:
        response = http.post(
            url,
            files={"file": (path.name, path.read_bytes())},
            data={"name": args.nombre},
            headers={"X-Service-Token": token},
        )
    except httpx.HTTPError as exc:
        print(f"No se pudo contactar con rag: {exc}", file=sys.stderr)
        return 1
    finally:
        if owns_client:
            http.close()

    if response.status_code != 201:
        try:
            body = response.json()
            error, message = body.get("error", "error"), body.get("message", "")
        except ValueError:
            error, message = f"http_{response.status_code}", response.text[:200]
        print(f"{error}: {message}", file=sys.stderr)
        return 1

    body = response.json()
    print(f"manual_id: {body['manual_id']}")
    print(f"chunks: {body['chunks']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
